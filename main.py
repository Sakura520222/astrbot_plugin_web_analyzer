"""
AstrBot 网页分析插件 - 重构版本

自动识别网页链接，智能抓取解析内容，集成大语言模型进行深度分析和总结，
支持网页截图、缓存机制和多种管理命令。

本版本使用核心模块重构，遵循 PEP 8 规范。
"""

from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Node, Nodes, Plain
from astrbot.api.star import Context, Star, register

from .core.analyzer import WebAnalyzer
from .core.cache import CacheManager

# 导入核心模块
from .core.config_loader import ConfigLoader
from .core.llm_analyzer import LLMAnalyzer
from .core.message_handler import MessageHandler
from .core.plugin_helpers import MessageHelpers, PluginHelpers
from .core.result_formatter import ResultFormatter


@register(
    "astrbot_plugin_web_analyzer",
    "Sakura520222",
    "自动识别网页链接，智能抓取解析内容，集成大语言模型进行深度分析和总结，支持网页截图、缓存机制和多种管理命令",
    "1.5.5",
    "https://github.com/Sakura520222/astrbot_plugin_web_analyzer",
)
class WebAnalyzerPlugin(Star):
    """网页分析插件主类，负责管理和调度所有功能模块"""

    def __init__(self, context: Context, config: AstrBotConfig):
        """插件初始化方法，负责加载、验证和初始化所有配置项"""
        super().__init__(context)
        self.config = config

        # 使用配置加载器加载所有配置
        config_dict = ConfigLoader.load_all_config(config, context)

        # 将配置项设置为实例属性
        for key, value in config_dict.items():
            setattr(self, key, value)

        # URL处理标志集合：用于避免重复处理同一URL
        self.processing_urls = set()

        # 初始化核心组件
        self._init_components(context, config_dict)

        # 撤回任务列表：用于管理所有撤回任务
        self.recall_tasks = []

        # 记录配置初始化完成
        logger.info("插件配置初始化完成")

    def _init_components(self, context: Context, config_dict: dict):
        """初始化所有核心组件

        Args:
            context: AstrBot 上下文对象
            config_dict: 配置字典
        """
        # 初始化缓存管理器
        self.cache_manager = CacheManager(
            max_size=self.max_cache_size,
            expire_time=self.cache_expire_time_min,
            preload_enabled=self.cache_preload_enabled,
            preload_count=self.cache_preload_count,
        )

        # 初始化网页分析器
        self.analyzer = WebAnalyzer(
            max_content_length=self.max_content_length,
            timeout=self.request_timeout_s,
            user_agent=self.user_agent,
            proxy=self.proxy,
            retry_count=self.retry_count,
            retry_delay=self.retry_delay_s,
            enable_memory_monitor=self.enable_memory_monitor,
            memory_threshold=self.memory_threshold_percent,
            enable_unified_domain=self.enable_unified_domain,
            hide_ip=self.hide_ip,
        )

        # 初始化结果格式化器
        self.result_formatter = ResultFormatter(
            enable_emoji=self.enable_emoji,
            enable_statistics=self.enable_statistics,
        )

        # 初始化 LLM 分析器
        self.llm_analyzer = LLMAnalyzer(
            context=context,
            llm_provider=self.llm_provider,
            custom_prompt=self.custom_prompt,
            max_summary_length=self.max_summary_length,
            enable_emoji=self.enable_emoji,
            llm_enabled=self.llm_enabled,
        )

        # 初始化消息处理器
        self.message_handler = MessageHandler(
            analyzer=self.analyzer,
            cache_manager=self.cache_manager,
            enable_cache=self.enable_cache,
            enable_screenshot=self.enable_screenshot,
            send_content_type=self.send_content_type,
            screenshot_format=self.screenshot_format,
            screenshot_quality=self.screenshot_quality,
            screenshot_width=self.screenshot_width,
            screenshot_height=self.screenshot_height,
            screenshot_full_page=self.screenshot_full_page,
            screenshot_wait_ms=self.screenshot_wait_ms,
            enable_crop=self.enable_crop,
            crop_area=self.crop_area,
            merge_forward_group=self.merge_forward_group,
            merge_forward_private=self.merge_forward_private,
            merge_forward_include_screenshot=self.merge_forward_include_screenshot,
            max_concurrency=self.max_concurrency,
        )

    @filter.command("网页分析", alias={"分析", "总结", "web", "analyze"})
    async def analyze_webpage(self, event: AstrMessageEvent):
        """手动触发网页分析命令"""
        message_text = event.message_str

        # 从消息中提取所有URL
        urls = self.analyzer.extract_urls(
            message_text, self.enable_no_protocol_url, self.default_protocol
        )
        if not urls:
            yield event.plain_result(
                "请提供要分析的网页链接，例如：/网页分析 https://example.com"
            )
            return

        # 验证URL格式是否正确，并规范化URL
        valid_urls = list(
            {
                self.analyzer.normalize_url(url)
                for url in urls
                if self.analyzer.is_valid_url(url)
            }
        )
        if not valid_urls:
            yield event.plain_result("无效的URL链接，请检查格式是否正确")
            return

        # 过滤掉不允许访问的域名
        allowed_urls = [
            url
            for url in valid_urls
            if PluginHelpers.is_domain_allowed(
                url, self.allowed_domains, self.blocked_domains
            )
        ]
        if not allowed_urls:
            yield event.plain_result("所有域名都不在允许访问的列表中，或已被禁止访问")
            return

        # 检查群组黑名单
        group_id = PluginHelpers.get_group_id(event)
        if PluginHelpers.is_group_blacklisted(
            str(group_id) if group_id else "", self.group_blacklist
        ):
            logger.info(f"群组 {group_id} 在黑名单中，跳过处理")
            return

        # 发送处理提示消息
        if len(allowed_urls) == 1:
            message = f"正在分析网页: {allowed_urls[0]}"
        else:
            message = f"正在分析{len(allowed_urls)}个网页链接..."

        processing_message_id, bot = await MessageHelpers.send_processing_message(
            event,
            message,
            self.enable_recall,
            self.recall_type,
            self.recall_time_s,
            self.smart_recall_enabled,
            self.recall_tasks,
        )

        # 批量处理所有允许访问的URL
        async for result in self._batch_process_urls(
            event, allowed_urls, processing_message_id, bot
        ):
            yield result

    @filter.llm_tool(name="analyze_webpage")
    async def analyze_webpage_tool(self, event: AstrMessageEvent, url: str) -> Any:
        """智能网页分析工具

        Args:
            url(string): 要分析的网页URL地址，支持http和https协议
        """
        # 检查是否启用了LLMTOOL模式，未启用则不执行
        if self.analysis_mode != "LLMTOOL":
            logger.info(f"当前未启用LLMTOOL模式，拒绝analyze_webpage_tool调用: {url}")
            yield event.plain_result("当前未启用网页分析工具模式")
            return

        logger.info(f"收到analyze_webpage_tool调用，原始URL: {url}")

        # 预处理URL：去除可能的反引号、空格等
        processed_url = url.strip().strip("`")
        logger.info(f"预处理后的URL: {processed_url}")

        # 补全URL协议头（如果需要）
        if not processed_url.startswith(("http://", "https://")):
            processed_url = f"{self.default_protocol}://{processed_url}"
            logger.info(f"补全协议头后的URL: {processed_url}")

        # 规范化URL
        normalized_url = self.analyzer.normalize_url(processed_url)
        logger.info(f"规范化后的URL: {normalized_url}")

        if not self.analyzer.is_valid_url(normalized_url):
            error_msg = f"无效的URL链接，请检查格式是否正确: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 检查域名是否允许访问
        if not PluginHelpers.is_domain_allowed(
            normalized_url, self.allowed_domains, self.blocked_domains
        ):
            error_msg = f"该域名不在允许访问的列表中: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 发送处理提示消息，告知用户正在分析
        message = f"正在分析网页: {normalized_url}"
        processing_message_id, bot = await MessageHelpers.send_processing_message(
            event,
            message,
            self.enable_recall,
            self.recall_type,
            self.recall_time_s,
            self.smart_recall_enabled,
            self.recall_tasks,
        )

        # 处理单个URL
        async for result in self._batch_process_urls(
            event, [normalized_url], processing_message_id, bot
        ):
            yield result

    @filter.llm_tool(name="analyze_webpage_with_decision")
    async def analyze_webpage_with_decision_tool(
        self, event: AstrMessageEvent, url: str, return_type: str = "both"
    ) -> Any:
        """智能网页分析工具（带自主决策）

        Args:
            url(string): 要分析的网页URL地址，支持http和https协议
            return_type(string): 返回结果类型，可选值：analysis_only（仅分析结果）、screenshot_only（仅截图）、both（两者都返回），默认为both
        """
        # 检查是否启用了LLMTOOL模式，未启用则不执行
        if self.analysis_mode != "LLMTOOL":
            logger.info(
                f"当前未启用LLMTOOL模式，拒绝analyze_webpage_with_decision_tool调用: {url}"
            )
            yield event.plain_result("当前未启用网页分析工具模式")
            return

        # 检查是否启用了LLM自主决策功能
        if not self.enable_llm_decision:
            logger.info(
                f"当前未启用LLM自主决策功能，拒绝analyze_webpage_with_decision_tool调用: {url}"
            )
            yield event.plain_result("当前未启用LLM自主决策功能")
            return

        logger.info(
            f"收到analyze_webpage_with_decision_tool调用，原始URL: {url}，返回类型: {return_type}"
        )

        # 验证返回类型
        valid_return_types = ["analysis_only", "screenshot_only", "both"]
        if return_type not in valid_return_types:
            logger.warning(f"无效的返回类型: {return_type}，使用默认值: both")
            return_type = "both"

        # 预处理URL：去除可能的反引号、空格等
        processed_url = url.strip().strip("`")
        logger.info(f"预处理后的URL: {processed_url}")

        # 补全URL协议头（如果需要）
        if not processed_url.startswith(("http://", "https://")):
            processed_url = f"{self.default_protocol}://{processed_url}"
            logger.info(f"补全协议头后的URL: {processed_url}")

        # 规范化URL
        normalized_url = self.analyzer.normalize_url(processed_url)
        logger.info(f"规范化后的URL: {normalized_url}")

        if not self.analyzer.is_valid_url(normalized_url):
            error_msg = f"无效的URL链接，请检查格式是否正确: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 检查域名是否允许访问
        if not PluginHelpers.is_domain_allowed(
            normalized_url, self.allowed_domains, self.blocked_domains
        ):
            error_msg = f"该域名不在允许访问的列表中: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 发送处理提示消息，告知用户正在分析
        message = f"正在分析网页: {normalized_url}"
        processing_message_id, bot = await MessageHelpers.send_processing_message(
            event,
            message,
            self.enable_recall,
            self.recall_type,
            self.recall_time_s,
            self.smart_recall_enabled,
            self.recall_tasks,
        )

        # 保存原始send_content_type配置
        original_send_content_type = self.message_handler.send_content_type

        try:
            # 根据LLM的决策设置send_content_type
            self.message_handler.send_content_type = return_type
            logger.info(f"临时设置send_content_type为: {return_type}")

            # 处理单个URL
            async for result in self._batch_process_urls(
                event, [normalized_url], processing_message_id, bot
            ):
                yield result
        finally:
            # 恢复原始send_content_type配置
            self.message_handler.send_content_type = original_send_content_type
            logger.info(f"恢复send_content_type为: {original_send_content_type}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_detect_urls(self, event: AstrMessageEvent):
        """自动检测消息中的URL链接并进行分析"""
        # 检查分析模式，manual模式下不进行自动分析
        if self.analysis_mode == "manual":
            return

        # 检查是否启用自动分析功能（兼容旧配置）
        if not self.auto_analyze:
            return

        # 检查是否为指令调用，避免重复处理
        message_text = event.message_str.strip()

        # 跳过以/开头的指令消息
        if message_text.startswith("/"):
            logger.info("检测到指令调用，跳过自动分析")
            return

        # 检查事件是否有command属性（指令调用时会有）
        if hasattr(event, "command"):
            logger.info("检测到command属性，跳过自动分析")
            return

        # 检查群聊是否在黑名单中（仅群聊消息）
        group_id = PluginHelpers.get_group_id(event)
        if PluginHelpers.is_group_blacklisted(
            str(group_id) if group_id else "", self.group_blacklist
        ):
            return

        # 从消息中提取所有URL
        urls = self.analyzer.extract_urls(
            message_text, self.enable_no_protocol_url, self.default_protocol
        )
        if not urls:
            return

        # 验证URL格式是否正确，并规范化URL
        valid_urls = list(
            {
                self.analyzer.normalize_url(url)
                for url in urls
                if self.analyzer.is_valid_url(url)
            }
        )
        if not valid_urls:
            return

        # 过滤掉不允许访问的域名
        allowed_urls = [
            url
            for url in valid_urls
            if PluginHelpers.is_domain_allowed(
                url, self.allowed_domains, self.blocked_domains
            )
        ]
        if not allowed_urls:
            return

        # 根据analysis_mode配置决定是否使用旧版直接分析方式
        if self.analysis_mode == "LLMTOOL":
            # 启用了LLM函数工具模式，不使用旧版直接分析
            logger.info(
                f"启用了LLM函数工具模式，不自动分析链接，让LLM自己决定: {allowed_urls}"
            )
            return
        else:
            # 未启用LLM函数工具模式，使用旧版直接分析方式
            # 发送处理提示消息，告知用户正在分析
            if len(allowed_urls) == 1:
                message = f"检测到网页链接，正在分析: {allowed_urls[0]}"
            else:
                message = f"检测到{len(allowed_urls)}个网页链接，正在分析..."

            # 直接调用发送方法，不使用yield，获取message_id和bot实例
            processing_message_id, bot = await MessageHelpers.send_processing_message(
                event,
                message,
                self.enable_recall,
                self.recall_type,
                self.recall_time_s,
                self.smart_recall_enabled,
                self.recall_tasks,
            )

            # 批量处理所有允许访问的URL
            if self.allow_llm_propagation:
                # 允许事件传播：使用 send_message 直接发送，不 yield
                # 这样不会设置 event result，事件继续传播到 LLM
                async for result in self._batch_process_urls(
                    event, allowed_urls, processing_message_id, bot
                ):
                    await self.context.send_message(
                        event.unified_msg_origin, result
                    )
            else:
                # 默认行为：yield 结果，阻止事件传播到 LLM
                async for result in self._batch_process_urls(
                    event, allowed_urls, processing_message_id, bot
                ):
                    yield result

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
- 启用「允许LLM传播」后，自动分析URL不会阻止LLM回复原始消息
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

        # 保存配置
        try:
            analysis_settings = self.config.get("analysis_settings", {})
            analysis_settings["analysis_mode"] = mode
            self.config["analysis_settings"] = analysis_settings
            self.config.save_config()
            logger.info(f"已保存分析模式配置: {mode}")
        except Exception as e:
            logger.error(f"保存分析模式配置失败: {e}")

        yield event.plain_result(f"✅ 已切换到 {mode} 模式")

    @filter.command("web_export", alias={"导出分析结果", "网页导出"})
    async def export_analysis_result(self, event: AstrMessageEvent):
        """导出网页分析结果"""
        import json
        import os
        import time

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
                prompt = self.custom_translation_prompt.format(
                    content=content, target_language=self.target_language
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

    async def _batch_process_urls(
        self,
        event: AstrMessageEvent,
        urls: list,
        processing_message_id: int,
        bot: Any,
    ):
        """批量处理多个URL"""
        results = []

        for url in urls:
            try:
                # 标记URL正在处理中
                self.processing_urls.add(url)

                # 使用消息处理器处理单个URL
                result = await self.message_handler.process_single_url(
                    event=event,
                    url=url,
                    analyzer=self.analyzer,
                    llm_analyzer=self.llm_analyzer if self.llm_enabled else None,
                    enable_translation=self.enable_translation,
                    enable_specific_extraction=self.enable_specific_extraction,
                    extract_types=self.extract_types,
                    result_formatter=self.result_formatter,
                )
                results.append(result)

                # 从处理中集合移除URL
                self.processing_urls.discard(url)

            except Exception as e:
                error_type = PluginHelpers.get_error_type(e)
                error_msg = PluginHelpers.handle_error(error_type, e, url)
                results.append({"url": url, "result": error_msg, "screenshot": None})
                self.processing_urls.discard(url)

        # 发送所有分析结果
        if results:
            async for result in self.message_handler.send_analysis_result(
                event, results
            ):
                yield result

        # 撤回处理消息
        if self.enable_recall and processing_message_id and bot:
            await MessageHelpers.recall_processing_message(
                event,
                processing_message_id,
                bot,
                self.recall_time_s,
                self.recall_type,
                self.smart_recall_enabled,
            )

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("网页分析插件已卸载")
