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

import re
from typing import List, Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

from astrbot.api import logger


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

    def __init__(
        self,
        max_content_length: int = 10000,
        timeout: int = 30,
        user_agent: str = None,
        proxy: str = None,
        retry_count: int = 3,
        retry_delay: int = 2,
    ):
        """初始化网页分析器

        Args:
            max_content_length: 提取的最大内容长度，防止内容过大
            timeout: HTTP请求超时时间，单位为秒
            user_agent: 请求时使用的User-Agent头
            proxy: HTTP代理设置，格式为 http://host:port 或 https://host:port
            retry_count: 请求失败时的重试次数
            retry_delay: 重试间隔时间，单位为秒
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
        - 浏览器实例正确关闭（如果使用了）
        - 资源泄漏的防止

        Args:
            exc_type: 异常类型（如果有）
            exc_val: 异常值（如果有）
            exc_tb: 异常回溯（如果有）
        """
        if self.client:
            await self.client.aclose()
        if self.browser:
            await self.browser.close()

    def extract_urls(self, text: str) -> List[str]:
        """从文本中提取所有HTTP/HTTPS URL链接

        使用正则表达式匹配文本中的URL，支持：
        - HTTP和HTTPS协议
        - 各种常见的URL格式
        - 排除中文等非ASCII字符作为URL的一部分

        Args:
            text: 要从中提取URL的文本内容

        Returns:
            包含所有提取到的URL的列表
        """
        # 匹配常见的URL格式，排除中文等非ASCII字符
        url_pattern = r"https?://[^\s\u4e00-\u9fff]+"
        urls = re.findall(url_pattern, text)
        return urls

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

        Args:
            url: 要规范化的URL字符串

        Returns:
            规范化后的URL字符串
        """
        try:
            parsed = urlparse(url)
            # 转换为小写
            normalized = parsed._replace(
                scheme=parsed.scheme.lower(),
                netloc=parsed.netloc.lower(),
                path=parsed.path.rstrip('/')  # 移除尾部斜杠
            )
            return normalized.geturl()
        except Exception:
            return url

    async def fetch_webpage(self, url: str) -> Optional[str]:
        """异步抓取网页HTML内容

        使用异步HTTP客户端抓取网页，支持：
        - 自定义User-Agent
        - 自动跟随重定向
        - 配置的代理设置
        - 智能重试机制（失败后自动重试）

        Args:
            url: 要抓取的网页URL

        Returns:
            网页的HTML文本内容，如果抓取失败则返回None
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Sec-GPC": "1"
        }

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
                    import asyncio

                    await asyncio.sleep(self.retry_delay)
                else:
                    # 重试次数用完，记录错误并返回None
                    logger.error(
                        f"抓取网页失败: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    return None

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
            包含标题、内容和URL的字典，如果解析失败则返回None
        """
        try:
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
            return None
    
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
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            提取的主要内容文本
        """
        # 尝试提取文章内容（优先选择article、main等语义化标签）
        content_selectors = [
            "article",  # 语义化文章标签
            "main",  # 语义化主内容标签
            ".article-content",  # 常见文章内容类名
            ".post-content",  # 常见博客内容类名
            ".content",  # 通用内容类名
            "body",  # 兜底：使用整个body
        ]

        content_text = ""
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                # 清理内容，移除脚本和样式标签
                cleaned_element = self._clean_content_element(element)
                text = cleaned_element.get_text(separator="\n", strip=True)
                if len(text) > len(content_text):
                    content_text = text

        # 如果没找到合适的内容，使用body作为最后的兜底方案
        if not content_text:
            body = soup.find("body")
            if body:
                cleaned_body = self._clean_content_element(body)
                content_text = cleaned_body.get_text(separator="\n", strip=True)
        
        return content_text
    
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
        """使用Playwright捕获网页截图

        自动处理浏览器的安装和配置，支持：
        - 自定义分辨率和质量
        - 全屏截图或可视区域截图
        - 自定义等待时间，确保页面加载完成
        - 支持JPEG和PNG格式

        Args:
            url: 要截图的网页URL
            quality: 截图质量，范围1-100
            width: 截图宽度（像素）
            height: 截图高度（像素）
            full_page: 是否截取整个页面，False仅截取可视区域
            wait_time: 页面加载后等待的时间（毫秒），确保动态内容加载
            format: 截图格式，支持"jpeg"和"png"

        Returns:
            截图的二进制数据，如果失败则返回None
        """
        try:
            from playwright.async_api import async_playwright
            import sys
            import subprocess
            import os

            # 只在第一次执行时检查浏览器安装
            if not hasattr(self, '_playwright_browser_checked'):
                logger.info("正在检查浏览器...")
                # 检查浏览器是否已安装
                browser_path = os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright', 'chromium')
                if os.path.exists(browser_path):
                    logger.info("浏览器已安装，跳过安装步骤")
                else:
                    # 安装浏览器
                    logger.info("正在安装浏览器...")
                    result = subprocess.run(
                        [sys.executable, "-m", "playwright", "install", "chromium"],
                        capture_output=True,
                        text=True,
                    )

                    if result.returncode != 0:
                        logger.error(f"浏览器安装失败: {result.stderr}")
                        return None
                    logger.info("浏览器安装成功")
            
            # 标记已检查浏览器
            self._playwright_browser_checked = True

            logger.info("正在尝试截图...")

            # 尝试启动playwright并截图
            async with async_playwright() as p:
                # 启动浏览器（无头模式，不显示GUI）
                browser = await p.chromium.launch(
                    headless=True,
                    # 增加浏览器启动超时时间到60秒
                    timeout=20000,
                    # 添加额外的启动参数，提高兼容性和稳定性
                    args=[
                        "--no-sandbox",  # 禁用沙箱，提高兼容性
                        "--disable-setuid-sandbox",  # 禁用setuid沙箱
                        "--disable-dev-shm-usage",  # 禁用/dev/shm使用
                        "--disable-gpu",  # 禁用GPU加速
                        # 移除固定端口，让playwright自动分配可用端口
                    ],
                )

                # 创建新的页面，设置视口和User-Agent
                page = await browser.new_page(
                    viewport={"width": width, "height": height},
                    user_agent=self.user_agent,
                )

                # 导航到目标URL，使用更宽松的等待条件
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # 等待指定时间，确保页面完全加载（尤其是动态内容）
                await page.wait_for_timeout(wait_time)

                # 捕获截图
                screenshot_bytes = await page.screenshot(
                    full_page=full_page,  # 是否截取整个页面
                    quality=quality,  # 截图质量
                    type=format,  # 截图格式
                )

                await browser.close()

                logger.info("截图成功")
                return screenshot_bytes
        except Exception as e:
            logger.error(f"捕获网页截图失败: {url}, 错误: {e}")
            return None

    def extract_specific_content(
        self, html: str, url: str, extract_types: List[str]
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
                        images.append(full_url)
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
                        # 限制单个代码块长度
                        truncated_code = (
                            code_text[:1000] + "..."
                            if len(code_text) > 1000
                            else code_text
                        )
                        code_blocks.append(truncated_code)
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

                extracted_content["meta"] = meta_info

            return extracted_content
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            return {}
