"""
网页正文抓取模块

为助手工具提供按需的网页正文读取：
- 默认使用宿主提供的 httpx 流式读取；
- 可配置使用系统浏览器渲染动态页面。

两种方式共用 URL 与跳转校验，限制响应大小和处理时间，
只输出标题与可读正文。
"""

import asyncio
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from astrbot.api import logger

from .screenshot import ScreenshotError, ScreenshotService
from .urls import is_valid_url

# 单个响应体的大小上限
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
# 手动跟随跳转的最大次数
MAX_REDIRECTS = 5

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_REQUEST_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.3,en;q=0.2",
    "Upgrade-Insecure-Requests": "1",
}

# 正文提取优先尝试的选择器（从高到低）
_CONTENT_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".article-content",
    ".post-content",
    ".content",
]
# 提取正文前移除的干扰元素
_STRIP_TAGS = [
    "script",
    "style",
    "noscript",
    "template",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "iframe",
]


class FetchError(Exception):
    """网页正文抓取失败"""


@dataclass
class ContentResult:
    """一次正文抓取的结果。"""

    url: str  # 请求的 URL
    final_url: str  # 跳转后的最终 URL
    title: str  # 页面标题
    content: str  # 可读正文
    truncated: bool = False  # 正文是否因长度上限被截断


