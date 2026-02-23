"""
网页分析插件 - 网页分析器模块

这个模块是网页分析的核心组件，负责：
- 网页内容的异步抓取
- URL的提取和验证
- 网页内容的结构化解析
- 特定类型内容的提取（图片、链接、表格等）
- 网页截图的捕获

使用异步HTTP客户端和BeautifulSoup进行网页处理，支持代理、重试等高级功能。
"""

import gc
import io
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
import psutil
from bs4 import BeautifulSoup
from PIL import Image

from astrbot.api import logger


# 自定义异常类
class WebAnalyzerException(Exception):
    """网页分析器基础异常类"""

    pass


class NetworkError(WebAnalyzerException):
    """网络相关错误"""

    pass


class ParsingError(WebAnalyzerException):
    """网页解析相关错误"""

    pass


class ScreenshotError(WebAnalyzerException):
    """网页截图相关错误"""

    pass


class ContentExtractionError(WebAnalyzerException):
    """内容提取相关错误"""

    pass


class WebAnalyzer:
    """网页分析器核心类

    这个类提供了完整的网页分析功能，包括：
    - 网页内容的异步抓取
    - URL的提取和验证
    - HTML内容的解析和结构化
    - 特定类型内容的提取
    - 网页截图的捕获

    支持异步上下文管理器，确保资源的正确释放。
    """

    # 类级别的浏览器实例池，用于复用浏览器实例
    _browser_pool = []
    _max_browser_instances = 3  # 最大浏览器实例数量
    _browser_last_used = {}  # 记录每个浏览器实例的最后使用时间
    _browser_lock = None  # 浏览器实例池锁
    _last_cleanup_time = 0  # 上次清理时间，用于定期清理任务
    _cleanup_interval = 60 * 5  # 清理间隔，5分钟
    _instance_timeout = 60 * 30  # 实例超时时间，30分钟未使用则清理

    # 浏览器安装相关
    _browser_install_lock = None  # 浏览器安装进程锁
    _browser_install_status_file = None  # 浏览器安装状态文件路径
    _is_installing = False  # 是否正在安装浏览器

    def __init__(
        self,
        max_content_length: int = 10000,
        timeout: int = 30,
        user_agent: str = None,
        proxy: str = None,
        retry_count: int = 3,
        retry_delay: int = 2,
        enable_memory_monitor: bool = True,
        memory_threshold: float = 80.0,  # 内存使用阈值百分比
        enable_unified_domain: bool = True,  # 是否启用域名统一处理
    ):
        """初始化网页分析器

        Args:
            max_content_length: 提取的最大内容长度，防止内容过大
            timeout: HTTP请求超时时间，单位为秒
            user_agent: 请求时使用的User-Agent头
            proxy: HTTP代理设置，格式为 http://host:port 或 https://host:port
            retry_count: 请求失败时的重试次数
            retry_delay: 重试间隔时间，单位为秒
            enable_memory_monitor: 是否启用内存监控
            memory_threshold: 内存使用阈值百分比，超过此阈值时自动释放内存
            enable_unified_domain: 是否启用域名统一处理（如google.com和www.google.com视为同一域名）
        """
        self.max_content_length = max_content_length
        self.timeout = timeout
        self.user_agent = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.proxy = proxy
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.client = None
        self.browser = None
        # 内存监控相关
        self.enable_memory_monitor = enable_memory_monitor
        self.memory_threshold = memory_threshold
        self.last_memory_check = time.time()
        self.memory_check_interval = 60 * 5  # 内存检查间隔，单位为秒，从60秒延长到5分钟
        # URL处理相关
        self.enable_unified_domain = enable_unified_domain

        # 初始化浏览器锁
        if not WebAnalyzer._browser_lock:
            import asyncio

            WebAnalyzer._browser_lock = asyncio.Lock()

        # 初始化浏览器安装锁
        if not WebAnalyzer._browser_install_lock:
            import asyncio

            WebAnalyzer._browser_install_lock = asyncio.Lock()

        # 初始化浏览器安装状态文件路径
        if not WebAnalyzer._browser_install_status_file:
            from pathlib import Path

            try:
                from astrbot.core.utils.astrbot_path import get_astrbot_data_path
                data_path = get_astrbot_data_path()
                status_file_path = data_path / "plugin_data" / "astrbot_plugin_web_analyzer" / "browser_install_status.json"
                # 确保目录存在
                status_file_path.parent.mkdir(parents=True, exist_ok=True)
                WebAnalyzer._browser_install_status_file = str(status_file_path)
            except Exception as e:
                logger.warning(f"无法初始化浏览器状态文件路径: {e}, 将使用临时路径")
                import tempfile
                WebAnalyzer._browser_install_status_file = str(Path(tempfile.gettempdir()) / "browser_install_status.json")

    @staticmethod
    async def _cleanup_browser_pool():
        """定期清理浏览器实例池，移除过期或无效的实例

        该方法会：
        1. 清理超过30分钟未使用的浏览器实例
        2. 清理已断开连接的浏览器实例
        3. 确保实例池大小不超过最大值
        """
        try:
            current_time = time.time()

            # 检查是否需要执行清理
            if (
                current_time - WebAnalyzer._last_cleanup_time
                < WebAnalyzer._cleanup_interval
            ):
                return

            async with WebAnalyzer._browser_lock:
                WebAnalyzer._last_cleanup_time = current_time
                valid_browsers = []

                for browser in WebAnalyzer._browser_pool:
                    last_used = WebAnalyzer._browser_last_used.get(id(browser), 0)
                    try:
                        # 检查浏览器实例是否有效（未过期且已连接）
                        if (
                            current_time - last_used < WebAnalyzer._instance_timeout
                            and browser.is_connected()
                        ):
                            valid_browsers.append(browser)
                        else:
                            # 关闭过期或已断开连接的浏览器实例
                            await browser.close()
                            logger.info("关闭过期或已断开连接的浏览器实例")
                    except Exception as e:
                        logger.error(f"检查浏览器实例状态失败: {e}, 将关闭该实例")
                        try:
                            await browser.close()
                        except Exception as close_e:
                            logger.error(f"关闭异常浏览器实例失败: {close_e}")

                # 更新浏览器实例池，确保不超过最大实例数量
                WebAnalyzer._browser_pool = valid_browsers[
                    : WebAnalyzer._max_browser_instances
                ]
                logger.debug(
                    f"浏览器实例池清理完成，当前池大小: {len(WebAnalyzer._browser_pool)}"
                )
        except Exception as e:
            logger.error(f"清理浏览器实例池失败: {e}")

    def _check_memory_usage(self):
        """检查内存使用情况，超过阈值时自动释放内存

        Returns:
            bool: 如果释放了内存，返回True，否则返回False
        """
        current_time = time.time()
        # 定期检查内存使用情况
        if current_time - self.last_memory_check < self.memory_check_interval:
            return False

        self.last_memory_check = current_time

        try:
            # 获取内存使用情况
            memory_info = psutil.virtual_memory()
            memory_usage = memory_info.percent

            logger.debug(f"当前内存使用情况: {memory_usage:.1f}%")

            if memory_usage > self.memory_threshold:
                logger.warning(
                    f"内存使用超过阈值 ({self.memory_threshold}%), 自动释放资源"
                )
                # 释放内存
                self._release_memory()
                return True
        except Exception as e:
            logger.error(f"检查内存使用情况失败: {e}")

        return False

    async def _optimize_browser_pool(self):
        """异步优化浏览器实例池，根据内存使用情况调整实例数量

        根据当前内存使用情况动态调整浏览器实例池大小：
        - 内存使用率 > 90%: 只保留0个实例
        - 内存使用率 > 80%: 只保留1个实例
        - 内存使用率 > 70%: 只保留2个实例
        - 内存使用率 ≤70%: 保留最大数量减1个实例
        """
        try:
            async with WebAnalyzer._browser_lock:
                # 获取当前内存使用情况
                memory_info = psutil.virtual_memory()
                memory_usage = memory_info.percent

                # 根据内存使用情况决定保留的实例数量
                if memory_usage > 90:
                    max_keep = 0
                elif memory_usage > 80:
                    max_keep = 1
                elif memory_usage > 70:
                    max_keep = 2
                else:
                    max_keep = WebAnalyzer._max_browser_instances - 1

                # 释放超出保留数量的浏览器实例
                while len(WebAnalyzer._browser_pool) > max_keep:
                    browser = WebAnalyzer._browser_pool.pop()
                    try:
                        if browser.is_connected():
                            await browser.close()
                            logger.info(
                                f"释放空闲浏览器实例，当前池大小: {len(WebAnalyzer._browser_pool)}"
                            )
                    except Exception as e:
                        logger.error(f"释放浏览器实例失败: {e}")
                        # 忽略单个实例释放失败，继续处理其他实例
        except Exception as e:
            logger.error(f"优化浏览器实例池失败: {e}")

    def _release_memory(self):
        """释放内存资源

        执行垃圾回收，释放不再使用的资源，优化内存使用

        优化策略：
        1. 执行垃圾回收释放内存
        2. 智能调整浏览器实例池大小
        3. 增强容错机制，确保内存释放过程稳定
        """
        try:
            # 执行垃圾回收，释放内存
            collected = gc.collect()
            logger.info(f"执行垃圾回收，释放内存，回收了 {collected} 个对象")

            # 在异步上下文中执行浏览器池优化
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._optimize_browser_pool())
                else:
                    # 如果事件循环未运行，记录警告但不抛出异常
                    logger.warning("事件循环未运行，跳过浏览器实例池优化")
            except Exception as e:
                logger.error(f"执行浏览器实例池优化失败: {e}")
        except Exception as e:
            logger.error(f"释放内存资源失败: {e}")
            # 增强容错机制，确保内存释放失败不会影响插件正常运行

    async def __aenter__(self):
        """异步上下文管理器入口

        初始化异步HTTP客户端，配置：
        - 请求超时时间
        - 代理设置（如果提供）
        - 其他HTTP客户端参数

        Returns:
            返回WebAnalyzer实例自身，用于上下文管理
        """
        # 配置客户端参数
        client_params = {"timeout": self.timeout}

        # 添加代理配置（如果有）
        if self.proxy:
            client_params["proxies"] = {"http://": self.proxy, "https://": self.proxy}

        self.client = httpx.AsyncClient(**client_params)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口

        清理资源，确保：
        - 异步HTTP客户端正确关闭
        - 浏览器实例正确处理（放回池中或关闭）
        - 资源泄漏的防止

        Args:
            exc_type: 异常类型（如果有）
            exc_val: 异常值（如果有）
            exc_tb: 异常回溯（如果有）
        """
        if self.client:
            await self.client.aclose()

        if self.browser:
            try:
                # 将浏览器实例放回池中，以便复用
                async with WebAnalyzer._browser_lock:
                    # 检查浏览器实例是否仍然可用
                    if (
                        len(WebAnalyzer._browser_pool)
                        < WebAnalyzer._max_browser_instances
                    ):
                        # 更新最后使用时间
                        WebAnalyzer._browser_last_used[id(self.browser)] = time.time()
                        # 将浏览器实例放回池中
                        WebAnalyzer._browser_pool.append(self.browser)
                        logger.debug(
                            f"浏览器实例已放回池中，当前池大小: {len(WebAnalyzer._browser_pool)}"
                        )
                    else:
                        # 池已满，关闭浏览器实例
                        await self.browser.close()
                        logger.debug("浏览器实例池已满，关闭浏览器实例")
            except Exception as e:
                logger.error(f"处理浏览器实例失败: {e}")
                # 出现错误时，确保浏览器实例被关闭
                try:
                    await self.browser.close()
                except Exception:
                    pass

        # 检查内存使用情况
        self._check_memory_usage()

    def extract_urls(
        self,
        text: str,
        enable_no_protocol: bool = False,
        default_protocol: str = "https",
    ) -> list[str]:
        """从文本中提取所有HTTP/HTTPS URL链接

        使用正则表达式匹配文本中的URL，支持：
        - HTTP和HTTPS协议
        - 各种常见的URL格式
        - 排除中文等非ASCII字符作为URL的一部分
        - 可选识别无协议头的URL（如 www.example.com）

        Args:
            text: 要从中提取URL的文本内容
            enable_no_protocol: 是否识别无协议头的URL
            default_protocol: 无协议头URL使用的默认协议（http或https）

        Returns:
            包含所有提取到的URL的列表
        """
        urls = self._extract_protocol_urls(text)
        if enable_no_protocol:
            no_protocol_urls = self._extract_no_protocol_urls(
                text, urls, default_protocol
            )
            urls.extend(no_protocol_urls)
        return urls

    def _extract_protocol_urls(self, text: str) -> list[str]:
        """提取带协议头的URL"""
        url_pattern = r"https?://[^\s\u4e00-\u9fff]+"
        return re.findall(url_pattern, text)

    def _extract_no_protocol_urls(
        self, text: str, existing_urls: list[str], default_protocol: str
    ) -> list[str]:
        """提取无协议头的URL"""
        text_for_no_protocol = self._remove_existing_urls(text, existing_urls)
        no_protocol_urls = self._find_no_protocol_urls(text_for_no_protocol)
        return self._format_no_protocol_urls(no_protocol_urls, default_protocol)

    def _remove_existing_urls(self, text: str, urls: list[str]) -> str:
        """从文本中移除已提取的URL"""
        text_for_no_protocol = text
        for url in urls:
            text_for_no_protocol = text_for_no_protocol.replace(url, "")
        return text_for_no_protocol

    def _find_no_protocol_urls(self, text: str) -> list[str]:
        """查找无协议头的URL"""
        no_protocol_pattern = r"(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9](?:\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9])+(?:/[^\s\u4e00-\u9fff]*)?"
        return re.findall(no_protocol_pattern, text)

    def _format_no_protocol_urls(
        self, urls: list[str], default_protocol: str
    ) -> list[str]:
        """格式化无协议头的URL"""
        formatted_urls = []
        for url in urls:
            cleaned_url = url.rstrip(".,;:!?)'\"")
            full_url = f"{default_protocol}://{cleaned_url}"
            formatted_urls.append(full_url)
        return formatted_urls

    def is_valid_url(self, url: str) -> bool:
        """验证URL格式是否有效

        检查URL是否符合基本格式要求：
        - 必须包含有效的协议（http/https）
        - 必须包含有效的域名或IP地址
        - 必须能被正确解析

        Args:
            url: 要验证的URL字符串

        Returns:
            True表示URL格式有效，False表示无效
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def normalize_url(self, url: str) -> str:
        """规范化URL，统一格式

        对URL进行规范化处理：
        - 🔄  转换为小写
        - 📏  统一处理尾部斜杠
        - 🧹  去除多余的查询参数和片段（可选）
        - 🌐  统一域名格式（如google.com和www.google.com视为同一域名）

        Args:
            url: 要规范化的URL字符串

        Returns:
            规范化后的URL字符串
        """
        try:
            parsed = urlparse(url)
            netloc = self._normalize_netloc(parsed.netloc.lower())
            normalized = parsed._replace(
                scheme=parsed.scheme.lower(),
                netloc=netloc,
                path=parsed.path.rstrip("/"),
            )
            return normalized.geturl()
        except Exception:
            return url

    def _normalize_netloc(self, netloc: str) -> str:
        """规范化网络位置（域名或IP）"""
        if not self.enable_unified_domain or not netloc or "." not in netloc:
            return netloc
        if netloc.startswith("www.") or ".www." in netloc:
            return netloc
        if self._is_ip_address(netloc):
            return netloc
        return f"www.{netloc}"

    def _is_ip_address(self, netloc: str) -> bool:
        """检查是否为IP地址"""
        try:
            import ipaddress

            ipaddress.ip_address(netloc)
            return True
        except ValueError:
            return False

    async def fetch_webpage(self, url: str) -> str:
        """异步抓取网页HTML内容

        使用异步HTTP客户端抓取网页，支持：
        - 自定义User-Agent
        - 自动跟随重定向
        - 配置的代理设置
        - 智能重试机制（失败后自动重试）

        Args:
            url: 要抓取的网页URL

        Returns:
            网页的HTML文本内容

        Raises:
            NetworkError: 当网络请求失败时抛出
        """
        # 构造HTTP请求头，模拟真实浏览器行为
        headers = self._build_http_headers()

        # 执行带重试机制的HTTP请求
        return await self._fetch_with_retry(url, headers)

    def _build_http_headers(self) -> dict:
        """构造HTTP请求头

        Returns:
            包含完整请求头的字典
        """
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Sec-GPC": "1",
        }

    async def _fetch_with_retry(self, url: str, headers: dict) -> str:
        """执行带重试机制的HTTP请求

        Args:
            url: 目标URL
            headers: HTTP请求头

        Returns:
            网页HTML内容

        Raises:
            NetworkError: 当所有重试都失败时抛出
        """
        import asyncio

        # 实现重试机制，最多尝试 retry_count + 1 次
        for attempt in range(self.retry_count + 1):
            try:
                response = await self.client.get(
                    url, headers=headers, follow_redirects=True
                )
                response.raise_for_status()

                logger.info(
                    f"抓取网页成功: {url} (尝试 {attempt + 1}/{self.retry_count + 1})"
                )
                return response.text
            except Exception as e:
                if attempt < self.retry_count:
                    # 还有重试次数，等待 retry_delay 秒后重试
                    logger.warning(
                        f"抓取网页失败，将重试: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    # 重试次数用完，抛出网络错误
                    logger.error(
                        f"抓取网页失败: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    raise NetworkError(f"抓取网页失败: {url}, 错误: {str(e)}") from e

    def extract_content(self, html: str, url: str) -> dict:
        """从HTML中提取结构化的网页内容

        解析HTML文档，提取关键内容：
        - 网页标题
        - 主要正文内容
        - 支持多种内容选择策略

        使用BeautifulSoup进行HTML解析，优先选择语义化标签
        （如article、main等）提取内容，确保提取的内容质量。

        Args:
            html: 网页的HTML文本内容
            url: 网页的原始URL，用于结果返回

        Returns:
            包含标题、内容和URL的字典

        Raises:
            ParsingError: 当HTML解析失败时抛出
        """
        try:
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html, "lxml")

            # 提取网页标题
            title_text = self._extract_title(soup)

            # 提取文章内容
            content_text = self._extract_main_content(soup)

            # 限制内容长度，防止内容过大
            content_text = self._limit_content_length(content_text)

            return {"title": title_text, "content": content_text, "url": url}
        except Exception as e:
            logger.error(f"解析网页内容失败: {e}")
            raise ParsingError(f"解析网页内容失败: {url}, 错误: {str(e)}") from e

    def _get_content_selectors(self) -> list[str]:
        """获取内容选择器列表（优先级从高到低）

        Returns:
            CSS选择器列表，按优先级排序
        """
        return [
            "article",  # 语义化文章标签
            "main",  # 语义化主内容标签
            ".article-content",  # 常见文章内容类名
            ".post-content",  # 常见博客内容类名
            ".content",  # 通用内容类名
            "body",  # 兜底：使用整个body
        ]

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """从BeautifulSoup对象中提取网页标题

        Args:
            soup: BeautifulSoup对象

        Returns:
            网页标题文本
        """
        title = soup.find("title")
        return title.get_text().strip() if title else "无标题"

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """从BeautifulSoup对象中提取主要内容

        使用多策略内容提取算法:
        1. 优先选择语义化标签(article, main)
        2. 选择常见的内容类名
        3. 最后使用整个body作为兜底

        Args:
            soup: BeautifulSoup对象

        Returns:
            提取的主要内容文本
        """
        # 获取内容选择器列表
        content_selectors = self._get_content_selectors()

        # 尝试从各个选择器中提取内容，选择最长的作为结果
        content_text = self._try_extract_from_selectors(soup, content_selectors)

        # 如果没找到合适的内容，使用body作为最后的兜底方案
        if not content_text:
            content_text = self._extract_from_body(soup)

        return content_text

    def _try_extract_from_selectors(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        """尝试从多个选择器中提取内容

        Args:
            soup: BeautifulSoup对象
            selectors: CSS选择器列表

        Returns:
            提取的最长内容文本
        """
        content_text = ""
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # 清理内容，移除脚本和样式标签
                cleaned_element = self._clean_content_element(element)
                text = cleaned_element.get_text(separator="\n", strip=True)
                # 选择最长的内容作为结果
                if len(text) > len(content_text):
                    content_text = text

        return content_text

    def _extract_from_body(self, soup: BeautifulSoup) -> str:
        """从body标签中提取内容（兜底方案）

        Args:
            soup: BeautifulSoup对象

        Returns:
            提取的内容文本
        """
        body = soup.find("body")
        if body:
            cleaned_body = self._clean_content_element(body)
            return cleaned_body.get_text(separator="\n", strip=True)
        return ""

    def _clean_content_element(self, element: BeautifulSoup) -> BeautifulSoup:
        """清理内容元素，移除脚本和样式标签

        Args:
            element: BeautifulSoup元素

        Returns:
            清理后的BeautifulSoup元素
        """
        # 直接处理元素，不需要创建副本
        # 移除脚本和样式标签，避免干扰内容提取
        for script in element.find_all(["script", "style"]):
            script.decompose()
        return element

    def _limit_content_length(self, content: str) -> str:
        """限制内容长度，防止内容过大

        Args:
            content: 原始内容文本

        Returns:
            限制长度后的内容文本
        """
        if len(content) > self.max_content_length:
            return content[: self.max_content_length] + "..."
        return content

    def crop_screenshot(
        self, screenshot_bytes: bytes, crop_area: tuple[int, int, int, int]
    ) -> bytes:
        """裁剪截图

        Args:
            screenshot_bytes: 原始截图二进制数据
            crop_area: 裁剪区域，格式为 (left, top, right, bottom)

        Returns:
            裁剪后的截图二进制数据
        """
        try:
            # 将二进制数据转换为Image对象
            image = Image.open(io.BytesIO(screenshot_bytes))

            # 裁剪图片
            cropped_image = image.crop(crop_area)

            # 将裁剪后的图片转换回二进制数据
            output = io.BytesIO()
            cropped_image.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            logger.error(f"裁剪截图失败: {e}")
            raise ScreenshotError(f"裁剪截图失败: {str(e)}") from e

    async def capture_screenshot(
        self,
        url: str,
        quality: int = 80,
        width: int = 1280,
        height: int = 720,
        full_page: bool = False,
        wait_time: int = 2000,
        format: str = "jpeg",
    ) -> bytes:
        """使用Playwright捕获网页截图

        自动处理浏览器的安装和配置，支持：
        - 自定义分辨率和质量
        - 全屏截图或可视区域截图
        - 自定义等待时间，确保页面加载完成
        - 支持JPEG、PNG格式

        Args:
            url: 要截图的网页URL
            quality: 截图质量，范围1-100（仅适用于JPEG格式）
            width: 截图宽度（像素）
            height: 截图高度（像素）
            full_page: 是否截取整个页面，False仅截取可视区域
            wait_time: 页面加载后等待的时间（毫秒），确保动态内容加载
            format: 截图格式，支持"jpeg"、"png"

        Returns:
            截图的二进制数据

        Raises:
            ScreenshotError: 当截图失败时抛出
        """
        try:
            # 确保浏览器已安装
            await self._ensure_browser_installed()

            # 清理浏览器实例池
            await self._cleanup_browser_pool()

            # 获取或创建浏览器实例
            browser, playwright_instance = await self._get_or_create_browser()

            try:
                # 执行截图操作
                screenshot_bytes = await self._perform_screenshot(
                    browser=browser,
                    url=url,
                    width=width,
                    height=height,
                    quality=quality,
                    full_page=full_page,
                    wait_time=wait_time,
                    format=format,
                )

                # 处理浏览器实例（放回池中或保存）
                await self._handle_browser_after_use(browser, playwright_instance)

                return screenshot_bytes

            except Exception as screenshot_error:
                # 截图失败时的错误处理
                screenshot_bytes = await self._handle_screenshot_error(
                    browser=browser,
                    playwright_instance=playwright_instance,
                    screenshot_error=screenshot_error,
                    url=url,
                    width=width,
                    height=height,
                    quality=quality,
                    full_page=full_page,
                    wait_time=wait_time,
                    format=format,
                )
                return screenshot_bytes

            finally:
                # 确保playwright实例被关闭
                if playwright_instance:
                    await playwright_instance.stop()

        except Exception as e:
            logger.error(f"捕获网页截图失败: {url}, 错误: {e}")
            raise ScreenshotError(f"捕获网页截图失败: {url}, 错误: {str(e)}") from e

    def _get_browser_install_path(self) -> str:
        """获取浏览器安装路径

        Returns:
            str: 浏览器安装路径
        """
        from pathlib import Path

        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            data_path = get_astrbot_data_path()
            browser_path = data_path / "plugin_data" / "astrbot_plugin_web_analyzer" / "playwright_browsers"
            # 确保目录存在
            browser_path.mkdir(parents=True, exist_ok=True)
            return str(browser_path)
        except Exception as e:
            logger.warning(f"无法获取AstrBot数据路径，使用临时路径: {e}")
            import tempfile
            temp_path = Path(tempfile.gettempdir()) / "astrbot_web_analyzer_browsers"
            temp_path.mkdir(parents=True, exist_ok=True)
            return str(temp_path)

    def _load_install_status(self) -> dict:
        """加载浏览器安装状态

        Returns:
            dict: 安装状态字典，包含installed、install_path、install_time等信息
        """
        import json
        from pathlib import Path

        status_file = Path(WebAnalyzer._browser_install_status_file)

        if not status_file.exists():
            return {"installed": False}

        try:
            with open(status_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载浏览器安装状态失败: {e}")
            return {"installed": False}

    def _save_install_status(self, status: dict):
        """保存浏览器安装状态

        Args:
            status: 要保存的状态字典
        """
        import json
        from pathlib import Path

        try:
            status_file = Path(WebAnalyzer._browser_install_status_file)
            status_file.parent.mkdir(parents=True, exist_ok=True)

            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)

            logger.debug(f"已保存浏览器安装状态: {status}")
        except Exception as e:
            logger.error(f"保存浏览器安装状态失败: {e}")

    async def _check_browser_installed_async(self) -> tuple[bool, str]:
        """异步检查浏览器是否已安装

        Returns:
            tuple: (是否已安装, 浏览器路径或错误信息)
        """
        from playwright.async_api import async_playwright

        try:
            pw = await async_playwright().start()
            try:
                browser_path = pw.chromium.executable_path
                import os
                exists = os.path.exists(browser_path)
                return exists, browser_path
            finally:
                await pw.stop()
        except Exception as e:
            return False, str(e)

    async def _install_browser_async(self) -> str:
        """异步安装浏览器

        Returns:
            str: 安装路径

        Raises:
            ScreenshotError: 安装失败时抛出
        """
        import asyncio
        import os
        import sys

        install_path = self._get_browser_install_path()
        logger.info(f"开始安装浏览器到: {install_path}")

        # 设置环境变量，指定安装路径
        env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": install_path}

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "playwright",
            "install",
            "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        try:
            # 等待进程完成，设置超时
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300  # 5分钟超时
            )

            # 解码输出
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # 合并标准输出和错误输出
            full_output = f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}"

            # 检查是否真正失败（忽略仅有弃用警告的情况）
            if process.returncode != 0:
                # 检查 stderr 是否只有弃用警告（而非真正的错误）
                stderr_lines = [
                    line for line in stderr_text.split("\n") if line.strip()
                ]
                has_real_error = any(
                    "error" in line.lower()
                    or "failed" in line.lower()
                    or "exception" in line.lower()
                    for line in stderr_lines
                )

                # 检查输出中是否包含成功下载的标记
                download_success = (
                    "Chromium" in stdout_text and "downloaded to" in stdout_text
                )

                if download_success and not has_real_error:
                    # 浏览器实际下载成功，只是有弃用警告
                    logger.info(
                        f"浏览器安装成功（忽略非关键警告）\n{full_output}"
                    )
                else:
                    error_msg = (
                        f"浏览器安装失败 (返回码: {process.returncode})\n"
                        f"完整输出:\n{full_output}\n\n"
                        f"请尝试手动安装:\n"
                        f"  1. 运行: pip install --upgrade playwright\n"
                        f"  2. 运行: PLAYWRIGHT_BROWSERS_PATH={install_path} python -m playwright install chromium\n"
                        f"  3. 如果仍然失败,可能需要配置代理或检查网络连接"
                    )
                    logger.error(error_msg)
                    raise ScreenshotError(error_msg) from None
            else:
                logger.info(f"浏览器安装成功\n{full_output}")

            return install_path

        except asyncio.TimeoutError:
            # 超时时终止进程
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            raise

    async def _ensure_browser_installed(self):
        """确保Playwright浏览器已安装（优化版本）

        改进点：
        1. 使用持久化记录，避免重复检查
        2. 使用安装锁，防止并发安装
        3. 完全异步化，避免阻塞
        4. 使用安全路径，避免被清理

        Raises:
            ScreenshotError: 浏览器安装失败时抛出
        """
        import asyncio

        # 检查当前实例是否已检查过
        if hasattr(self, "_playwright_browser_checked"):
            return

        # 加载持久化的安装状态
        install_status = self._load_install_status()

        if install_status.get("installed", False):
            logger.info(f"浏览器已安装（从持久化记录）: {install_status.get('install_path', '未知路径')}")
            self._playwright_browser_checked = True
            return

        # 先检查 playwright 是否已安装
        try:
            import importlib.util
            if importlib.util.find_spec("playwright"):
                logger.debug("Playwright 已安装")
            else:
                raise ImportError()
        except ImportError:
            error_msg = (
                "Playwright 未安装！\n"
                "请运行以下命令安装:\n"
                "  pip install playwright\n"
                "然后运行:\n"
                "  playwright install chromium"
            )
            logger.error(error_msg)
            raise ScreenshotError(error_msg) from None

        # 获取安装锁，防止并发安装
        async with WebAnalyzer._browser_install_lock:
            # 双重检查：可能在等待锁的过程中已被其他实例安装
            install_status = self._load_install_status()
            if install_status.get("installed", False):
                logger.info(f"浏览器已在其他实例中安装: {install_status.get('install_path', '未知路径')}")
                self._playwright_browser_checked = True
                return

            # 检查是否正在安装
            if WebAnalyzer._is_installing:
                logger.info("浏览器正在其他实例中安装，等待完成...")
                # 等待安装完成（最多等待5分钟）
                for _ in range(300):
                    await asyncio.sleep(1)
                    install_status = self._load_install_status()
                    if install_status.get("installed", False):
                        logger.info("浏览器安装完成")
                        self._playwright_browser_checked = True
                        return
                # 超时
                error_msg = "等待浏览器安装超时"
                logger.error(error_msg)
                raise ScreenshotError(error_msg) from None

            # 标记开始安装
            WebAnalyzer._is_installing = True
            logger.info("正在检查浏览器...")

            try:
                # 异步检查浏览器是否已安装
                installed, browser_info = await self._check_browser_installed_async()

                if installed:
                    logger.info(f"浏览器已安装: {browser_info}")
                    # 保存安装状态
                    self._save_install_status({
                        "installed": True,
                        "install_path": browser_info,
                        "install_time": time.time(),
                        "browser_type": "chromium"
                    })
                    self._playwright_browser_checked = True
                    return

                # 浏览器未安装，开始安装
                logger.info("浏览器未安装，开始自动安装...")
                install_path = await self._install_browser_async()

                # 保存安装状态
                self._save_install_status({
                    "installed": True,
                    "install_path": install_path,
                    "install_time": time.time(),
                    "browser_type": "chromium"
                })

                logger.info(f"浏览器安装成功: {install_path}")

            except Exception as e:
                logger.error(f"浏览器安装失败: {e}")
                # 清理安装状态
                install_status = self._load_install_status()
                if install_status.get("installed", False):
                    # 如果之前的安装成功，不需要清理
                    pass
                else:
                    # 安装失败，清理状态
                    self._save_install_status({"installed": False})
                raise
            finally:
                # 清除安装标志
                WebAnalyzer._is_installing = False

        # 标记已检查浏览器
        self._playwright_browser_checked = True

    async def _get_or_create_browser(self) -> tuple:
        """从池中获取或创建新的浏览器实例

        Returns:
            tuple: (browser实例, playwright实例)
            playwright_instance为None表示从池中获取的浏览器
        """
        browser = await self._try_get_browser_from_pool()

        if browser:
            return browser, None

        # 创建新的浏览器实例
        return await self._create_new_browser()

    async def _try_get_browser_from_pool(self):
        """尝试从浏览器实例池获取有效的浏览器实例

        Returns:
            有效的浏览器实例，如果没有可用实例则返回None
        """

        async with WebAnalyzer._browser_lock:
            while WebAnalyzer._browser_pool:
                candidate_browser = WebAnalyzer._browser_pool.pop(0)
                try:
                    if candidate_browser.is_connected():
                        logger.debug("从浏览器实例池获取有效浏览器实例")
                        return candidate_browser
                    else:
                        logger.warning("跳过已断开连接的浏览器实例")
                        await candidate_browser.close()
                except Exception as e:
                    logger.error(f"检查浏览器实例连接状态失败: {e}, 将跳过该实例")
                    try:
                        await candidate_browser.close()
                    except Exception:
                        pass

        return None

    async def _create_new_browser(self) -> tuple:
        """创建新的浏览器实例

        Returns:
            tuple: (browser实例, playwright实例)
        """
        from playwright.async_api import async_playwright

        logger.debug("创建新的浏览器实例")
        playwright_instance = await async_playwright().start()

        browser = await playwright_instance.chromium.launch(
            headless=True,
            timeout=20000,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        return browser, playwright_instance

    async def _perform_screenshot(
        self,
        browser,
        url: str,
        width: int,
        height: int,
        quality: int,
        full_page: bool,
        wait_time: int,
        format: str,
    ) -> bytes:
        """执行实际的截图操作

        Args:
            browser: 浏览器实例
            url: 目标URL
            width: 视口宽度
            height: 视口高度
            quality: 截图质量
            full_page: 是否全页截图
            wait_time: 等待时间（毫秒）
            format: 截图格式

        Returns:
            截图的二进制数据
        """
        # 创建新页面
        page = await browser.new_page(
            viewport={"width": width, "height": height},
            user_agent=self.user_agent,
        )

        try:
            # 导航到目标URL
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # 等待页面加载完成
            await page.wait_for_timeout(wait_time)

            # 构建截图参数
            screenshot_params = {
                "full_page": full_page,
                "type": format,
            }

            # quality 参数只适用于 jpeg 格式
            if format.lower() == "jpeg":
                screenshot_params["quality"] = quality

            # 捕获截图
            screenshot_bytes = await page.screenshot(**screenshot_params)

            logger.info("截图成功")
            return screenshot_bytes

        finally:
            await page.close()

    async def _handle_browser_after_use(self, browser, playwright_instance):
        """处理使用后的浏览器实例

        Args:
            browser: 浏览器实例
            playwright_instance: playwright实例（如果为None表示从池中获取的浏览器）
        """
        if playwright_instance is None:
            # 从池中获取的浏览器实例，放回池中
            async with WebAnalyzer._browser_lock:
                WebAnalyzer._browser_last_used[id(browser)] = time.time()
                WebAnalyzer._browser_pool.append(browser)
                logger.debug(
                    f"浏览器实例已放回池中，当前池大小: {len(WebAnalyzer._browser_pool)}"
                )
        else:
            # 新创建的浏览器实例，保存到self.browser
            self.browser = browser

    async def _handle_screenshot_error(
        self,
        browser,
        playwright_instance,
        screenshot_error: Exception,
        url: str,
        width: int,
        height: int,
        quality: int,
        full_page: bool,
        wait_time: int,
        format: str,
    ) -> bytes:
        """处理截图过程中的错误

        Args:
            browser: 发生错误的浏览器实例
            playwright_instance: playwright实例
            screenshot_error: 截图错误
            url: 目标URL
            width: 视口宽度
            height: 视口高度
            quality: 截图质量
            full_page: 是否全页截图
            wait_time: 等待时间
            format: 截图格式

        Returns:
            截图的二进制数据

        Raises:
            Exception: 如果错误处理失败，则重新抛出异常
        """
        if playwright_instance is not None:
            # 新创建的浏览器实例出错，直接抛出异常
            raise screenshot_error

        # 从池中获取的浏览器实例无效，尝试创建新实例
        logger.error(f"从池中获取的浏览器实例无效，重新创建浏览器实例: {screenshot_error}")

        try:
            await browser.close()
        except Exception:
            pass

        # 创建新的浏览器实例并重试
        from playwright.async_api import async_playwright

        new_playwright_instance = await async_playwright().start()
        new_browser = await new_playwright_instance.chromium.launch(
            headless=True,
            timeout=20000,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        try:
            # 使用新浏览器实例重试截图
            screenshot_bytes = await self._perform_screenshot(
                browser=new_browser,
                url=url,
                width=width,
                height=height,
                quality=quality,
                full_page=full_page,
                wait_time=wait_time,
                format=format,
            )

            logger.info("使用新浏览器实例截图成功")

            # 保存新创建的浏览器实例
            self.browser = new_browser

            return screenshot_bytes

        finally:
            await new_playwright_instance.stop()

    def extract_specific_content(
        self, html: str, url: str, extract_types: list[str]
    ) -> dict:
        """从HTML中提取特定类型的内容

        根据指定的提取类型，从HTML文档中提取结构化数据：
        - 标题（title）
        - 正文内容（content）
        - 图片链接（images）
        - 超链接（links）
        - 表格（tables）
        - 列表（lists）
        - 代码块（code）
        - 元信息（meta）
        - 视频链接（videos）
        - 音频链接（audios）
        - 引用块（quotes）
        - 标题列表（headings）
        - 段落（paragraphs）
        - 按钮（buttons）
        - 表单（forms）

        Args:
            html: 网页的HTML文本内容
            url: 网页的原始URL，用于处理相对路径
            extract_types: 要提取的内容类型列表

        Returns:
            包含提取内容的字典，键为提取类型，值为对应内容
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            extracted_content = {}

            # 提取标题
            if "title" in extract_types:
                title = soup.find("title")
                extracted_content["title"] = (
                    title.get_text().strip() if title else "无标题"
                )

            # 提取正文内容
            if "content" in extract_types:
                content_selectors = [
                    "article",  # 语义化文章标签
                    "main",  # 语义化主内容标签
                    ".article-content",  # 常见文章内容类名
                    ".post-content",  # 常见博客内容类名
                    ".content",  # 通用内容类名
                    "body",  # 兜底方案
                ]

                content_text = ""
                for selector in content_selectors:
                    element = soup.select_one(selector)
                    if element:
                        # 移除脚本和样式标签，避免干扰内容提取
                        for script in element.find_all(["script", "style"]):
                            script.decompose()
                        text = element.get_text(separator="\n", strip=True)
                        if len(text) > len(content_text):
                            content_text = text

                # 限制内容长度
                if len(content_text) > self.max_content_length:
                    content_text = content_text[: self.max_content_length] + "..."

                extracted_content["content"] = content_text

            # 提取图片链接，最多提取10张
            if "images" in extract_types:
                images = []
                for img in soup.find_all("img"):
                    src = img.get("src")
                    if src:
                        # 处理相对路径，转换为绝对URL
                        full_url = urljoin(url, src)
                        alt_text = img.get("alt", "").strip()
                        images.append({"url": full_url, "alt": alt_text})
                extracted_content["images"] = images[:10]  # 限制最多10张图片

            # 提取超链接，最多提取20个
            if "links" in extract_types:
                links = []
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if href and not href.startswith("#"):  # 跳过锚点链接
                        full_url = urljoin(url, href)
                        text = a.get_text().strip() or full_url  # 链接文本为空时使用URL
                        links.append({"text": text, "url": full_url})
                extracted_content["links"] = links[:20]  # 限制最多20个链接

            # 提取表格，最多提取5个
            if "tables" in extract_types:
                tables = []
                for table in soup.find_all("table"):
                    table_data = []
                    # 提取表头
                    headers = []
                    thead = table.find("thead")
                    if thead:
                        for th in thead.find_all("th"):
                            headers.append(th.get_text().strip())

                    # 提取表体
                    tbody = table.find("tbody") or table  # 没有tbody时使用table本身
                    for row in tbody.find_all("tr"):
                        row_data = []
                        for cell in row.find_all(["td", "th"]):  # 同时处理td和th
                            row_data.append(cell.get_text().strip())
                        if row_data:  # 跳过空行
                            table_data.append(row_data)

                    if table_data:  # 只添加有数据的表格
                        tables.append({"headers": headers, "rows": table_data})
                extracted_content["tables"] = tables[:5]  # 限制最多5个表格

            # 提取列表，最多提取10个
            if "lists" in extract_types:
                lists = []
                # 提取无序列表
                for ul in soup.find_all("ul"):
                    list_items = []
                    for li in ul.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:  # 只添加有内容的列表
                        lists.append(
                            {
                                "type": "ul",  # 列表类型：无序列表
                                "items": list_items[:20],  # 每个列表最多20项
                            }
                        )

                # 提取有序列表
                for ol in soup.find_all("ol"):
                    list_items = []
                    for li in ol.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:  # 只添加有内容的列表
                        lists.append(
                            {
                                "type": "ol",  # 列表类型：有序列表
                                "items": list_items[:20],  # 每个列表最多20项
                            }
                        )
                extracted_content["lists"] = lists[:10]  # 限制最多10个列表

            # 提取代码块，最多提取5个
            if "code" in extract_types:
                code_blocks = []
                for code in soup.find_all(["pre", "code"]):  # 同时处理pre和code标签
                    code_text = code.get_text().strip()
                    if code_text and len(code_text) > 10:  # 跳过短代码块
                        # 获取语言类型
                        language = ""
                        if code.parent.name == "pre":
                            # 检查pre标签是否有语言类名
                            for cls in code.parent.get("class", []):
                                if cls.startswith("language-"):
                                    language = cls[9:]
                                    break
                                if cls.startswith("lang-"):
                                    language = cls[5:]
                                    break
                        elif code.get("class"):
                            # 检查code标签是否有语言类名
                            for cls in code.get("class", []):
                                if cls.startswith("language-"):
                                    language = cls[9:]
                                    break
                                if cls.startswith("lang-"):
                                    language = cls[5:]
                                    break

                        # 限制单个代码块长度
                        truncated_code = (
                            code_text[:1000] + "..."
                            if len(code_text) > 1000
                            else code_text
                        )
                        code_blocks.append({"code": truncated_code, "language": language})
                extracted_content["code_blocks"] = code_blocks[:5]  # 限制最多5个代码块

            # 提取元信息
            if "meta" in extract_types:
                meta_info = {}
                # 提取描述
                description = soup.find("meta", attrs={"name": "description"})
                if description:
                    meta_info["description"] = description.get("content", "").strip()

                # 提取关键词
                keywords = soup.find("meta", attrs={"name": "keywords"})
                if keywords:
                    meta_info["keywords"] = keywords.get("content", "").strip()

                # 提取作者
                author = soup.find("meta", attrs={"name": "author"})
                if author:
                    meta_info["author"] = author.get("content", "").strip()

                # 提取发布时间
                publish_time = soup.find(
                    "meta", attrs={"property": "article:published_time"}
                )
                if not publish_time:
                    publish_time = soup.find("meta", attrs={"name": "publish_date"})
                if publish_time:
                    meta_info["publish_time"] = publish_time.get("content", "").strip()

                # 提取网站名称
                site_name = soup.find("meta", attrs={"property": "og:site_name"})
                if site_name:
                    meta_info["site_name"] = site_name.get("content", "").strip()

                # 提取og:title
                og_title = soup.find("meta", attrs={"property": "og:title"})
                if og_title:
                    meta_info["og_title"] = og_title.get("content", "").strip()

                # 提取og:description
                og_description = soup.find("meta", attrs={"property": "og:description"})
                if og_description:
                    meta_info["og_description"] = og_description.get("content", "").strip()

                extracted_content["meta"] = meta_info

            # 提取视频链接，最多提取5个
            if "videos" in extract_types:
                videos = []
                # 查找video标签
                for video in soup.find_all("video"):
                    src = video.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        videos.append({"url": full_url, "type": "video"})
                # 查找iframe标签（可能包含视频）
                for iframe in soup.find_all("iframe"):
                    src = iframe.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        videos.append({"url": full_url, "type": "iframe"})
                extracted_content["videos"] = videos[:5]  # 限制最多5个视频

            # 提取音频链接，最多提取5个
            if "audios" in extract_types:
                audios = []
                # 查找audio标签
                for audio in soup.find_all("audio"):
                    src = audio.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        audios.append(full_url)
                # 查找embed标签（可能包含音频）
                for embed in soup.find_all("embed"):
                    src = embed.get("src")
                    if src and (src.endswith(".mp3") or src.endswith(".wav") or src.endswith(".ogg")):
                        full_url = urljoin(url, src)
                        audios.append(full_url)
                extracted_content["audios"] = audios[:5]  # 限制最多5个音频

            # 提取引用块，最多提取10个
            if "quotes" in extract_types:
                quotes = []
                # 查找blockquote标签
                for blockquote in soup.find_all("blockquote"):
                    quote_text = blockquote.get_text().strip()
                    if quote_text:
                        # 查找引用的作者
                        cite = blockquote.find("cite")
                        author = cite.get_text().strip() if cite else ""
                        quotes.append({"text": quote_text, "author": author})
                extracted_content["quotes"] = quotes[:10]  # 限制最多10个引用块

            # 提取标题列表
            if "headings" in extract_types:
                headings = []
                # 查找所有h1-h6标签
                for level in range(1, 7):
                    for heading in soup.find_all(f"h{level}"):
                        headings.append({
                            "level": level,
                            "text": heading.get_text().strip(),
                            "id": heading.get("id", "")
                        })
                extracted_content["headings"] = headings

            # 提取段落，最多提取20个
            if "paragraphs" in extract_types:
                paragraphs = []
                for p in soup.find_all("p"):
                    text = p.get_text().strip()
                    if text:
                        paragraphs.append(text)
                extracted_content["paragraphs"] = paragraphs[:20]  # 限制最多20个段落

            # 提取按钮，最多提取10个
            if "buttons" in extract_types:
                buttons = []
                for button in soup.find_all("button"):
                    text = button.get_text().strip()
                    onclick = button.get("onclick", "").strip()
                    buttons.append({
                        "text": text,
                        "onclick": onclick,
                        "type": button.get("type", "button")
                    })
                extracted_content["buttons"] = buttons[:10]  # 限制最多10个按钮

            # 提取表单，最多提取5个
            if "forms" in extract_types:
                forms = []
                for form in soup.find_all("form"):
                    form_data = {
                        "action": form.get("action", ""),
                        "method": form.get("method", "get"),
                        "inputs": [],
                        "buttons": []
                    }
                    # 提取表单输入
                    for input_elem in form.find_all("input"):
                        form_data["inputs"].append({
                            "type": input_elem.get("type", "text"),
                            "name": input_elem.get("name", ""),
                            "value": input_elem.get("value", "")
                        })
                    # 提取表单文本域
                    for textarea in form.find_all("textarea"):
                        form_data["inputs"].append({
                            "type": "textarea",
                            "name": textarea.get("name", ""),
                            "value": textarea.get_text().strip()
                        })
                    # 提取表单选择
                    for select in form.find_all("select"):
                        options = []
                        for option in select.find_all("option"):
                            options.append({
                                "value": option.get("value", ""),
                                "text": option.get_text().strip(),
                                "selected": bool(option.get("selected"))
                            })
                        form_data["inputs"].append({
                            "type": "select",
                            "name": select.get("name", ""),
                            "options": options
                        })
                    # 提取表单按钮
                    for button in form.find_all("button"):
                        form_data["buttons"].append({
                            "text": button.get_text().strip(),
                            "type": button.get("type", "submit")
                        })
                    forms.append(form_data)
                extracted_content["forms"] = forms[:5]  # 限制最多5个表单

            return extracted_content
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            raise ContentExtractionError(f"提取特定内容失败: {str(e)}") from e
