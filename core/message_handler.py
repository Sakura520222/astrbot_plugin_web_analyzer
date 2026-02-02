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

from core.analyzer import WebAnalyzer
from core.cache import CacheManager
from core.constants import ErrorType
from core.error_handler import ErrorHandler
from core.utils import WebAnalyzerUtils


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
        merge_forward_group: bool = False,
        merge_forward_private: bool = False,
        merge_forward_include_screenshot: bool = False,
    ):
        """初始化消息处理器

        Args:
            analyzer: WebAnalyzer 实例
            cache_manager: CacheManager 实例
            enable_cache: 是否启用缓存
            enable_screenshot: 是否启用截图
            send_content_type: 发送内容类型
            screenshot_format: 截图格式
            merge_forward_group: 群聊启用合并转发
            merge_forward_private: 私聊启用合并转发
            merge_forward_include_screenshot: 合并转发包含截图
        """
        self.analyzer = analyzer
        self.cache_manager = cache_manager
        self.enable_cache = enable_cache
        self.enable_screenshot = enable_screenshot
        self.send_content_type = send_content_type
        self.screenshot_format = screenshot_format
        self.merge_forward_group = merge_forward_group
        self.merge_forward_private = merge_forward_private
        self.merge_forward_include_screenshot = merge_forward_include_screenshot

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
        cached_result = self.cache_manager.get(normalized_url)
        
        # 缓存管理器返回的是内层的 result 字典，格式为：
        # {
        #   "url": "https://...",
        #   "result": "分析结果文本",
        #   "has_screenshot": true/false,
        #   "screenshot": bytes (如果已加载到内存)
        # }
        if cached_result and isinstance(cached_result, dict):
            # 获取分析结果文本
            result_text = cached_result.get("result", "")
            if isinstance(result_text, dict):
                result_text = result_text.get("analysis", str(result_text))
            
            # 处理截图数据
            screenshot = None
            if cached_result.get("has_screenshot", False):
                # 有截图标记，尝试获取截图数据
                screenshot = cached_result.get("screenshot")
                
                # 如果内存中没有实际的截图数据（bytes），从磁盘加载
                if not isinstance(screenshot, bytes):
                    screenshot = self._load_screenshot_from_cache(normalized_url)
                    if screenshot:
                        logger.info(f"从磁盘加载缓存截图成功: {normalized_url}, 大小: {len(screenshot)} 字节")
                    else:
                        logger.warning(f"缓存标记有截图，但磁盘文件不存在: {normalized_url}")
                else:
                    logger.info(f"使用内存中的缓存截图: {normalized_url}, 大小: {len(screenshot)} 字节")
            else:
                logger.info(f"缓存中无截图标记: {normalized_url}")
            
            # 返回标准格式
            return {
                "url": url,
                "result": result_text,
                "screenshot": screenshot
            }
        
        return cached_result

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
            # 判断是否使用合并转发
            is_group_message = self._is_group_message(event)
            use_merge_forward = (is_group_message and self.merge_forward_group) or (
                not is_group_message and self.merge_forward_private
            )

            if use_merge_forward:
                # 使用合并转发方式发送
                async for result in self._send_with_merge_forward(
                    event, analysis_results, is_group_message
                ):
                    yield result
            else:
                # 使用原有的逐条发送方式
                async for result in self._send_individually(event, analysis_results):
                    yield result

        except Exception as e:
            logger.error(f"发送分析结果失败: {e}")
            yield event.plain_result(f"❌ 发送分析结果失败: {str(e)}")

    def _is_group_message(self, event: AstrMessageEvent) -> bool:
        """判断消息是否为群聊消息

        Args:
            event: 消息事件对象

        Returns:
            是否为群聊消息
        """
        # 方法1：检查 unified_msg_origin
        if hasattr(event, "unified_msg_origin"):
            umo = event.unified_msg_origin
            if hasattr(umo, "group_id") and umo.group_id:
                return True

        # 方法2：检查 group_id 属性
        if hasattr(event, "group_id") and event.group_id:
            return True

        # 方法3：检查 is_private_chat 方法
        if hasattr(event, "is_private_chat"):
            try:
                is_private = event.is_private_chat()
                return not is_private
            except Exception:
                pass

        return False

    async def _send_with_merge_forward(
        self, event: AstrMessageEvent, analysis_results: list, is_group: bool
    ):
        """使用合并转发方式发送分析结果

        Args:
            event: 消息事件对象
            analysis_results: 分析结果列表
            is_group: 是否为群聊消息

        Yields:
            消息结果
        """
        nodes = []
        sender_id = self._get_sender_id(event)
        screenshots_to_send = []  # 收集需要单独发送的截图

        for i, result_data in enumerate(analysis_results, 1):
            screenshot = result_data.get("screenshot")
            analysis_result = result_data.get("result")
            url = result_data.get("url", "")

            # 构建节点内容列表
            node_content = []

            # 添加文本内容
            if self.send_content_type != "screenshot_only" and analysis_result:
                if len(analysis_results) == 1:
                    result_text = f"网页分析结果：\n{analysis_result}"
                else:
                    result_text = f"第{i}/{len(analysis_results)}个网页分析结果\n\n{analysis_result}"
                node_content.append(Plain(result_text))

            # 处理截图
            has_screenshot = False
            if self.send_content_type != "analysis_only":
                # 检查是否有实际的截图数据（从缓存或新生成的）
                if isinstance(screenshot, bytes) and len(screenshot) > 0:
                    has_screenshot = True
                    logger.info(f"检测到实际截图数据，大小: {len(screenshot)} 字节")
                else:
                    logger.info(f"无截图数据 - screenshot类型: {type(screenshot)}, 大小: {len(screenshot) if screenshot else 0}")

            # 根据配置决定如何处理截图
            if self.merge_forward_include_screenshot and has_screenshot and screenshot:
                # 将截图添加到合并转发中
                try:
                    # 使用项目目录下的临时文件，而不是系统临时目录
                    import uuid
                    temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "temp")
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    suffix = f".{self.screenshot_format}" if self.screenshot_format else ".jpg"
                    temp_filename = f"{uuid.uuid4()}{suffix}"
                    temp_file_path = os.path.join(temp_dir, temp_filename)
                    
                    # 写入临时文件
                    with open(temp_file_path, "wb") as f:
                        f.write(screenshot)
                    
                    image_component = Image.fromFileSystem(temp_file_path)
                    node_content.append(image_component)
                    
                    logger.info(f"创建临时截图文件: {temp_file_path}, 大小: {len(screenshot)} 字节")
                except Exception as e:
                    logger.error(f"添加截图到合并转发失败: {e}")
            elif not self.merge_forward_include_screenshot and has_screenshot and screenshot:
                # 收集截图，稍后单独发送
                screenshots_to_send.append(screenshot)

            # 创建节点
            if node_content:
                node = Node(
                    uin=sender_id,
                    name=f"网页分析 {i}",
                    content=node_content,
                )
                nodes.append(node)

        # 发送合并转发消息
        if nodes:
            try:
                merge_forward_message = Nodes(nodes)
                yield event.chain_result([merge_forward_message])
                logger.info(f"使用合并转发发送了 {len(nodes)} 个分析结果")
            except Exception as e:
                logger.error(f"发送合并转发消息失败: {e}")
                # 如果合并转发失败，回退到逐条发送
                logger.info("合并转发失败，回退到逐条发送方式")
                async for result in self._send_individually(event, analysis_results):
                    yield result
                return

        # 如果配置了不包含截图在合并转发中，则单独发送截图
        if screenshots_to_send:
            logger.info(f"单独发送 {len(screenshots_to_send)} 个截图")
            for screenshot in screenshots_to_send:
                try:
                    suffix = f".{self.screenshot_format}" if self.screenshot_format else ".jpg"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                        temp_file.write(screenshot)
                        temp_file_path = temp_file.name

                    image_component = Image.fromFileSystem(temp_file_path)
                    yield event.chain_result([image_component])
                    logger.info("发送截图成功")

                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"发送截图失败: {e}")
                    if "temp_file_path" in locals() and os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)

    def _get_sender_id(self, event: AstrMessageEvent) -> int:
        """获取发送者ID

        Args:
            event: 消息事件对象

        Returns:
            发送者ID
        """
        # 方法1：使用 get_sender_id
        if hasattr(event, "get_sender_id"):
            try:
                return event.get_sender_id()
            except Exception:
                pass

        # 方法2：从 unified_msg_origin 获取
        if hasattr(event, "unified_msg_origin"):
            umo = event.unified_msg_origin
            if hasattr(umo, "user_id"):
                return umo.user_id

        # 方法3：从 sender_id 属性获取
        if hasattr(event, "sender_id"):
            return event.sender_id

        # 默认返回0（机器人自己的ID）
        return 0

    def _load_screenshot_from_cache(self, url: str) -> bytes | None:
        """从缓存加载截图数据

        Args:
            url: 网页URL

        Returns:
            截图二进制数据，如果不存在则返回None
        """
        try:
            # 获取缓存目录
            cache_dir = self.cache_manager.cache_dir
            import hashlib
            
            # 计算截图文件路径
            url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            screenshot_path = os.path.join(cache_dir, f"{url_hash}_screenshot.bin")
            
            # 检查文件是否存在
            if os.path.exists(screenshot_path):
                with open(screenshot_path, "rb") as f:
                    return f.read()
            
            return None
        except Exception as e:
            logger.error(f"从缓存加载截图失败: {url}, 错误: {e}")
            return None

    async def _send_individually(self, event: AstrMessageEvent, analysis_results: list):
        """逐条发送分析结果

        Args:
            event: 消息事件对象
            analysis_results: 分析结果列表

        Yields:
            消息结果
        """
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
