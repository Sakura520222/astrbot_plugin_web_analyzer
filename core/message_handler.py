# -*- coding: utf-8 -*-
"""
消息处理模块

负责处理单个和批量 URL 分析、发送分析结果等。
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# 确保父目录在 Python 路径中
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Node, Nodes, Plain

from analyzer import WebAnalyzer
from cache import CacheManager
from core.constants import ErrorType
from core.error_handler import ErrorHandler


class MessageHandler:
    """消息处理器类"""

    def __init__(
        self,
        analyzer: WebAnalyzer,
        cache_manager: CacheManager,
        enable_cache: bool = True,
        enable_screenshot: bool = True,
        send_content_type: str = "both",
        screenshot_format: str = "jpeg",
    ):
        """初始化消息处理器

        Args:
            analyzer: WebAnalyzer 实例
            cache_manager: CacheManager 实例
            enable_cache: 是否启用缓存
            enable_screenshot: 是否启用截图
            send_content_type: 发送内容类型
            screenshot_format: 截图格式
        """
        self.analyzer = analyzer
        self.cache_manager = cache_manager
        self.enable_cache = enable_cache
        self.enable_screenshot = enable_screenshot
        self.send_content_type = send_content_type
        self.screenshot_format = screenshot_format

    def check_cache(self, url: str) -> dict | None:
        """检查指定 URL 的缓存是否存在且有效

        Args:
            url: 网页 URL

        Returns:
            缓存结果，如果不存在或无效则返回 None
        """
        if not self.enable_cache:
            return None

        normalized_url = self.analyzer.normalize_url(url)
        return self.cache_manager.get(normalized_url)

    def update_cache(self, url: str, result: dict, content: str = None):
        """更新指定 URL 的缓存

        Args:
            url: 网页 URL
            result: 分析结果
            content: 网页内容（可选，用于内容哈希缓存）
        """
        if not self.enable_cache:
            return

        normalized_url = self.analyzer.normalize_url(url)

        if content:
            self.cache_manager.set_with_content_hash(normalized_url, result, content)
        else:
            self.cache_manager.set(normalized_url, result)

    async def process_single_url(
        self,
        event: AstrMessageEvent,
        url: str,
        analyzer: WebAnalyzer,
        llm_analyzer=None,
        enable_translation=False,
        enable_specific_extraction=False,
        extract_types=None,
        result_formatter=None,
    ) -> dict:
        """处理单个网页 URL，生成完整的分析结果

        Args:
            event: 消息事件对象
            url: 网页 URL
            analyzer: WebAnalyzer 实例
            llm_analyzer: LLMAnalyzer 实例（可选）
            enable_translation: 是否启用翻译
            enable_specific_extraction: 是否启用特定内容提取
            extract_types: 提取类型列表
            result_formatter: ResultFormatter 实例（可选）

        Returns:
            分析结果字典
        """
        try:
            # 1. 检查缓存
            cached_result = self.check_cache(url)
            if cached_result:
                logger.info(f"使用 URL 缓存结果: {url}")
                return cached_result

            # 使用异步上下文管理器确保所有操作都在同一个 HTTP 客户端中完成
            async with analyzer:
                # 2. 抓取网页内容
                html = await analyzer.fetch_webpage(url)
                if not html:
                    error_msg = ErrorHandler.handle_error(
                        ErrorType.NETWORK_ERROR, Exception("无法获取网页内容"), url
                    )
                    return {"url": url, "result": error_msg, "screenshot": None}

                # 3. 提取结构化内容
                content_data = analyzer.extract_content(html, url)
                if not content_data:
                    error_msg = ErrorHandler.handle_error(
                        ErrorType.PARSING_ERROR, Exception("无法解析网页内容"), url
                    )
                    return {"url": url, "result": error_msg, "screenshot": None}

                # 4. 调用 LLM 进行分析
                analysis_result = await self._analyze_content(
                    event, content_data, llm_analyzer, enable_translation
                )

                # 5. 提取特定内容
                if enable_specific_extraction and extract_types:
                    analysis_result = await self._extract_and_add_specific_content(
                        analysis_result, html, url, extract_types
                    )

                # 6. 生成截图
                screenshot = await self._generate_screenshot(
                    analyzer, url, analysis_result
                )

                # 7. 准备结果数据
                result_data = {
                    "url": url,
                    "result": analysis_result,
                    "screenshot": screenshot,
                }

                # 8. 更新缓存
                self.update_cache(url, result_data, content_data["content"])

                return result_data
        except Exception as e:
            error_type = ErrorHandler.get_error_type(e)
            error_msg = ErrorHandler.handle_error(error_type, e, url)
            return {"url": url, "result": error_msg, "screenshot": None}

    async def _fetch_webpage_content(self, analyzer: WebAnalyzer, url: str) -> str:
        """抓取网页 HTML 内容

        Args:
            analyzer: WebAnalyzer 实例
            url: 要抓取的 URL

        Returns:
            网页 HTML 内容
        """
        try:
            # 使用异步上下文管理器确保 client 被正确初始化
            async with analyzer:
                html = await analyzer.fetch_webpage(url)
                return html
        except Exception as e:
            logger.error(f"抓取网页失败: {url}, 错误: {e}")
            return ""

    async def _extract_structured_content(
        self, analyzer: WebAnalyzer, html: str, url: str
    ) -> dict | None:
        """从 HTML 中提取结构化内容

        Args:
            analyzer: WebAnalyzer 实例
            html: 网页 HTML 内容
            url: 网页 URL

        Returns:
            包含结构化内容的字典
        """
        try:
            content_data = analyzer.extract_content(html, url)
            return content_data
        except Exception as e:
            logger.error(f"提取结构化内容失败: {url}, 错误: {e}")
            return None

    async def _analyze_content(
        self, event: AstrMessageEvent, content_data: dict, llm_analyzer, enable_translation: bool
    ) -> str:
        """调用 LLM 或基础分析方法分析内容

        Args:
            event: 消息事件对象
            content_data: 结构化内容数据
            llm_analyzer: LLMAnalyzer 实例
            enable_translation: 是否启用翻译

        Returns:
            分析结果文本
        """
        try:
            # 如果有 LLM 分析器，使用 LLM 分析
            if llm_analyzer:
                result = await llm_analyzer.analyze_with_llm(event, content_data)
                if result:
                    return result

            # 否则返回基础分析
            # 这里需要 result_formatter，如果没有则返回简单摘要
            return f"网页标题：{content_data.get('title', '无标题')}\n\n内容：{content_data.get('content', '')[:500]}..."
        except Exception as e:
            logger.error(f"分析内容失败: {content_data.get('url', '')}, 错误: {e}")
            return "分析失败"

    async def _extract_and_add_specific_content(
        self, analysis_result: str, html: str, url: str, extract_types: list
    ) -> str:
        """提取特定类型内容并添加到分析结果中

        Args:
            analysis_result: 当前的分析结果
            html: 网页 HTML 内容
            url: 网页 URL
            extract_types: 提取类型列表

        Returns:
            更新后的分析结果
        """
        try:
            specific_content = self.analyzer.extract_specific_content(
                html, url, extract_types
            )
            if not specific_content:
                return analysis_result

            # 在分析结果中添加特定内容
            specific_content_str = "\n\n**特定内容提取**\n"

            # 添加图片链接
            if "images" in specific_content and specific_content["images"]:
                specific_content_str += (
                    f"\n📷 图片链接 ({len(specific_content['images'])}):\n"
                )
                for img in specific_content["images"]:
                    img_url = img.get("url", "")
                    alt_text = img.get("alt", "")
                    if alt_text:
                        specific_content_str += f"- {img_url} (alt: {alt_text})\n"
                    else:
                        specific_content_str += f"- {img_url}\n"

            # 添加相关链接
            if "links" in specific_content and specific_content["links"]:
                specific_content_str += (
                    f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                )
                for link in specific_content["links"][:5]:
                    specific_content_str += f"- [{link['text']}]({link['url']})\n"

            return analysis_result + specific_content_str
        except Exception as e:
            logger.warning(f"特定内容提取失败: {url}, 错误: {e}")
            return analysis_result

    async def _generate_screenshot(
        self, analyzer: WebAnalyzer, url: str, analysis_result: str
    ) -> bytes | None:
        """生成网页截图

        Args:
            analyzer: WebAnalyzer 实例
            url: 网页 URL
            analysis_result: 当前的分析结果

        Returns:
            截图二进制数据
        """
        if not self.enable_screenshot or self.send_content_type == "analysis_only":
            return None

        try:
            # 这里需要传入截图参数，暂时使用默认值
            screenshot = await analyzer.capture_screenshot(url)
            return screenshot
        except Exception as e:
            logger.error(f"截图失败: {url}, 错误: {e}")
            return None

    async def send_analysis_result(self, event: AstrMessageEvent, analysis_results: list):
        """发送分析结果

        Args:
            event: 消息事件对象
            analysis_results: 分析结果列表

        Yields:
            消息结果
        """
        if not analysis_results:
            logger.info("没有分析结果，不发送消息")
            return

        # 检查是否所有结果都是错误结果
        all_errors = True
        for result in analysis_results:
            if result.get("screenshot"):
                all_errors = False
                break
            result_text = result.get("result", "")
            if not any(keyword in result_text for keyword in ["失败", "错误", "无法", "❌"]):
                all_errors = False
                break

        if all_errors:
            logger.info("所有 URL 分析失败，不发送消息")
            return

        try:
            for i, result_data in enumerate(analysis_results, 1):
                screenshot = result_data.get("screenshot")
                analysis_result = result_data.get("result")

                # 发送分析结果文本
                if self.send_content_type != "screenshot_only" and analysis_result:
                    if len(analysis_results) == 1:
                        result_text = f"网页分析结果：\n{analysis_result}"
                    else:
                        result_text = f"第{i}/{len(analysis_results)}个网页分析结果：\n{analysis_result}"
                    yield event.plain_result(result_text)

                # 发送截图
                if screenshot and self.send_content_type != "analysis_only":
                    try:
                        suffix = f".{self.screenshot_format}" if self.screenshot_format else ".jpg"
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                            temp_file.write(screenshot)
                            temp_file_path = temp_file.name

                        image_component = Image.fromFileSystem(temp_file_path)
                        yield event.chain_result([image_component])
                        logger.info("发送分析结果和截图")

                        os.unlink(temp_file_path)
                    except Exception as e:
                        logger.error(f"发送截图失败: {e}")
                        if "temp_file_path" in locals() and os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
        except Exception as e:
            logger.error(f"发送分析结果失败: {e}")
            yield event.plain_result(f"❌ 发送分析结果失败: {str(e)}")