class ContentFetcher:
    """网页正文抓取器。

    持有一个按需创建、进程内共享的 httpx 客户端；浏览器模式复用
    截图服务的实例池。
    """

    _shared_client: httpx.AsyncClient | None = None
    _shared_client_params: tuple = ()

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "",
        proxy: str = "",
        retry_count: int = 3,
        retry_delay_s: int = 2,
        max_content_length: int = 10000,
        fetch_mode: str = "httpx",
        screenshot_service: ScreenshotService | None = None,
        allow_local: bool = False,
    ):
        """初始化正文抓取器。

        Args:
            timeout: 单次请求的处理时间上限（秒）。
            user_agent: 请求 User-Agent，留空使用默认值。
            proxy: HTTP 代理。
            retry_count: HTTP 请求失败后的重试次数。
            retry_delay_s: 重试间隔秒数。
            max_content_length: 正文长度上限（字符）。
            fetch_mode: 抓取方式（httpx/browser）。
            screenshot_service: 浏览器模式使用的截图服务。
            allow_local: 是否允许本地/内网地址（SSRF 防护开关）。
        """
        self.timeout = timeout
        self.user_agent = user_agent
        self.proxy = proxy
        self.retry_count = max(0, int(retry_count))
        self.retry_delay_s = max(0, int(retry_delay_s))
        self.max_content_length = int(max_content_length)
        self.fetch_mode = "browser" if fetch_mode == "browser" else "httpx"
        self.screenshot_service = screenshot_service
        self.allow_local = allow_local

    def apply_runtime_config(self, settings: dict) -> None:
        """应用运行中的配置更新。"""
        mapping = {
            "request_timeout_s": "timeout",
            "user_agent": "user_agent",
            "proxy": "proxy",
            "retry_count": "retry_count",
            "retry_delay_s": "retry_delay_s",
            "max_content_length": "max_content_length",
            "fetch_mode": "fetch_mode",
            "allow_local_addresses": "allow_local",
        }
        for key, attr in mapping.items():
            if key in settings:
                value = settings[key]
                if attr == "fetch_mode":
                    value = "browser" if value == "browser" else "httpx"
                setattr(self, attr, value)

    async def fetch(self, url: str, fetch_mode: str | None = None) -> ContentResult:
        """抓取网页并返回标题与可读正文。

        Args:
            url: 目标 URL。
            fetch_mode: 临时覆盖抓取方式。

        Raises:
            FetchError: URL 不合法、访问失败或解析失败。
        """
        mode = fetch_mode or self.fetch_mode
        if not is_valid_url(url, self.allow_local):
            raise FetchError(f"无效或被禁止访问的 URL: {url}")

        if mode == "browser":
            try:
                return await self._fetch_with_browser(url)
            except ScreenshotError as e:
                logger.warning(f"浏览器抓取失败，回退到 HTTP: {url}, 错误: {e}")
            except FetchError:
                raise

        return await self._fetch_with_httpx(url)

    # ==================== httpx 流式抓取 ====================

    async def _fetch_with_httpx(self, url: str) -> ContentResult:
        """流式抓取网页，手动跟随跳转并在每一跳复用校验规则。"""
        import time
        from urllib.parse import urljoin

        deadline = time.monotonic() + self.timeout
        current_url = url
        for hop in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FetchError(f"抓取超时（上限 {self.timeout} 秒）: {url}")
            request = self._build_request(current_url)
            client = self._get_client()
            try:
                async with asyncio.timeout(remaining):
                    response = await client.send(request, stream=True)
            except TimeoutError as e:
                raise FetchError(f"抓取超时（上限 {self.timeout} 秒）: {url}") from e
            try:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        raise FetchError(f"跳转缺少目标地址: {current_url}")
                    if hop == MAX_REDIRECTS:
                        raise FetchError(f"跳转次数超过上限: {url}")
                    next_url = urljoin(str(response.url), location)
                    if not is_valid_url(next_url, self.allow_local):
                        raise FetchError(f"跳转目标不允许访问: {next_url}")
                    current_url = next_url
                    continue

                if response.status_code >= 400:
                    raise FetchError(
                        f"网页返回错误状态码 {response.status_code}: {current_url}"
                    )

                html = await self._read_body(response)
            finally:
                if not response.is_closed:
                    await response.aclose()

            title, content, truncated = self._extract_readable(html)
            if not content:
                raise FetchError(f"未能从网页中提取到正文: {current_url}")
            return ContentResult(
                url=url,
                final_url=current_url,
                title=title,
                content=content,
                truncated=truncated,
            )
        raise FetchError(f"跳转次数超过上限: {url}")  # pragma: no cover

    def _build_request(self, url: str) -> httpx.Request:
        """构造带请求头的 GET 请求。"""
        headers = dict(_REQUEST_HEADERS)
        headers["User-Agent"] = self.user_agent or _DEFAULT_USER_AGENT
        return httpx.Request("GET", url, headers=headers)

    def _get_client(self) -> httpx.AsyncClient:
        """返回共享的 httpx 客户端；代理等参数变化时重建。"""
        params = (self.proxy,)
        client = ContentFetcher._shared_client
        if client is not None and ContentFetcher._shared_client_params == params:
            return client
        if client is not None:
            # 旧客户端交给后台关闭，不阻塞当前请求
            asyncio.get_running_loop().create_task(_close_quietly(client))
        timeout = httpx.Timeout(
            connect=min(10, self.timeout),
            read=self.timeout,
            write=self.timeout,
            pool=self.timeout,
        )
        client = httpx.AsyncClient(
            timeout=timeout,
            proxy=self.proxy or None,
            follow_redirects=False,
        )
        ContentFetcher._shared_client = client
        ContentFetcher._shared_client_params = params
        return client

    async def _read_body(self, response: httpx.Response) -> str:
        """流式读取响应体，限制总大小。"""
        total = 0
        chunks: list[bytes] = []
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise FetchError(
                        f"响应体超过大小上限 ({MAX_RESPONSE_BYTES // (1024 * 1024)} MB)"
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        try:
            return raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return raw.decode("utf-8", errors="replace")

    # ==================== 浏览器渲染 ====================

    async def _fetch_with_browser(self, url: str) -> ContentResult:
        """使用系统浏览器渲染后提取正文。"""
        if self.screenshot_service is None:
            raise FetchError("浏览器渲染方式不可用：截图服务未初始化")
        final_url, html = await self.screenshot_service.render_html(url)
        if not is_valid_url(final_url, self.allow_local):
            raise FetchError(f"跳转后的地址不允许访问: {final_url}")
        title, content, truncated = self._extract_readable(html)
        if not content:
            raise FetchError(f"未能从网页中提取到正文: {final_url}")
        return ContentResult(
            url=url,
            final_url=final_url,
            title=title,
            content=content,
            truncated=truncated,
        )

    # ==================== 可读正文提取 ====================

    def _extract_readable(self, html: str) -> tuple[str, str, bool]:
        """从 HTML 中提取 (标题, 可读正文, 是否截断)，正文按上限截断。"""
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as e:
            raise FetchError(f"HTML 解析失败: {e}") from e

        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        if not title:
            og = soup.find("meta", attrs={"property": "og:title"})
            title = og.get("content", "").strip() if og else ""

        for element in soup(_STRIP_TAGS):
            element.decompose()

        content = ""
        for selector in _CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if node is not None:
                text = node.get_text(separator="\n", strip=True)
                if len(text) > len(content):
                    content = text
        if not content:
            body = soup.find("body")
            if body is not None:
                content = body.get_text(separator="\n", strip=True)

        truncated = False
        if len(content) > self.max_content_length:
            content = content[: self.max_content_length]
            truncated = True
        return title, content, truncated

    @staticmethod
    def format_tool_result(result: ContentResult, max_chars: int | None = None) -> str:
        """把抓取结果整理为返回给模型的文本。"""
        content = result.content
        limit = max_chars or len(content)
        if len(content) > limit:
            content = content[:limit] + f"…(共 {len(result.content)} 字符)"
        parts = [f"最终URL: {result.final_url}", f"标题: {result.title or '无标题'}"]
        if result.truncated:
            parts.append(f"说明: 正文按配置截断至 {len(result.content)} 字符")
        parts.append(f"正文:\n{content}")
        return "\n".join(parts)

    async def close(self) -> None:
        """关闭共享的 HTTP 客户端。"""
        client = ContentFetcher._shared_client
        ContentFetcher._shared_client = None
        ContentFetcher._shared_client_params = ()
        if client is not None:
            await _close_quietly(client)


async def _close_quietly(client: httpx.AsyncClient) -> None:
    try:
        await client.aclose()
    except Exception as e:  # pragma: no cover
        logger.debug(f"关闭 HTTP 客户端失败（可忽略）: {e}")


__all__ = [
    "ContentFetcher",
    "ContentResult",
    "FetchError",
    "MAX_RESPONSE_BYTES",
]
