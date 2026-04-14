"""
命令处理器模块

使用 CommandMixin 模式，提供所有的插件命令处理方法。
这些方法将作为混入类被主插件类继承，保持对 self 的完整访问。
"""

import json
import os
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Node, Nodes, Plain

from .plugin_helpers import PluginHelpers
from .utils import WebAnalyzerUtils


class CommandMixin:
    """命令处理器混入类

    包含所有的插件命令处理方法，通过继承的方式混入主插件类。
    这样可以保持对主类实例属性的完整访问。
    """

    @filter.command("web_help", alias={"网页分析帮助", "网页分析命令"})
    async def show_help(self, event: AstrMessageEvent):
        """显示插件的所有可用命令和帮助信息"""
        help_text = """【网页分析插件命令帮助】

📋 核心分析命令
🔍 /网页分析 <URL1> <URL2>... - 手动分析指定网页链接
   别名：/分析, /总结, /web, /analyze
   示例：/网页分析 https://example.com

📋 配置管理命令
🛠️ /web_config - 查看当前插件配置
   别名：/网页分析配置, /网页分析设置
   示例：/web_config

📋 缓存管理命令
🗑️ /web_cache [clear] - 管理分析结果缓存
   别名：/网页缓存, /清理缓存
   选项：
     - clear: 清空所有缓存
   示例：/web_cache clear

📋 群聊管理命令
👥 /group_blacklist [add/remove/clear] <群号> - 管理群聊黑名单
   别名：/群黑名单, /黑名单
   选项：
     - (空): 查看当前黑名单
     - add <群号>: 添加群聊到黑名单
     - remove <群号>: 从黑名单移除群聊
     - clear: 清空黑名单
   示例：/群黑名单 add 123456789

📋 导出功能命令
📤 /web_export - 导出分析结果
   别名：/导出分析结果, /网页导出
   示例：/web_export

📋 测试功能命令
📋 /test_merge - 测试合并转发功能
   别名：/测试合并转发, /测试转发
   示例：/test_merge

📋 帮助命令
❓ /web_help - 显示本帮助信息
   别名：/网页分析帮助, /网页分析命令
   示例：/web_help

💡 使用提示：
- 所有命令支持Tab补全（如果客户端支持）
- 命令参数支持提示功能
- 可以自定义命令别名

🔧 配置提示：
- 在AstrBot管理面板中可以配置插件的各项功能
- 支持自定义命令别名
- 可以调整分析结果模板和显示方式
"""

        yield event.plain_result(help_text)
        logger.info("显示命令帮助信息")

    @filter.command("web_config", alias={"网页分析配置", "网页分析设置"})
    async def show_config(self, event: AstrMessageEvent):
        """显示当前插件的详细配置信息"""
        config_info = f"""**网页分析插件配置信息**

**基本设置**
- 最大内容长度: {self.max_content_length} 字符
- 请求超时时间: {self.request_timeout_s} 秒
- LLM智能分析: {"✅ 已启用" if self.llm_enabled else "❌ 已禁用"}
- 分析模式: {self.analysis_mode}
- 自动分析链接: {"✅ 已启用" if self.auto_analyze else "❌ 已禁用"}

**并发处理设置**
- 最大并发数: {self.max_concurrency}
- LLM自主决策: {"✅ 已启用" if self.enable_llm_decision else "❌ 已禁用"}

**域名控制**
- 允许域名: {len(self.allowed_domains)} 个
- 禁止域名: {len(self.blocked_domains)} 个

**群聊控制**
- 群聊黑名单: {len(self.group_blacklist)} 个群聊

**分析设置**
- 启用emoji: {"✅ 已启用" if self.enable_emoji else "❌ 已禁用"}
- 显示统计: {"✅ 已启用" if self.enable_statistics else "❌ 已禁用"}
- 最大摘要长度: {self.max_summary_length} 字符
- 发送内容类型: {self.send_content_type}
- 启用截图: {"✅ 已启用" if self.enable_screenshot else "❌ 已禁用"}
- 截图质量: {self.screenshot_quality}
- 截图宽度: {self.screenshot_width}px
- 截图高度: {self.screenshot_height}px
- 截图格式: {self.screenshot_format}

**缓存设置**
- 启用结果缓存: {"✅ 已启用" if self.enable_cache else "❌ 已禁用"}
- 缓存过期时间: {self.cache_expire_time_min} 分钟
- 最大缓存数量: {self.max_cache_size} 个

*提示: 如需修改配置，请在AstrBot管理面板中编辑插件配置*"""

        yield event.plain_result(config_info)

    @filter.command("test_merge", alias={"测试合并转发", "测试转发"})
    async def test_merge_forward(self, event: AstrMessageEvent):
        """测试合并转发功能"""
        # 检查是否为群聊消息，合并转发仅支持群聊
        group_id = PluginHelpers.get_group_id(event)

        if group_id:
            # 创建测试用的合并转发节点
            nodes = []

            # 标题节点
            title_node = Node(
                uin=event.get_sender_id(),
                name="测试合并转发",
                content=[Plain("这是合并转发测试消息")],
            )
            nodes.append(title_node)

            # 内容节点1
            content_node1 = Node(
                uin=event.get_sender_id(),
                name="测试节点1",
                content=[Plain("这是第一个测试节点内容")],
            )
            nodes.append(content_node1)

            # 内容节点2
            content_node2 = Node(
                uin=event.get_sender_id(),
                name="测试节点2",
                content=[Plain("这是第二个测试节点内容")],
            )
            nodes.append(content_node2)

            # 使用Nodes包装所有节点，合并成一个合并转发消息
            merge_forward_message = Nodes(nodes)
            yield event.chain_result([merge_forward_message])
            logger.info(f"测试合并转发功能，群聊 {group_id}")
        else:
            yield event.plain_result("合并转发功能仅支持群聊消息测试")
            logger.info("私聊消息无法测试合并转发功能")

    @filter.command("group_blacklist", alias={"群黑名单", "黑名单"})
    async def manage_group_blacklist(self, event: AstrMessageEvent):
        """管理群聊黑名单"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()

        # 如果没有参数，显示当前黑名单列表
        if len(message_parts) <= 1:
            if not self.group_blacklist:
                yield event.plain_result("当前群聊黑名单为空")
                return

            blacklist_info = "**当前群聊黑名单**\n\n"
            for i, group_id in enumerate(self.group_blacklist, 1):
                blacklist_info += f"{i}. {group_id}\n"

            blacklist_info += "\n使用 `/group_blacklist add <群号>` 添加群聊到黑名单"
            blacklist_info += "\n使用 `/group_blacklist remove <群号>` 从黑名单移除群聊"
            blacklist_info += "\n使用 `/group_blacklist clear` 清空黑名单"

            yield event.plain_result(blacklist_info)
            return

        # 解析操作类型和参数
        action = message_parts[1].lower() if len(message_parts) > 1 else ""
        group_id = message_parts[2] if len(message_parts) > 2 else ""

        # 添加群聊到黑名单
        if action == "add" and group_id:
            if group_id in self.group_blacklist:
                yield event.plain_result(f"群聊 {group_id} 已在黑名单中")
                return

            self.group_blacklist.append(group_id)
            self._save_group_blacklist()
            yield event.plain_result(f"✅ 已添加群聊 {group_id} 到黑名单")

        # 从黑名单移除群聊
        elif action == "remove" and group_id:
            if group_id not in self.group_blacklist:
                yield event.plain_result(f"群聊 {group_id} 不在黑名单中")
                return

            self.group_blacklist.remove(group_id)
            self._save_group_blacklist()
            yield event.plain_result(f"✅ 已从黑名单移除群聊 {group_id}")

        # 清空黑名单
        elif action == "clear":
            if not self.group_blacklist:
                yield event.plain_result("黑名单已为空")
                return

            self.group_blacklist.clear()
            self._save_group_blacklist()
            yield event.plain_result("✅ 已清空群聊黑名单")

        # 无效操作
        else:
            yield event.plain_result(
                "无效的操作，请使用: add <群号>, remove <群号>, clear"
            )

    def _save_group_blacklist(self):
        """保存群聊黑名单到配置文件"""
        try:
            # 将群聊列表转换为文本格式，每行一个群聊ID
            group_text = "\n".join(self.group_blacklist)
            # 获取当前group_settings配置
            group_settings = self.config.get("group_settings", {})
            # 更新group_blacklist
            group_settings["group_blacklist"] = group_text
            # 更新配置并保存到文件
            self.config["group_settings"] = group_settings
            self.config.save_config()
        except Exception as e:
            logger.error(f"保存群聊黑名单失败: {e}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("web_cache", alias={"网页缓存", "清理缓存"})
    async def manage_cache(self, event: AstrMessageEvent):
        """管理插件的网页分析结果缓存"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()

        # 如果没有参数，显示当前缓存状态
        if len(message_parts) <= 1:
            cache_stats = self.cache_manager.get_stats()
            cache_info = "**当前缓存状态**\n\n"
            cache_info += f"- 缓存总数: {cache_stats['total']} 个\n"
            cache_info += f"- 有效缓存: {cache_stats['valid']} 个\n"
            cache_info += f"- 过期缓存: {cache_stats['expired']} 个\n"
            cache_info += f"- 缓存过期时间: {self.cache_expire_time_min} 分钟\n"
            cache_info += f"- 最大缓存数量: {self.max_cache_size} 个\n"
            cache_info += (
                f"- 缓存功能: {'✅ 已启用' if self.enable_cache else '❌ 已禁用'}\n"
            )

            cache_info += "\n使用 `/web_cache clear` 清空所有缓存"

            yield event.plain_result(cache_info)
            return

        # 解析操作类型
        action = message_parts[1].lower() if len(message_parts) > 1 else ""

        # 清空缓存操作
        if action == "clear":
            # 清空所有缓存
            self.cache_manager.clear()
            cache_stats = self.cache_manager.get_stats()
            yield event.plain_result(
                f"✅ 已清空所有缓存，当前缓存数量: {cache_stats['total']} 个"
            )

        # 无效操作
        else:
            yield event.plain_result("无效的操作，请使用: clear")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("web_mode", alias={"分析模式", "网页分析模式"})
    async def manage_analysis_mode(self, event: AstrMessageEvent):
        """管理插件的网页分析模式"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()

        # 如果没有参数，显示当前模式
        if len(message_parts) <= 1:
            mode_names = {
                "auto": "自动分析",
                "manual": "手动分析",
                "hybrid": "混合模式",
            }
            mode_info = "**当前分析模式**\n\n"
            mode_info += f"- 模式: {mode_names.get(self.analysis_mode, self.analysis_mode)} ({self.analysis_mode})\n"
            mode_info += (
                f"- 自动分析: {'✅ 已启用' if self.auto_analyze else '❌ 已禁用'}\n\n"
            )
            mode_info += "使用 `/web_mode <模式>` 切换模式\n"
            mode_info += "支持的模式: auto, manual, hybrid, LLMTOOL"

            yield event.plain_result(mode_info)
            return

        # 解析模式参数
        mode = message_parts[1].lower() if len(message_parts) > 1 else ""
        valid_modes = ["auto", "manual", "hybrid", "LLMTOOL"]

        # 验证模式是否有效
        if mode not in valid_modes:
            yield event.plain_result(f"无效的模式，请使用: {', '.join(valid_modes)}")
            return

        # 更新分析模式
        self.analysis_mode = mode
        self.auto_analyze = mode == "auto"

        yield event.plain_result(f"✅ 已切换到 {mode} 模式")

    @filter.command("web_export", alias={"导出分析结果", "网页导出"})
    async def export_analysis_result(self, event: AstrMessageEvent):
        """导出网页分析结果"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()

        # 检查参数是否足够
        if len(message_parts) < 2:
            yield event.plain_result(
                "请提供要导出的URL链接和格式，例如：/web_export https://example.com md 或 /web_export all json"
            )
            return

        # 获取导出范围和格式
        url_or_all = message_parts[1]
        format_type = message_parts[2] if len(message_parts) > 2 else "md"

        # 验证格式类型是否支持
        supported_formats = ["md", "markdown", "json", "txt"]
        if format_type.lower() not in supported_formats:
            yield event.plain_result(
                f"不支持的格式类型，请使用：{', '.join(supported_formats)}"
            )
            return

        # 准备导出数据
        export_results = []

        if url_or_all.lower() == "all":
            # 导出所有缓存的分析结果
            if not self.cache_manager.memory_cache:
                yield event.plain_result("当前没有缓存的分析结果")
                return

            for url, cache_data in self.cache_manager.memory_cache.items():
                export_results.append({"url": url, "result": cache_data["result"]})
        else:
            # 导出指定URL的分析结果
            url = url_or_all

            # 检查URL格式是否有效
            if not self.analyzer.is_valid_url(url):
                yield event.plain_result("无效的URL链接")
                return

            # 检查缓存中是否已有该URL的分析结果
            cached_result = self.message_handler.check_cache(url)
            if cached_result:
                export_results.append({"url": url, "result": cached_result})
            else:
                # 如果缓存中没有，先进行分析
                yield event.plain_result("缓存中没有该URL的分析结果，正在进行分析...")

                # 抓取并分析网页
                async with self.analyzer as analyzer:
                    html = await analyzer.fetch_webpage(url)
                    if not html:
                        yield event.plain_result(f"无法抓取网页内容: {url}")
                        return

                    content_data = analyzer.extract_content(html, url)
                    if not content_data:
                        yield event.plain_result(f"无法解析网页内容: {url}")
                        return

                    # 调用LLM进行分析
                    if self.enable_translation:
                        translated_content = await self._translate_content(
                            event, content_data["content"]
                        )
                        translated_content_data = content_data.copy()
                        translated_content_data["content"] = translated_content
                        analysis_result = await self.llm_analyzer.analyze_with_llm(
                            event, translated_content_data
                        )
                    else:
                        analysis_result = await self.llm_analyzer.analyze_with_llm(
                            event, content_data
                        )

                    # 提取特定内容（如果启用）
                    if self.enable_specific_extraction:
                        specific_content = analyzer.extract_specific_content(
                            html, url, self.extract_types
                        )
                        if specific_content:
                            # 在分析结果中添加特定内容
                            analysis_result = self._add_specific_content_to_result(
                                analysis_result, specific_content
                            )

                    # 准备导出数据
                    export_results.append(
                        {
                            "url": url,
                            "result": {
                                "url": url,
                                "result": analysis_result,
                                "screenshot": None,
                            },
                        }
                    )

        # 执行导出操作
        try:
            # 创建data目录（如果不存在）
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)

            # 生成文件名
            timestamp = int(time.time())
            if len(export_results) == 1:
                # 单个URL导出，使用域名作为文件名的一部分
                url_obj = export_results[0]["url"]
                from urllib.parse import urlparse

                parsed = urlparse(url_obj)
                domain = parsed.netloc.replace(".", "_")
                filename = f"web_analysis_{domain}_{timestamp}"
            else:
                # 多个URL导出
                filename = f"web_analysis_all_{timestamp}"

            # 确定文件扩展名
            file_extension = format_type.lower()
            if file_extension == "markdown":
                file_extension = "md"

            file_path = os.path.join(data_dir, f"{filename}.{file_extension}")

            if format_type.lower() in ["md", "markdown"]:
                # 生成Markdown格式内容
                md_content = "# 网页分析结果导出\n\n"
                md_content += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}\n\n"
                md_content += f"共 {len(export_results)} 个分析结果\n\n"
                md_content += "---\n\n"

                for i, export_item in enumerate(export_results, 1):
                    url = export_item["url"]
                    result_data = export_item["result"]

                    md_content += f"## {i}. {url}\n\n"
                    md_content += result_data["result"]
                    md_content += "\n\n"
                    md_content += "---\n\n"

                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(md_content)

            elif format_type.lower() == "json":
                # 生成JSON格式内容
                json_data = {
                    "export_time": timestamp,
                    "export_time_str": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(timestamp)
                    ),
                    "total_results": len(export_results),
                    "results": [],
                }

                for export_item in export_results:
                    url = export_item["url"]
                    result_data = export_item["result"]

                    json_data["results"].append(
                        {
                            "url": url,
                            "analysis_result": result_data["result"],
                            "has_screenshot": result_data["screenshot"] is not None,
                        }
                    )

                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)

            elif format_type.lower() == "txt":
                # 生成纯文本格式内容
                txt_content = "网页分析结果导出\n"
                txt_content += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}\n"
                txt_content += f"共 {len(export_results)} 个分析结果\n"
                txt_content += "=" * 50 + "\n\n"

                for i, export_item in enumerate(export_results, 1):
                    url = export_item["url"]
                    result_data = export_item["result"]

                    txt_content += f"{i}. {url}\n"
                    txt_content += "-" * 30 + "\n"
                    txt_content += result_data["result"]
                    txt_content += "\n\n"
                    txt_content += "=" * 50 + "\n\n"

                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(txt_content)

            # 发送导出成功消息，并附带导出文件
            # 构建消息链
            message_chain = [
                Plain("✅ 分析结果导出成功！\n\n"),
                Plain(f"导出格式: {format_type}\n"),
                Plain(f"导出数量: {len(export_results)}\n\n"),
                Plain("📁 导出文件：\n"),
                File(file=file_path, name=os.path.basename(file_path)),
            ]

            yield event.chain_result(message_chain)

            logger.info(
                f"成功导出 {len(export_results)} 个分析结果到 {file_path}，并发送给用户"
            )

        except Exception as e:
            logger.error(f"导出分析结果失败: {e}")
            yield event.plain_result(f"❌ 导出分析结果失败: {str(e)}")

    async def _translate_content(self, event: AstrMessageEvent, content: str) -> str:
        """翻译网页内容

        Args:
            event: 消息事件对象
            content: 要翻译的内容

        Returns:
            翻译后的内容
        """
        if not self.enable_translation:
            return content

        try:
            # 检查LLM是否可用
            if not hasattr(self.context, "llm_generate"):
                logger.error("LLM不可用，无法进行翻译")
                return content

            # 优先使用配置的LLM提供商，如果没有配置则使用当前会话的模型
            provider_id = self.llm_provider
            if not provider_id:
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)

            if not provider_id:
                logger.error("无法获取LLM提供商ID，无法进行翻译")
                return content

            # 使用自定义翻译提示词或默认提示词
            if self.custom_translation_prompt:
                # 替换自定义提示词中的变量
                # 对用户可控内容进行花括号转义，防止 format() 异常
                safe_content = WebAnalyzerUtils.escape_format_braces(content)
                prompt = self.custom_translation_prompt.format(
                    content=safe_content, target_language=self.target_language
                )
            else:
                # 默认翻译提示词
                prompt = (
                    f"请将以下内容翻译成{self.target_language}语言，"
                    f"保持原文意思不变，语言流畅自然：\n\n{content}"
                )

            # 调用LLM进行翻译
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id, prompt=prompt
            )

            if llm_resp and llm_resp.completion_text:
                return llm_resp.completion_text.strip()
            else:
                logger.error("LLM翻译返回为空")
                return content
        except Exception as e:
            logger.error(f"翻译内容失败: {e}")
            return content

    def _add_specific_content_to_result(
        self, analysis_result: str, specific_content: dict
    ) -> str:
        """将特定内容添加到分析结果中

        Args:
            analysis_result: 当前的分析结果
            specific_content: 特定内容字典

        Returns:
            更新后的分析结果
        """
        try:
            # 在分析结果中添加特定内容
            specific_content_str = "\n\n**特定内容提取**\n"

            # 添加图片链接（如果有）
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

            # 添加相关链接（如果有）
            if "links" in specific_content and specific_content["links"]:
                specific_content_str += (
                    f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                )
                for link in specific_content["links"][:5]:
                    specific_content_str += f"- [{link['text']}]({link['url']})\n"

            # 添加视频链接（如果有）
            if "videos" in specific_content and specific_content["videos"]:
                specific_content_str += (
                    f"\n🎬 视频链接 ({len(specific_content['videos'])}):\n"
                )
                for video in specific_content["videos"]:
                    video_url = video.get("url", "")
                    video_type = video.get("type", "video")
                    specific_content_str += f"- {video_url} (type: {video_type})\n"

            # 添加音频链接（如果有）
            if "audios" in specific_content and specific_content["audios"]:
                specific_content_str += (
                    f"\n🎵 音频链接 ({len(specific_content['audios'])}):\n"
                )
                for audio in specific_content["audios"]:
                    specific_content_str += f"- {audio}\n"

            # 添加引用块（如果有）
            if "quotes" in specific_content and specific_content["quotes"]:
                specific_content_str += (
                    f"\n💬 引用块 ({len(specific_content['quotes'])}):\n"
                )
                for quote in specific_content["quotes"][:3]:
                    quote_text = quote.get("text", "")
                    author = quote.get("author", "")
                    if author:
                        specific_content_str += f"> {quote_text} — {author}\n\n"
                    else:
                        specific_content_str += f"> {quote_text}\n\n"

            # 添加标题列表（如果有）
            if "headings" in specific_content and specific_content["headings"]:
                specific_content_str += (
                    f"\n📑 标题列表 ({len(specific_content['headings'])}):\n"
                )
                for heading in specific_content["headings"]:
                    level = heading.get("level", 1)
                    text = heading.get("text", "")
                    heading_id = heading.get("id", "")
                    indent = "  " * (level - 1)
                    if heading_id:
                        specific_content_str += (
                            f"{indent}#{level} {text} (id: {heading_id})\n"
                        )
                    else:
                        specific_content_str += f"{indent}#{level} {text}\n"

            # 添加代码块（如果有）
            if "code_blocks" in specific_content and specific_content["code_blocks"]:
                specific_content_str += (
                    f"\n💻 代码块 ({len(specific_content['code_blocks'])}):\n"
                )
                for code_block in specific_content["code_blocks"][:2]:
                    code = code_block.get("code", "")
                    language = code_block.get("language", "")
                    specific_content_str += f"``` {language}\n{code}\n```\n"

            # 添加表格（如果有）
            if "tables" in specific_content and specific_content["tables"]:
                specific_content_str += (
                    f"\n📊 表格 ({len(specific_content['tables'])}):\n"
                )
                for table in specific_content["tables"][:2]:
                    headers = table.get("headers", [])
                    rows = table.get("rows", [])
                    specific_content_str += "\n表格:\n"
                    if headers:
                        specific_content_str += (
                            f"| {' | '.join(headers)} |\n"
                            f"| {' | '.join(['---' for _ in headers])} |\n"
                        )
                    for row in rows:
                        specific_content_str += f"| {' | '.join(row)} |\n"

            # 添加列表（如果有）
            if "lists" in specific_content and specific_content["lists"]:
                specific_content_str += (
                    f"\n📋 列表 ({len(specific_content['lists'])}):\n"
                )
                for list_item in specific_content["lists"][:2]:
                    list_type = list_item.get("type", "ul")
                    items = list_item.get("items", [])
                    specific_content_str += f"\n列表 ({list_type}):\n"
                    for item in items:
                        if list_type == "ol":
                            specific_content_str += f"1. {item}\n"
                        else:
                            specific_content_str += f"- {item}\n"

            # 添加元信息（如果有）
            if "meta" in specific_content and specific_content["meta"]:
                meta_info = specific_content["meta"]
                specific_content_str += "\n📋 元信息:\n"
                for key, value in meta_info.items():
                    if value:
                        specific_content_str += f"- {key}: {value}\n"

            # 将特定内容添加到分析结果中
            return analysis_result + specific_content_str
        except Exception as e:
            logger.warning(f"添加特定内容失败: {e}")
            return analysis_result
