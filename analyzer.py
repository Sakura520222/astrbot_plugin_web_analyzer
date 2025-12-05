"""
网页分析器模块
负责网页内容的抓取、提取和分析
"""

import re
from typing import List, Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

from astrbot.api import logger


class WebAnalyzer:
    """网页分析器类"""

    def __init__(
        self,
        max_content_length: int = 10000,
        timeout: int = 30,
        user_agent: str = None,
        proxy: str = None,
        retry_count: int = 3,
        retry_delay: int = 2,
    ):
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

    async def __aenter__(self):
        """异步上下文管理器入口"""
        # 配置客户端参数
        client_params = {"timeout": self.timeout}

        # 添加代理配置（如果有）
        if self.proxy:
            client_params["proxies"] = {"http://": self.proxy, "https://": self.proxy}

        self.client = httpx.AsyncClient(**client_params)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.client:
            await self.client.aclose()
        if self.browser:
            await self.browser.close()

    def extract_urls(self, text: str) -> List[str]:
        """从文本中提取URL链接"""
        # 匹配常见的URL格式
        url_pattern = r"https?://[^\s\u4e00-\u9fff]+"
        urls = re.findall(url_pattern, text)
        return urls

    def is_valid_url(self, url: str) -> bool:
        """验证URL是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def fetch_webpage(self, url: str) -> Optional[str]:
        """抓取网页内容"""
        headers = {"User-Agent": self.user_agent}

        # 实现重试机制
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
                    # 还有重试次数，等待后重试
                    logger.warning(
                        f"抓取网页失败，将重试: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    import asyncio

                    await asyncio.sleep(self.retry_delay)
                else:
                    # 重试次数用完
                    logger.error(
                        f"抓取网页失败: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    return None

    def extract_content(self, html: str, url: str) -> dict:
        """从HTML中提取主要内容"""
        try:
            soup = BeautifulSoup(html, "lxml")

            # 提取标题
            title = soup.find("title")
            title_text = title.get_text().strip() if title else "无标题"

            # 尝试提取文章内容（优先选择article、main等语义化标签）
            content_selectors = [
                "article",
                "main",
                ".article-content",
                ".post-content",
                ".content",
                "body",
            ]

            content_text = ""
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    # 移除脚本和样式标签
                    for script in element(["script", "style"]):
                        script.decompose()

                    text = element.get_text(separator="\n", strip=True)
                    if len(text) > len(content_text):
                        content_text = text

            # 如果没找到合适的内容，使用body
            if not content_text:
                body = soup.find("body")
                if body:
                    for script in body(["script", "style"]):
                        script.decompose()
                    content_text = body.get_text(separator="\n", strip=True)

            # 限制内容长度
            if len(content_text) > self.max_content_length:
                content_text = content_text[: self.max_content_length] + "..."

            return {"title": title_text, "content": content_text, "url": url}
        except Exception as e:
            logger.error(f"解析网页内容失败: {e}")
            return None

    async def capture_screenshot(
        self,
        url: str,
        quality: int = 80,
        width: int = 1280,
        height: int = 720,
        full_page: bool = False,
        wait_time: int = 2000,
        format: str = "jpeg",
    ) -> Optional[bytes]:
        """捕获网页截图"""
        try:
            from playwright.async_api import async_playwright
            import sys
            import subprocess

            # 首先尝试安装浏览器（无论是否已安装，playwright install都会检查并更新）
            logger.info("正在检查并安装浏览器...")
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"浏览器安装失败: {result.stderr}")
                return None

            logger.info("浏览器安装成功，正在尝试截图...")

            # 尝试启动playwright并截图
            browser = None
            async with async_playwright() as p:
                # 启动浏览器（无头模式）
                browser = await p.chromium.launch(
                    headless=True,
                    # 添加额外的启动参数，提高兼容性
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--remote-debugging-port=9222",
                    ],
                )
                page = await browser.new_page(
                    viewport={"width": width, "height": height},
                    user_agent=self.user_agent,
                )

                # 导航到目标URL，使用更宽松的等待条件
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # 等待指定时间，确保页面完全加载
                await page.wait_for_timeout(wait_time)

                # 捕获截图
                screenshot_bytes = await page.screenshot(
                    full_page=full_page, quality=quality, type=format
                )

                await browser.close()

                logger.info("截图成功")
                return screenshot_bytes
        except Exception as e:
            logger.error(f"捕获网页截图失败: {url}, 错误: {e}")
            if browser:
                await browser.close()
            return None

    def extract_specific_content(
        self, html: str, url: str, extract_types: List[str]
    ) -> dict:
        """提取特定类型的内容"""
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
                    "article",
                    "main",
                    ".article-content",
                    ".post-content",
                    ".content",
                    "body",
                ]

                content_text = ""
                for selector in content_selectors:
                    element = soup.select_one(selector)
                    if element:
                        for script in element(["script", "style"]):
                            script.decompose()
                        text = element.get_text(separator="\n", strip=True)
                        if len(text) > len(content_text):
                            content_text = text

                if len(content_text) > self.max_content_length:
                    content_text = content_text[: self.max_content_length] + "..."

                extracted_content["content"] = content_text

            # 提取图片链接
            if "images" in extract_types:
                images = []
                for img in soup.find_all("img"):
                    src = img.get("src")
                    if src:
                        # 处理相对路径
                        full_url = urljoin(url, src)
                        images.append(full_url)
                extracted_content["images"] = images[:10]  # 最多提取10张图片

            # 提取链接
            if "links" in extract_types:
                links = []
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if href and not href.startswith("#"):
                        full_url = urljoin(url, href)
                        links.append(
                            {"text": a.get_text().strip() or full_url, "url": full_url}
                        )
                extracted_content["links"] = links[:20]  # 最多提取20个链接

            # 提取表格
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
                    tbody = table.find("tbody") or table
                    for row in tbody.find_all("tr"):
                        row_data = []
                        for cell in row.find_all(["td", "th"]):
                            row_data.append(cell.get_text().strip())
                        if row_data:
                            table_data.append(row_data)

                    if table_data:
                        tables.append({"headers": headers, "rows": table_data})
                extracted_content["tables"] = tables[:5]  # 最多提取5个表格

            # 提取列表
            if "lists" in extract_types:
                lists = []
                # 提取无序列表
                for ul in soup.find_all("ul"):
                    list_items = []
                    for li in ul.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:
                        lists.append(
                            {
                                "type": "ul",
                                "items": list_items[:20],  # 每个列表最多提取20项
                            }
                        )

                # 提取有序列表
                for ol in soup.find_all("ol"):
                    list_items = []
                    for li in ol.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:
                        lists.append(
                            {
                                "type": "ol",
                                "items": list_items[:20],  # 每个列表最多提取20项
                            }
                        )
                extracted_content["lists"] = lists[:10]  # 最多提取10个列表

            # 提取代码块
            if "code" in extract_types:
                code_blocks = []
                for code in soup.find_all(["pre", "code"]):
                    code_text = code.get_text().strip()
                    if code_text and len(code_text) > 10:
                        code_blocks.append(
                            code_text[:1000] + "..."
                            if len(code_text) > 1000
                            else code_text
                        )
                extracted_content["code_blocks"] = code_blocks[:5]  # 最多提取5个代码块

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

                extracted_content["meta"] = meta_info

            return extracted_content
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            return {}
