"""
AstrBot 网页分析插件

这是一个功能强大的AstrBot插件，专门用于网页内容的智能分析和总结。

✨ 核心功能
- 🤖 自动识别消息中的网页链接，无需手动指令
- 🌐 智能抓取和解析网页内容，支持多种网站结构
- 🧠 集成大语言模型(LLM)，提供深度分析和总结
- 📸 支持网页截图，直观展示网页内容
- 🔄 内置缓存机制，提升重复访问的响应速度
- 📝 支持多种分析结果导出格式
- 🔧 提供丰富的管理命令，方便配置和维护

📖 使用方式
- 自动模式：直接发送包含网页链接的消息
- 手动模式：使用 `/网页分析` 命令，例如：`/网页分析 https://example.com`
- 支持多种指令别名：`分析`、`总结`、`web`、`analyze`

🎯 插件优势
- 异步处理设计，支持并发分析多个URL
- 灵活的配置选项，满足不同使用场景
- 完善的错误处理，确保插件稳定运行
- 支持域名白名单和黑名单，控制访问范围
- 支持内容翻译，突破语言障碍

本插件采用模块化设计，包含缓存管理、网页分析、命令处理等多个组件，
可根据需求灵活扩展和定制。
"""

from typing import List

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .analyzer import WebAnalyzer
from .cache import CacheManager


@register(
    "astrbot_plugin_web_analyzer",
    "Sakura520222",
    "自动识别网页链接并进行内容分析和总结",
    "1.2.7",
    "https://github.com/Sakura520222/astrbot_plugin_web_analyzer",
)
class WebAnalyzerPlugin(Star):
    """网页分析插件主类

    这是插件的核心协调类，负责管理和调度所有功能模块：
    - 🔧 配置的加载、验证和管理
    - 📩 消息事件的监听和处理
    - 🔗 URL的提取、验证和过滤
    - 🕸️  网页内容的抓取、解析和分析
    - 🧠 大语言模型(LLM)的调用和结果生成
    - 💾 分析结果的缓存管理
    - ⚙️  各种管理命令的处理和响应

    插件支持两种分析模式：
    - 自动模式：自动识别消息中的网页链接并分析
    - 手动模式：通过命令触发网页分析

    提供了丰富的配置选项，可根据需求灵活调整插件行为。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        """插件初始化方法

        负责加载、验证和初始化所有配置项，构建插件的运行环境：

        🛠️ 基本配置：
        - 请求超时时间和重试机制
        - 用户代理和代理设置
        - 自动分析开关

        🚫 域名控制：
        - 允许访问的域名列表
        - 禁止访问的域名列表

        📊 分析设置：
        - 是否使用emoji增强显示
        - 是否显示内容统计信息
        - 最大摘要长度限制

        📸 截图配置：
        - 截图质量和分辨率
        - 是否截取整页
        - 截图格式（JPEG/PNG）

        🧠 LLM配置：
        - 大语言模型提供商
        - 自定义提示词

        👥 群聊管理：
        - 群聊黑名单设置

        🌐 翻译功能：
        - 是否启用自动翻译
        - 目标语言设置

        💾 缓存管理：
        - 缓存过期时间
        - 最大缓存数量

        📋 内容提取：
        - 提取内容类型设置

        所有配置项都会进行合理性验证，自动修正无效值并设置安全默认值，
        确保插件在各种配置下都能稳定运行。
        """
        super().__init__(context)
        self.config = config
        
        # 初始化配置
        self._load_network_settings()
        self._load_domain_settings()
        self._load_analysis_settings()
        self._load_screenshot_settings()
        self._load_llm_settings()
        self._load_group_settings()
        self._load_translation_settings()
        self._load_cache_settings()
        self._load_content_extraction_settings()
        
        # 初始化组件
        self._init_cache_manager()
        self._init_web_analyzer()
        
        # URL处理标志集合：用于避免重复处理同一URL
        self.processing_urls = set()
        
        # 加载撤回设置
        self._load_recall_settings()
        
        # 撤回任务列表：用于管理所有撤回任务
        self.recall_tasks = []

        # 记录配置初始化完成
        logger.info("插件配置初始化完成")
    
    def _load_network_settings(self):
        """加载和验证网络设置"""
        network_settings = self.config.get("network_settings", {})
        # 最大内容长度：限制抓取的网页内容大小，避免内存占用过高
        self.max_content_length = max(1000, network_settings.get("max_content_length", 10000))
        # 请求超时时间：设置合理的超时范围，避免请求过长时间阻塞
        self.timeout = max(5, min(300, network_settings.get("request_timeout", 30)))
        # 重试次数：请求失败时的重试次数
        self.retry_count = max(0, min(10, network_settings.get("retry_count", 3)))
        # 重试延迟：每次重试之间的等待时间
        self.retry_delay = max(0, min(10, network_settings.get("retry_delay", 2)))
        # 用户代理：用于模拟浏览器请求，避免被网站封禁
        self.user_agent = network_settings.get(
            "user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        # 代理设置：用于网络代理，加速或绕过网络限制
        self.proxy = network_settings.get("proxy", "")

        # 验证代理格式是否正确
        if self.proxy:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(self.proxy)
                if not all([parsed.scheme, parsed.netloc]):
                    logger.warning(f"无效的代理格式: {self.proxy}，将忽略代理设置")
                    self.proxy = ""
            except Exception as e:
                logger.warning(f"解析代理失败: {self.proxy}，将忽略代理设置，错误: {e}")
                self.proxy = ""
    
    def _load_domain_settings(self):
        """加载和验证域名设置"""
        domain_settings = self.config.get("domain_settings", {})
        # 解析允许和禁止的域名列表
        self.allowed_domains = self._parse_domain_list(
            domain_settings.get("allowed_domains", "")
        )
        self.blocked_domains = self._parse_domain_list(
            domain_settings.get("blocked_domains", "")
        )
    
    def _load_analysis_settings(self):
        """加载和验证分析设置"""
        analysis_settings = self.config.get("analysis_settings", {})
        # 是否自动分析检测到的链接
        self.auto_analyze = bool(analysis_settings.get("auto_analyze", True))
        # 是否在结果中使用emoji
        self.enable_emoji = bool(analysis_settings.get("enable_emoji", True))
        # 是否显示内容统计信息
        self.enable_statistics = bool(analysis_settings.get("enable_statistics", True))
        # 最大摘要长度：限制LLM生成的摘要大小
        self.max_summary_length = max(
            500, min(10000, analysis_settings.get("max_summary_length", 2000))
        )

        # 发送内容类型设置
        self.send_content_type = analysis_settings.get("send_content_type", "both")
        # 验证发送内容类型是否有效
        if self.send_content_type not in ["both", "analysis_only", "screenshot_only"]:
            logger.warning(
                f"无效的发送内容类型: {self.send_content_type}，将使用默认值 both"
            )
            self.send_content_type = "both"
    
    def _load_screenshot_settings(self):
        """加载和验证截图设置"""
        screenshot_settings = self.config.get("screenshot_settings", {})
        # 是否启用网页截图
        self.enable_screenshot = bool(screenshot_settings.get("enable_screenshot", True))
        # 截图质量：控制截图的清晰度和文件大小
        self.screenshot_quality = max(
            10, min(100, screenshot_settings.get("screenshot_quality", 80))
        )
        # 截图宽度和高度：控制截图的分辨率
        self.screenshot_width = max(
            320, min(4096, screenshot_settings.get("screenshot_width", 1280))
        )
        self.screenshot_height = max(
            240, min(4096, screenshot_settings.get("screenshot_height", 720))
        )
        # 是否截取整页：控制是否截取完整的网页内容
        self.screenshot_full_page = bool(
            screenshot_settings.get("screenshot_full_page", False)
        )
        # 截图等待时间：页面加载完成后等待的时间，确保内容完整显示
        self.screenshot_wait_time = max(
            0, min(10000, screenshot_settings.get("screenshot_wait_time", 2000))
        )

        # 验证截图格式是否支持
        screenshot_format = screenshot_settings.get("screenshot_format", "jpeg").lower()
        if screenshot_format not in ["jpeg", "png"]:
            logger.warning(f"无效的截图格式: {screenshot_format}，将使用默认格式 jpeg")
            self.screenshot_format = "jpeg"
        else:
            self.screenshot_format = screenshot_format
    
    def _load_llm_settings(self):
        """加载和验证LLM设置"""
        llm_settings = self.config.get("llm_settings", {})
        # 是否启用LLM智能分析
        self.llm_enabled = bool(llm_settings.get("llm_enabled", True))
        # LLM提供商配置：指定使用的大语言模型提供商
        self.llm_provider = llm_settings.get("llm_provider", "")
        # 自定义提示词配置：允许用户自定义LLM分析的提示词
        self.custom_prompt = llm_settings.get("custom_prompt", "")
    
    def _load_group_settings(self):
        """加载和验证群聊设置"""
        group_settings = self.config.get("group_settings", {})
        # 群聊黑名单配置：用于控制哪些群聊不允许使用插件
        group_blacklist_text = group_settings.get("group_blacklist", "")
        self.group_blacklist = self._parse_group_list(group_blacklist_text)
        
        # 合并转发配置：控制是否使用合并转发功能发送分析结果
        merge_forward_config = self.config.get("merge_forward_settings", {})
        self.merge_forward_enabled = {
            "group": bool(merge_forward_config.get("group", False)),
            "private": bool(merge_forward_config.get("private", False)),
            "include_screenshot": bool(
                merge_forward_config.get("include_screenshot", False)
            ),
        }
    
    def _load_translation_settings(self):
        """加载和验证翻译设置"""
        translation_settings = self.config.get("translation_settings", {})
        self.enable_translation = bool(
            translation_settings.get("enable_translation", False)
        )

        # 验证目标语言是否支持
        self.target_language = translation_settings.get("target_language", "zh").lower()
        valid_languages = ["zh", "en", "ja", "ko", "fr", "de", "es", "ru", "ar", "pt"]
        if self.target_language not in valid_languages:
            logger.warning(f"无效的目标语言: {self.target_language}，将使用默认语言 zh")
            self.target_language = "zh"

        # 翻译提供商配置
        self.translation_provider = translation_settings.get(
            "translation_provider", "llm"
        )
        # 自定义翻译提示词：允许用户自定义翻译的提示词
        self.custom_translation_prompt = translation_settings.get(
            "custom_translation_prompt", ""
        )
    
    def _load_cache_settings(self):
        """加载和验证缓存设置"""
        cache_settings = self.config.get("cache_settings", {})
        self.enable_cache = bool(cache_settings.get("enable_cache", True))
        # 缓存过期时间：控制缓存结果的有效期
        self.cache_expire_time = max(
            5, min(10080, cache_settings.get("cache_expire_time", 1440))
        )
        # 最大缓存数量：控制缓存的最大条目数，避免内存占用过高
        self.max_cache_size = max(
            10, min(1000, cache_settings.get("max_cache_size", 100))
        )
    
    def _load_content_extraction_settings(self):
        """加载和验证内容提取设置"""
        content_extraction_settings = self.config.get("content_extraction_settings", {})
        self.enable_specific_extraction = bool(
            content_extraction_settings.get("enable_specific_extraction", False)
        )
        # 提取类型：指定要提取的内容类型
        extract_types_text = content_extraction_settings.get(
            "extract_types", "title\ncontent"
        )
        
        # 使用辅助方法处理提取类型
        self.extract_types = self._parse_extract_types(extract_types_text)
        self.extract_types = self._validate_extract_types(self.extract_types)
        self.extract_types = self._ensure_minimal_extract_types(self.extract_types)
        self.extract_types = self._add_required_extract_types(self.extract_types)
    
    def _load_recall_settings(self):
        """加载和验证撤回设置"""
        recall_settings = self.config.get("recall_settings", {})
        # 是否启用自动撤回功能
        self.enable_recall = bool(recall_settings.get("enable_recall", True))
        # 撤回延迟时间：设置合理的范围，避免过短或过长
        self.recall_time = max(0, min(120, recall_settings.get("recall_time", 10)))
    
    def _init_cache_manager(self):
        """初始化缓存管理器"""
        self.cache_manager = CacheManager(
            max_size=self.max_cache_size, expire_time=self.cache_expire_time
        )
    
    def _init_web_analyzer(self):
        """初始化网页分析器"""
        self.analyzer = WebAnalyzer(
            max_content_length=self.max_content_length,
            timeout=self.timeout,
            user_agent=self.user_agent,
            proxy=self.proxy,
            retry_count=self.retry_count,
            retry_delay=self.retry_delay,
        )

    def _parse_domain_list(self, domain_text: str) -> List[str]:
        """将多行域名文本转换为Python列表

        处理配置中定义的域名列表，支持：
        - 每行一个域名的格式
        - 自动去除空行和前后空白字符
        - 支持域名通配符（如*.example.com）

        Args:
            domain_text: 包含域名的多行文本字符串

        Returns:
            解析后的域名列表，已清理无效内容
        """
        if not domain_text:
            return []
        domains = [
            domain.strip() for domain in domain_text.split("\n") if domain.strip()
        ]
        return domains

    def _parse_group_list(self, group_text: str) -> List[str]:
        """将多行群聊ID文本转换为Python列表

        处理配置中定义的群聊黑名单，支持：
        - 每行一个群聊ID的格式
        - 自动去除空行和前后空白字符
        - 支持数字和字符串类型的群聊ID

        Args:
            group_text: 包含群聊ID的多行文本字符串

        Returns:
            解析后的群聊ID列表，已清理无效内容
        """
        if not group_text:
            return []
        groups = [group.strip() for group in group_text.split("\n") if group.strip()]
        return groups

    def _is_group_blacklisted(self, group_id: str) -> bool:
        """检查指定群聊是否在黑名单中

        群聊黑名单功能可以控制哪些群聊不能使用插件，
        适用于需要限制插件使用范围的场景。

        Args:
            group_id: 群聊ID，可以是字符串或数字

        Returns:
            True表示在黑名单中（禁止使用），False表示不在黑名单中（允许使用）
        """
        if not group_id or not self.group_blacklist:
            return False
        return group_id in self.group_blacklist

    def _is_domain_allowed(self, url: str) -> bool:
        """检查指定URL的域名是否允许访问

        根据配置的允许和禁止域名列表，判断URL是否可以访问，
        支持灵活的访问控制策略：

        访问规则（优先级从高到低）：
        1. 如果域名在禁止列表中，直接拒绝访问
        2. 如果允许列表不为空，只有在列表中的域名才允许访问
        3. 如果允许列表为空，则允许所有未被禁止的域名

        Args:
            url: 要检查的完整URL

        Returns:
            True表示允许访问，False表示禁止访问
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 首先检查是否在禁止列表中
            if self.blocked_domains:
                for blocked_domain in self.blocked_domains:
                    if blocked_domain.lower() in domain:
                        return False

            # 然后检查是否在允许列表中（如果允许列表不为空）
            if self.allowed_domains:
                for allowed_domain in self.allowed_domains:
                    if allowed_domain.lower() in domain:
                        return True
                return False  # 允许列表不为空，但域名不在其中，拒绝访问

            return True  # 允许列表为空，允许所有未被禁止的域名
        except Exception:
            return False

    @filter.command("网页分析", alias={"分析", "总结", "web", "analyze"})
    async def analyze_webpage(self, event: AstrMessageEvent):
        """手动触发网页分析命令

        这是插件的核心命令，允许用户手动指定要分析的网页链接，
        支持多种命令别名，方便不同使用习惯的用户。

        📋 用法示例：
        - `/网页分析 https://example.com` - 分析单个链接
        - `/分析 https://example.com https://test.com` - 分析多个链接
        - `/总结 https://example.com` - 使用别名命令

        🔧 功能特性：
        - 支持同时分析多个网页链接
        - 自动验证URL格式正确性
        - 根据域名黑白名单过滤链接
        - 异步处理，不阻塞其他操作
        - 支持各种输出格式

        Args:
            event: 消息事件对象，包含消息内容和上下文信息
        """
        message_text = event.message_str

        # 从消息中提取所有URL
        urls = self.analyzer.extract_urls(message_text)
        if not urls:
            yield event.plain_result(
                "请提供要分析的网页链接，例如：/网页分析 https://example.com"
            )
            return

        # 验证URL格式是否正确，并规范化URL
        valid_urls = [self.analyzer.normalize_url(url) for url in urls if self.analyzer.is_valid_url(url)]
        # 去重，避免重复分析相同URL
        valid_urls = list(set(valid_urls))
        if not valid_urls:
            yield event.plain_result("无效的URL链接，请检查格式是否正确")
            return

        # 过滤掉不允许访问的域名
        allowed_urls = [url for url in valid_urls if self._is_domain_allowed(url)]
        if not allowed_urls:
            yield event.plain_result("所有域名都不在允许访问的列表中，或已被禁止访问")
            return

        # 发送处理提示消息，告知用户正在分析
        if len(allowed_urls) == 1:
            message = f"正在分析网页: {allowed_urls[0]}"
        else:
            message = f"正在分析{len(allowed_urls)}个网页链接..."
        
        # 直接调用发送方法，不使用yield
        await self._send_processing_message(event, message)

        # 批量处理所有允许访问的URL
        async for result in self._batch_process_urls(event, allowed_urls):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_detect_urls(self, event: AstrMessageEvent):
        """自动检测消息中的URL链接并进行分析

        这个方法实现了插件的自动分析功能，无需用户手动调用命令，
        只要发送包含网页链接的消息，插件就会自动进行分析。

        🚦 自动分析规则：
        1. 仅当配置中auto_analyze为True时启用
        2. 智能跳过命令消息，避免重复处理
        3. 跳过包含网页分析相关指令的消息
        4. 跳过在黑名单中的群聊消息
        5. 仅处理格式正确的URL
        6. 遵守域名黑白名单限制

        ✨ 优势：
        - 提升用户体验，无需记忆命令
        - 支持所有消息类型（私聊、群聊）
        - 智能过滤，避免误触发
        - 与手动分析使用相同的核心逻辑

        Args:
            event: 消息事件对象，包含消息内容和上下文信息
        """
        # 检查是否启用自动分析功能
        if not self.auto_analyze:
            return

        # 检查是否为指令调用，避免重复处理
        message_text = event.message_str.strip()

        # 方法1：跳过以/开头的指令消息
        if message_text.startswith("/"):
            logger.info("检测到指令调用，跳过自动分析")
            return

        # 方法2：检查事件是否有command属性（指令调用时会有）
        if hasattr(event, "command"):
            logger.info("检测到command属性，跳过自动分析")
            return

        # 方法3：检查原始消息中是否包含网页分析相关指令关键字
        raw_message = None
        if hasattr(event, "raw_message"):
            raw_message = str(event.raw_message)
        elif hasattr(event, "message_obj"):
            raw_message = str(event.message_obj)

        if raw_message:
            # 检查是否包含网页分析相关指令
            command_keywords = ["网页分析", "/分析", "/总结", "/web", "/analyze"]
            for keyword in command_keywords:
                if keyword in raw_message:
                    logger.info(f"检测到指令关键字 {keyword}，跳过自动分析")
                    return

        # 检查群聊是否在黑名单中（仅群聊消息）
        group_id = None

        # 方法1：从事件对象直接获取群聊ID
        if hasattr(event, "group_id") and event.group_id:
            group_id = event.group_id
        # 方法2：从消息对象获取群聊ID
        elif (
            hasattr(event, "message_obj")
            and hasattr(event.message_obj, "group_id")
            and event.message_obj.group_id
        ):
            group_id = event.message_obj.group_id
        # 方法3：从原始消息获取群聊ID
        elif (
            hasattr(event, "raw_message")
            and hasattr(event.raw_message, "group_id")
            and event.raw_message.group_id
        ):
            group_id = event.raw_message.group_id

        # 群聊在黑名单中时静默忽略，不进行任何处理
        if group_id and self._is_group_blacklisted(group_id):
            return

        # 从消息中提取所有URL
        urls = self.analyzer.extract_urls(message_text)
        if not urls:
            return  # 没有URL，不处理

        # 验证URL格式是否正确，并规范化URL
        valid_urls = [self.analyzer.normalize_url(url) for url in urls if self.analyzer.is_valid_url(url)]
        # 去重，避免重复分析相同URL
        valid_urls = list(set(valid_urls))
        if not valid_urls:
            return  # 没有有效URL，不处理

        # 过滤掉不允许访问的域名
        allowed_urls = [url for url in valid_urls if self._is_domain_allowed(url)]
        if not allowed_urls:
            return  # 没有允许访问的URL，不处理

        # 发送处理提示消息，告知用户正在分析
        if len(allowed_urls) == 1:
            message = f"检测到网页链接，正在分析: {allowed_urls[0]}"
        else:
            message = f"检测到{len(allowed_urls)}个网页链接，正在分析..."
        
        # 直接调用发送方法，不使用yield
        await self._send_processing_message(event, message)

        # 批量处理所有允许访问的URL
        async for result in self._batch_process_urls(event, allowed_urls):
            yield result

    async def _process_single_url(
        self, event: AstrMessageEvent, url: str, analyzer: WebAnalyzer
    ) -> dict:
        """处理单个网页URL，生成完整的分析结果

        这是处理单个网页链接的核心方法，包含完整的分析流程：

        🔄 处理流程：
        1. 🔍 检查缓存，避免重复分析
        2. 🌐 抓取网页HTML内容
        3. 📝 提取结构化的网页内容
        4. 🌍 翻译内容（如果启用了翻译功能）
        5. 🧠 调用大语言模型(LLM)进行智能分析
        6. 📊 提取特定类型内容（图片、链接、表格等）
        7. 📸 捕获网页截图（如果启用了截图功能）
        8. 💾 更新缓存，保存分析结果
        9. 📤 返回完整的分析结果

        Args:
            event: 消息事件对象，包含上下文信息
            url: 要分析的网页URL
            analyzer: WebAnalyzer实例，用于网页抓取和分析

        Returns:
            包含分析结果的字典：
            {
                'url': 分析的URL地址,
                'result': 格式化的分析结果文本,
                'screenshot': 网页截图二进制数据（如果启用）
            }
        """
        try:
            # 检查缓存，避免重复分析
            cached_result = self._check_cache(url)
            if cached_result:
                logger.info(f"使用缓存结果: {url}")
                return cached_result

            # 抓取网页HTML内容
            html = await analyzer.fetch_webpage(url)
            if not html:
                return {
                    "url": url,
                    "result": f"❌ 无法抓取网页内容: {url}",
                    "screenshot": None,
                }

            # 从HTML中提取结构化内容
            content_data = analyzer.extract_content(html, url)
            if not content_data:
                return {
                    "url": url,
                    "result": f"❌ 无法解析网页内容: {url}",
                    "screenshot": None,
                }

            # 如果启用了翻译功能，先翻译内容
            if self.enable_translation:
                translated_content = await self._translate_content(
                    event, content_data["content"]
                )
                # 创建翻译后的内容数据副本
                translated_content_data = content_data.copy()
                translated_content_data["content"] = translated_content
                # 调用LLM进行分析（使用翻译后的内容）
                analysis_result = await self.analyze_with_llm(
                    event, translated_content_data
                )
            else:
                # 直接调用LLM进行分析
                analysis_result = await self.analyze_with_llm(event, content_data)

            # 如果启用了特定内容提取，提取额外信息
            specific_content = self._extract_specific_content(html, url)
            if specific_content:
                # 在分析结果中添加特定内容
                specific_content_str = "\n\n**特定内容提取**\n"

                # 添加图片链接（如果有）
                if "images" in specific_content and specific_content["images"]:
                    specific_content_str += (
                        f"\n📷 图片链接 ({len(specific_content['images'])}):\n"
                    )
                    for img_url in specific_content["images"]:
                        specific_content_str += f"- {img_url}\n"

                # 添加相关链接（如果有，最多显示5个）
                if "links" in specific_content and specific_content["links"]:
                    specific_content_str += (
                        f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                    )
                    for link in specific_content["links"][:5]:
                        specific_content_str += f"- [{link['text']}]({link['url']})\n"

                # 添加代码块（如果有，最多显示2个）
                if (
                    "code_blocks" in specific_content
                    and specific_content["code_blocks"]
                ):
                    specific_content_str += (
                        f"\n💻 代码块 ({len(specific_content['code_blocks'])}):\n"
                    )
                    for i, code in enumerate(specific_content["code_blocks"][:2]):
                        specific_content_str += f"```\n{code}\n```\n"

                # 添加元信息（如果有）
                if "meta" in specific_content and specific_content["meta"]:
                    meta_info = specific_content["meta"]
                    specific_content_str += "\n📋 元信息:\n"
                    for key, value in meta_info.items():
                        if value:
                            specific_content_str += f"- {key}: {value}\n"

                # 将特定内容添加到分析结果中
                analysis_result += specific_content_str

            # 根据发送内容类型决定是否需要生成截图
            screenshot = None
            if self.enable_screenshot and self.send_content_type != "analysis_only":
                screenshot = await analyzer.capture_screenshot(
                    url,
                    quality=self.screenshot_quality,
                    width=self.screenshot_width,
                    height=self.screenshot_height,
                    full_page=self.screenshot_full_page,
                    wait_time=self.screenshot_wait_time,
                    format=self.screenshot_format,
                )

            # 准备最终的结果数据
            result_data = {
                "url": url,
                "result": analysis_result,
                "screenshot": screenshot,
            }

            # 更新缓存，保存分析结果
            self._update_cache(url, result_data)

            return result_data
        except Exception as e:
            # 捕获所有异常，确保方法始终返回有效结果
            logger.error(f"处理URL {url} 时出错: {e}")
            return {
                "url": url,
                "result": f"❌ 处理URL时出错: {url}\n错误信息: {str(e)}",
                "screenshot": None,
            }

    async def _batch_process_urls(self, event: AstrMessageEvent, urls: List[str]):
        """批量处理多个URL，实现高效的并发分析

        这个方法负责管理多个URL的并发处理，提高插件的处理效率，
        支持异步并发处理，避免阻塞等待单个URL分析完成。

        🔄 处理流程：
        1. 🚫 过滤掉正在处理的URL，避免重复分析
        2. 🎯 使用异步方式并发处理多个URL
        3. 📤 调用_send_analysis_result发送所有分析结果
        4. 🧹 确保URL处理完成后从处理队列中移除

        Args:
            event: 消息事件对象，用于生成响应
            urls: 要处理的URL列表
        """
        # 收集所有分析结果
        analysis_results = []

        # 过滤掉正在处理的URL，避免重复分析
        filtered_urls = []
        for url in urls:
            if url not in self.processing_urls:
                filtered_urls.append(url)
                # 添加到正在处理的集合中，防止重复处理
                self.processing_urls.add(url)
            else:
                logger.info(f"URL {url} 正在处理中，跳过重复分析")

        # 如果所有URL都正在处理中，直接返回
        if not filtered_urls:
            return

        try:
            # 创建WebAnalyzer实例，使用上下文管理器确保资源正确释放
            async with WebAnalyzer(
                self.max_content_length,
                self.timeout,
                self.user_agent,
                self.proxy,
                self.retry_count,
                self.retry_delay,
            ) as analyzer:
                # 使用asyncio.gather并发处理多个URL，提高效率
                import asyncio

                # 创建任务列表
                tasks = [
                    self._process_single_url(event, url, analyzer)
                    for url in filtered_urls
                ]
                # 并发执行所有任务
                analysis_results = await asyncio.gather(*tasks)

            # 发送所有分析结果
            async for result in self._send_analysis_result(event, analysis_results):
                yield result
        finally:
            # 无论处理成功还是失败，都要从处理集合中移除URL
            for url in filtered_urls:
                if url in self.processing_urls:
                    self.processing_urls.remove(url)

    async def analyze_with_llm(
        self, event: AstrMessageEvent, content_data: dict
    ) -> str:
        """调用大语言模型(LLM)进行智能内容分析和总结

        这是实现AI智能分析的核心方法，利用大语言模型对网页内容进行深度理解，
        支持灵活的配置和优化：

        🔧 功能特性：
        1. ✅ 检查LLM是否可用和启用
        2. 🤖 获取合适的LLM提供商
        3. 💬 构建优化的提示词（支持自定义提示词）
        4. 📝 调用LLM生成高质量分析结果
        5. 🎨 美化和格式化分析结果
        6. 🔄 LLM不可用时自动回退到基础分析

        Args:
            event: 消息事件对象，用于获取上下文信息
            content_data: 包含网页内容的结构化字典：
                {
                    'title': 网页标题,
                    'content': 网页正文内容,
                    'url': 网页URL地址
                }

        Returns:
            格式化的AI分析结果文本，包含标题、链接、分析内容等
        """
        try:
            title = content_data["title"]
            content = content_data["content"]
            url = content_data["url"]

            # 检查LLM是否可用和启用
            if not hasattr(self.context, "llm_generate") or not self.llm_enabled:
                # LLM不可用或未启用，使用基础分析
                return self.get_enhanced_analysis(content_data)

            # 优先使用配置的LLM提供商，如果没有配置则使用当前会话的模型
            provider_id = self.llm_provider
            if not provider_id:
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)

            if not provider_id:
                # 无法获取LLM提供商，使用基础分析
                return self.get_enhanced_analysis(content_data)

            # 构建优化的LLM提示词
            emoji_prefix = "每个要点用emoji图标标记" if self.enable_emoji else ""

            # 使用自定义提示词或默认提示词
            if self.custom_prompt:
                # 替换自定义提示词中的变量
                prompt = self.custom_prompt.format(
                    title=title,
                    url=url,
                    content=content,
                    max_length=self.max_summary_length,
                )
            else:
                # 默认提示词，包含详细的分析要求和格式要求
                prompt = f"""请对以下网页内容进行专业分析和智能总结：

**网页信息**
- 标题：{title}
- 链接：{url}

**网页内容**：
{content}

**分析要求**：
1. **核心摘要**：用50-100字概括网页的核心内容和主旨
2. **关键要点**：提取2-3个最重要的信息点或观点
3. **内容类型**：判断网页属于什么类型（新闻、教程、博客、产品介绍等）
4. **价值评估**：简要评价内容的价值和实用性
5. **适用人群**：说明适合哪些人群阅读

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{self.max_summary_length}字

请确保分析准确、全面且易于理解。"""

            # 使用当前会话的聊天模型ID调用大模型
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,  # 使用当前会话的聊天模型
                prompt=prompt,
            )

            if llm_resp and llm_resp.completion_text:
                # 美化LLM返回的结果
                analysis_text = llm_resp.completion_text.strip()

                # 限制摘要长度，避免结果过长
                if len(analysis_text) > self.max_summary_length:
                    analysis_text = analysis_text[: self.max_summary_length] + "..."

                # 添加标题和格式美化
                link_emoji = "🔗" if self.enable_emoji else ""
                title_emoji = "📝" if self.enable_emoji else ""

                formatted_result = "**AI智能网页分析报告**\n\n"
                formatted_result += f"{link_emoji} **分析链接**: {url}\n"
                formatted_result += f"{title_emoji} **网页标题**: {title}\n\n"
                formatted_result += "---\n\n"
                formatted_result += analysis_text
                formatted_result += "\n\n---\n"
                formatted_result += "*分析完成，希望对您有帮助！*"

                return formatted_result
            else:
                # LLM返回为空，使用基础分析
                return self.get_enhanced_analysis(content_data)

        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            # 如果LLM分析失败，返回错误信息
            return f"❌ LLM分析过程中出现错误: {str(e)}"

    def get_enhanced_analysis(self, content_data: dict) -> str:
        """增强版基础分析 - LLM不可用时的智能回退方案

        当LLM不可用或未启用时，提供可靠的基础分析功能，
        包含多种智能分析特性，确保插件在各种环境下都能正常工作：

        📊 分析内容：
        1. 🔢 内容统计（字符数、段落数、词数）
        2. 🧠 智能内容类型检测（新闻、教程、博客等）
        3. 🔍 提取关键句子作为内容摘要
        4. ⭐ 内容质量评估
        5. 🎨 美观的格式化输出

        ✨ 配置支持：
        - 根据配置显示/隐藏emoji
        - 根据配置显示/隐藏详细统计信息
        - 支持自定义格式

        Args:
            content_data: 包含网页内容的结构化字典：
                {
                    'title': 网页标题,
                    'content': 网页正文内容,
                    'url': 网页URL地址
                }

        Returns:
            格式化的基础分析结果文本，包含所有分析内容
        """
        title = content_data["title"]
        content = content_data["content"]
        url = content_data["url"]

        # 计算内容统计信息
        content_stats = self._calculate_content_statistics(content)
        
        # 智能检测内容类型
        content_type = self._detect_content_type(content)
        
        # 提取关键句子作为内容摘要
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        key_sentences = self._extract_key_sentences(paragraphs)
        
        # 评估内容质量
        quality_indicator = self._evaluate_content_quality(content_stats["char_count"])
        
        # 构建分析结果
        return self._build_analysis_result(
            title, url, content_type, quality_indicator, content_stats, paragraphs, key_sentences
        )
    
    def _calculate_content_statistics(self, content: str) -> dict:
        """计算内容统计信息
        
        Args:
            content: 网页正文内容
            
        Returns:
            包含字符数、词数的统计字典
        """
        char_count = len(content)
        word_count = len(content.split())
        return {
            "char_count": char_count,
            "word_count": word_count
        }
    
    def _detect_content_type(self, content: str) -> str:
        """智能检测内容类型
        
        Args:
            content: 网页正文内容
            
        Returns:
            检测到的内容类型字符串
        """
        content_lower = content.lower()
        
        content_type_rules = [
            ("新闻资讯", ["新闻", "报道", "消息", "时事"]),
            ("教程指南", ["教程", "指南", "教学", "步骤", "方法"]),
            ("个人博客", ["博客", "随笔", "日记", "个人", "观点"]),
            ("产品介绍", ["产品", "服务", "购买", "价格", "优惠"]),
            ("技术文档", ["技术", "开发", "编程", "代码", "API"])
        ]
        
        for type_name, keywords in content_type_rules:
            if any(keyword in content_lower for keyword in keywords):
                return type_name
        
        return "文章"
    
    def _extract_key_sentences(self, paragraphs: list) -> list:
        """提取关键句子作为内容摘要
        
        Args:
            paragraphs: 段落列表
            
        Returns:
            关键句子列表
        """
        # 提取前3个段落作为关键句子
        return paragraphs[:3]
    
    def _evaluate_content_quality(self, char_count: int) -> str:
        """评估内容质量
        
        Args:
            char_count: 内容字符数
            
        Returns:
            质量评估字符串
        """
        if char_count > 5000:
            return "内容详实"
        elif char_count > 1000:
            return "内容丰富"
        else:
            return "内容简洁"
    
    def _build_analysis_header(self) -> str:
        """构建分析结果的标题部分
        
        Returns:
            格式化的标题字符串
        """
        robot_emoji = "🤖" if self.enable_emoji else ""
        page_emoji = "📄" if self.enable_emoji else ""
        return f"{robot_emoji} **智能网页分析** {page_emoji}\n\n"
    
    def _build_basic_info(self, title: str, url: str, content_type: str, 
                         quality_indicator: str) -> str:
        """构建分析结果的基本信息部分
        
        Args:
            title: 网页标题
            url: 网页URL
            content_type: 内容类型
            quality_indicator: 质量评估
            
        Returns:
            格式化的基本信息字符串
        """
        info_emoji = "📝" if self.enable_emoji else ""
        
        basic_info = []
        if self.enable_emoji:
            basic_info.append(f"**{info_emoji} 基本信息**\n")
        else:
            basic_info.append("**基本信息**\n")
        
        basic_info.append(f"- **标题**: {title}\n")
        basic_info.append(f"- **链接**: {url}\n")
        basic_info.append(f"- **内容类型**: {content_type}\n")
        basic_info.append(f"- **质量评估**: {quality_indicator}\n\n")
        
        return "".join(basic_info)
    
    def _build_statistics_info(self, content_stats: dict, paragraphs: list) -> str:
        """构建分析结果的统计信息部分
        
        Args:
            content_stats: 内容统计信息
            paragraphs: 段落列表
            
        Returns:
            格式化的统计信息字符串
        """
        if not self.enable_statistics:
            return ""
        
        stats_emoji = "📊" if self.enable_emoji else ""
        
        stats_info = []
        if self.enable_emoji:
            stats_info.append(f"**{stats_emoji} 内容统计**\n")
        else:
            stats_info.append("**内容统计**\n")
        
        stats_info.append(f"- 字符数: {content_stats['char_count']:,}\n")
        stats_info.append(f"- 段落数: {len(paragraphs)}\n")
        stats_info.append(f"- 词数: {content_stats['word_count']:,}\n\n")
        
        return "".join(stats_info)
    
    def _build_content_summary(self, key_sentences: list) -> str:
        """构建分析结果的内容摘要部分
        
        Args:
            key_sentences: 关键句子列表
            
        Returns:
            格式化的内容摘要字符串
        """
        search_emoji = "🔍" if self.enable_emoji else ""
        
        summary_info = []
        if self.enable_emoji:
            summary_info.append(f"**{search_emoji} 内容摘要**\n")
        else:
            summary_info.append("**内容摘要**\n")
        
        # 格式化关键句子
        formatted_sentences = []
        for sentence in key_sentences:
            truncated = sentence[:100] + ('...' if len(sentence) > 100 else '')
            formatted_sentences.append(f"• {truncated}")
        
        summary_info.append(f"{chr(10).join(formatted_sentences)}\n\n")
        return "".join(summary_info)
    
    def _build_analysis_note(self) -> str:
        """构建分析结果的分析说明部分
        
        Returns:
            格式化的分析说明字符串
        """
        light_emoji = "💡" if self.enable_emoji else ""
        
        note_info = []
        if self.enable_emoji:
            note_info.append(f"**{light_emoji} 分析说明**\n")
        else:
            note_info.append("**分析说明**\n")
        
        note_info.append("此分析基于网页内容提取，如需更深入的AI智能分析，请确保AstrBot已正确配置LLM功能。\n\n")
        note_info.append("*提示：完整内容预览请查看原始网页*")
        
        return "".join(note_info)
    
    def _build_analysis_result(self, title: str, url: str, content_type: str, 
                              quality_indicator: str, content_stats: dict, 
                              paragraphs: list, key_sentences: list) -> str:
        """构建最终的分析结果
        
        Args:
            title: 网页标题
            url: 网页URL
            content_type: 内容类型
            quality_indicator: 质量评估
            content_stats: 内容统计信息
            paragraphs: 段落列表
            key_sentences: 关键句子列表
            
        Returns:
            格式化的分析结果字符串
        """
        # 构建分析结果
        result_parts = []
        result_parts.append(self._build_analysis_header())
        result_parts.append(self._build_basic_info(title, url, content_type, quality_indicator))
        result_parts.append(self._build_statistics_info(content_stats, paragraphs))
        result_parts.append(self._build_content_summary(key_sentences))
        result_parts.append(self._build_analysis_note())
        
        return "".join(result_parts)
    
    def _parse_extract_types(self, extract_types_text: str) -> list:
        """解析提取类型文本为列表
        
        将多行文本转换为提取类型列表，自动去除空行和前后空白字符
        
        Args:
            extract_types_text: 包含提取类型的多行文本字符串
            
        Returns:
            解析后的提取类型列表
        """
        if not extract_types_text:
            return []
        return [t.strip() for t in extract_types_text.split("\n") if t.strip()]
    
    def _validate_extract_types(self, extract_types: list) -> list:
        """验证提取类型的有效性
        
        检查提取类型是否在有效列表中，过滤掉无效类型
        
        Args:
            extract_types: 当前的提取类型列表
            
        Returns:
            过滤后的有效提取类型列表
        """
        valid_extract_types = [
            "title",
            "content",
            "images",
            "links",
            "tables",
            "lists",
            "code",
            "meta",
        ]
        invalid_types = [t for t in extract_types if t not in valid_extract_types]
        if invalid_types:
            logger.warning(
                f"无效的提取类型: {', '.join(invalid_types)}，将忽略这些类型"
            )
        return [t for t in extract_types if t in valid_extract_types]
    
    def _ensure_minimal_extract_types(self, extract_types: list) -> list:
        """确保至少有一个提取类型
        
        当提取类型列表为空时，设置默认提取类型
        
        Args:
            extract_types: 当前的提取类型列表
            
        Returns:
            至少包含一个提取类型的列表
        """
        if not extract_types:
            return ["title", "content"]
        return extract_types
    
    def _add_required_extract_types(self, extract_types: list) -> list:
        """添加必要的提取类型
        
        确保meta类型被添加到提取类型列表中，用于提取网页元信息
        
        Args:
            extract_types: 当前的提取类型列表
            
        Returns:
            更新后的提取类型列表
        """
        if "meta" not in extract_types:
            extract_types.append("meta")
        return extract_types
    
    async def _auto_recall_message(self, bot, message_id: int, recall_time: int) -> None:
        """
        自动撤回消息
        
        参数:
            bot: 机器人实例，用于发送撤回请求
            message_id: 要撤回的消息ID
            recall_time: 延迟撤回的时间（秒）
        """
        try:
            import asyncio
            
            # 等待指定时间
            if recall_time > 0:
                await asyncio.sleep(recall_time)
            
            # 调用bot的delete_msg方法撤回消息
            await bot.delete_msg(message_id=message_id)
            logger.debug(f"已撤回消息: {message_id}")
        except Exception as e:
            logger.error(f"撤回消息失败: {e}")
    
    async def _send_processing_message(self, event: AstrMessageEvent, message: str) -> None:
        """
        发送正在分析的消息并设置自动撤回
        
        参数:
            event: 消息事件对象，用于获取bot实例和消息上下文
            message: 要发送的消息内容
        """
        import asyncio
        
        # 获取bot实例
        bot = event.bot
        
        # 直接调用bot的发送消息方法，获取消息ID
        try:
            # 根据事件类型选择发送方法
            send_result = None
            group_id = None
            user_id = None
            
            # 方法1：使用AiocqhttpMessageEvent的方法获取
            if hasattr(event, 'get_group_id'):
                group_id = event.get_group_id()
            if hasattr(event, 'get_sender_id'):
                user_id = event.get_sender_id()
            
            # 方法2：判断是否为私聊
            is_private = False
            if hasattr(event, 'is_private_chat'):
                is_private = event.is_private_chat()
            
            # 发送消息
            if group_id:
                # 群聊消息
                send_result = await bot.send_group_msg(
                    group_id=group_id,
                    message=message
                )
                logger.debug(f"发送群聊处理消息: {message} 到群 {group_id}")
            elif user_id or is_private:
                # 私聊消息
                if not user_id and hasattr(event, 'get_sender_id'):
                    user_id = event.get_sender_id()
                
                if user_id:
                    send_result = await bot.send_private_msg(
                        user_id=user_id,
                        message=message
                    )
                    logger.debug(f"发送私聊处理消息: {message} 到用户 {user_id}")
                else:
                    # 无法获取user_id，使用原始方式发送
                    logger.warning(f"无法获取user_id，使用原始方式发送消息: {message}")
                    response = event.plain_result(message)
                    if hasattr(event, 'send'):
                        await event.send(response)
                    return
            else:
                # 无法确定消息类型，使用原始方式发送并记录详细信息
                logger.error(f"无法确定消息类型，event类型: {type(event)}, event方法: get_group_id={hasattr(event, 'get_group_id')}, get_sender_id={hasattr(event, 'get_sender_id')}, is_private_chat={hasattr(event, 'is_private_chat')}")
                # 尝试使用event.plain_result发送，虽然无法获取message_id
                response = event.plain_result(message)
                # 使用event的send方法发送
                if hasattr(event, 'send'):
                    await event.send(response)
                return
            
            # 检查send_result是否包含message_id
            message_id = None
            if isinstance(send_result, dict):
                message_id = send_result.get('message_id')
            elif hasattr(send_result, 'message_id'):
                message_id = send_result.message_id
            
            logger.debug(f"发送处理消息成功，message_id: {message_id}")
            
            # 如果获取到message_id且启用了自动撤回，创建撤回任务
            if message_id and self.enable_recall:
                logger.info(f"创建撤回任务，message_id: {message_id}，延迟: {self.recall_time}秒")
                
                async def _recall_task():
                    try:
                        await asyncio.sleep(self.recall_time)
                        await bot.delete_msg(message_id=message_id)
                        logger.info(f"已撤回消息: {message_id}")
                    except Exception as e:
                        logger.error(f"撤回消息失败: {e}")
                
                task = asyncio.create_task(_recall_task())
                
                # 将任务添加到列表中管理
                self.recall_tasks.append(task)
                
                # 添加完成回调，从列表中移除已完成的任务
                def _remove_task(t):
                    try:
                        self.recall_tasks.remove(t)
                    except ValueError:
                        pass
                
                task.add_done_callback(_remove_task)
        except Exception as e:
            logger.error(f"发送处理消息或设置撤回失败: {e}")

    @filter.command("web_config", alias={"网页分析配置", "网页分析设置"})
    async def show_config(self, event: AstrMessageEvent):
        """显示当前插件的详细配置信息

        这个命令允许用户查看插件的所有配置项，方便了解插件的当前状态和设置，
        支持多种命令别名，方便用户调用。

        📋 显示内容：
        - 🛠️  基本设置（超时、重试、自动分析等）
        - 🚫  域名控制（允许/禁止列表）
        - 👥  群聊控制（黑名单）
        - 📊  分析设置（emoji、统计、摘要长度等）
        - 🧠  LLM配置（提供商、自定义提示词等）
        - 🌐  翻译设置（自动翻译、目标语言等）
        - 💾  缓存设置（过期时间、最大数量等）
        - 📋  内容提取设置（提取类型等）

        📝 使用示例：
        - `/web_config` - 查看配置
        - `/网页分析配置` - 中文命令
        - `/网页分析设置` - 中文别名

        Args:
            event: 消息事件对象，用于生成响应
        """
        config_info = f"""**网页分析插件配置信息**

**基本设置**
- 最大内容长度: {self.max_content_length} 字符
- 请求超时时间: {self.timeout} 秒
- LLM智能分析: {"✅ 已启用" if self.llm_enabled else "❌ 已禁用"}
- 自动分析链接: {"✅ 已启用" if self.auto_analyze else "❌ 已禁用"}
- 合并转发功能(群聊): {"✅ 已启用" if self.merge_forward_enabled["group"] else "❌ 已禁用"}
- 合并转发功能(私聊): {"✅ 已启用" if self.merge_forward_enabled["private"] else "❌ 已禁用"}
- 合并转发包含截图: {"✅ 已启用" if self.merge_forward_enabled["include_screenshot"] else "❌ 已禁用"}

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
- 截取整页: {"✅ 已启用" if self.screenshot_full_page else "❌ 已禁用"}
- 截图等待时间: {self.screenshot_wait_time}ms

**LLM配置**
- 指定提供商: {self.llm_provider if self.llm_provider else "使用会话默认"}
- 自定义提示词: {"✅ 已启用" if self.custom_prompt else "❌ 未设置"}

**翻译设置**
- 启用网页翻译: {"✅ 已启用" if self.enable_translation else "❌ 已禁用"}
- 目标语言: {self.target_language}
- 翻译提供商: {self.translation_provider}
- 自定义翻译提示词: {"✅ 已启用" if self.custom_translation_prompt else "❌ 未设置"}

**缓存设置**
- 启用结果缓存: {"✅ 已启用" if self.enable_cache else "❌ 已禁用"}
- 缓存过期时间: {self.cache_expire_time} 分钟
- 最大缓存数量: {self.max_cache_size} 个

**内容提取设置**
- 启用特定内容提取: {"✅ 已启用" if self.enable_specific_extraction else "❌ 已禁用"}
- 提取内容类型: {", ".join(self.extract_types)}

*提示: 如需修改配置，请在AstrBot管理面板中编辑插件配置*"""

        yield event.plain_result(config_info)

    @filter.command("test_merge", alias={"测试合并转发", "测试转发"})
    async def test_merge_forward(self, event: AstrMessageEvent):
        """测试合并转发功能

        这个命令用于测试插件的合并转发功能，仅在群聊环境中可用，
        方便用户验证合并转发功能是否正常工作。

        📝 使用示例：
        - `/test_merge` - 测试合并转发
        - `/测试合并转发` - 中文命令
        - `/测试转发` - 中文别名

        ✨ 功能说明：
        - 创建测试用的合并转发消息
        - 包含标题节点和两个内容节点
        - 演示合并转发的基本用法和效果
        - 验证合并转发功能是否正常工作

        Args:
            event: 消息事件对象，用于生成测试消息
        """
        from astrbot.api.message_components import Node, Plain, Nodes

        # 检查是否为群聊消息，合并转发仅支持群聊
        group_id = None
        if hasattr(event, "group_id") and event.group_id:
            group_id = event.group_id
        elif (
            hasattr(event, "message_obj")
            and hasattr(event.message_obj, "group_id")
            and event.message_obj.group_id
        ):
            group_id = event.message_obj.group_id

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
        """管理群聊黑名单

        这个命令允许用户管理插件的群聊黑名单，控制哪些群聊不能使用插件，
        支持多种操作，包括查看、添加、移除和清空黑名单。

        📋 命令用法：
        1. 🔍 查看黑名单：`/group_blacklist`
        2. ➕ 添加群聊：`/group_blacklist add <群号>`
        3. ➖ 移除群聊：`/group_blacklist remove <群号>`
        4. 🗑️ 清空黑名单：`/group_blacklist clear`

        🔤 支持别名：
        - `/群黑名单`
        - `/黑名单`

        Args:
            event: 消息事件对象，用于获取命令参数和生成响应
        """
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("web_cache", alias={"网页缓存", "清理缓存"})
    async def manage_cache(self, event: AstrMessageEvent):
        """管理插件的网页分析结果缓存

        这个命令允许用户管理插件的缓存，包括查看缓存状态和清空缓存，
        方便用户控制缓存的使用和释放存储空间。

        📋 命令用法：
        1. 🔍 查看缓存状态：`/web_cache`
        2. 🗑️ 清空所有缓存：`/web_cache clear`

        🔤 支持别名：
        - `/网页缓存`
        - `/清理缓存`

        💡 缓存说明：
        - ⏰ 缓存有效期：由配置中的`cache_expire_time`决定
        - 📊 最大缓存数量：由配置中的`max_cache_size`决定
        - 📦 缓存内容：包括网页分析结果和截图数据

        Args:
            event: 消息事件对象，用于获取命令参数和生成响应
        """
        # 解析命令参数
        message_parts = event.message_str.strip().split()

        # 如果没有参数，显示当前缓存状态
        if len(message_parts) <= 1:
            cache_stats = self.cache_manager.get_stats()
            cache_info = "**当前缓存状态**\n\n"
            cache_info += f"- 缓存总数: {cache_stats['total']} 个\n"
            cache_info += f"- 有效缓存: {cache_stats['valid']} 个\n"
            cache_info += f"- 过期缓存: {cache_stats['expired']} 个\n"
            cache_info += f"- 缓存过期时间: {self.cache_expire_time} 分钟\n"
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

    @filter.command("web_export", alias={"导出分析结果", "网页导出"})
    async def export_analysis_result(self, event: AstrMessageEvent):
        """导出网页分析结果

        这个命令允许用户导出网页分析结果，支持多种格式和导出范围，
        方便用户保存和分享分析结果。

        📋 命令用法：
        1. 📄 导出单个URL：`/web_export https://example.com [格式]`
        2. 📚 导出所有缓存：`/web_export all [格式]`

        📁 支持的格式：
        - 📝 `md/markdown`：Markdown格式，适合阅读和编辑
        - 📊 `json`：JSON格式，适合程序处理
        - 📄 `txt`：纯文本格式，适合简单查看

        🔤 支持别名：
        - `/导出分析结果`
        - `/网页导出`

        ✨ 功能特点：
        - 🔄 支持导出单个URL的分析结果
        - 📚 支持导出所有缓存的分析结果
        - 📤 导出文件会自动发送给用户
        - 🔍 如果缓存中没有结果，会先进行分析
        - 📦 支持多种导出格式，满足不同需求

        Args:
            event: 消息事件对象，用于获取命令参数和生成响应
        """
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
            cached_result = self._check_cache(url)
            if cached_result:
                export_results.append({"url": url, "result": cached_result})
            else:
                # 如果缓存中没有，先进行分析
                yield event.plain_result("缓存中没有该URL的分析结果，正在进行分析...")

                # 抓取并分析网页
                async with WebAnalyzer(
                    self.max_content_length,
                    self.timeout,
                    self.user_agent,
                    self.proxy,
                    self.retry_count,
                    self.retry_delay,
                ) as analyzer:
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
                        analysis_result = await self.analyze_with_llm(
                            event, translated_content_data
                        )
                    else:
                        analysis_result = await self.analyze_with_llm(
                            event, content_data
                        )

                    # 提取特定内容（如果启用）
                    specific_content = self._extract_specific_content(html, url)
                    if specific_content:
                        # 在分析结果中添加特定内容
                        specific_content_str = "\n\n**特定内容提取**\n"

                        if "images" in specific_content and specific_content["images"]:
                            specific_content_str += (
                                f"\n📷 图片链接 ({len(specific_content['images'])}):\n"
                            )
                            for img_url in specific_content["images"]:
                                specific_content_str += f"- {img_url}\n"

                        if "links" in specific_content and specific_content["links"]:
                            specific_content_str += (
                                f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                            )
                            for link in specific_content["links"][
                                :5
                            ]:  # 只显示前5个链接
                                specific_content_str += (
                                    f"- [{link['text']}]({link['url']})\n"
                                )

                        if (
                            "code_blocks" in specific_content
                            and specific_content["code_blocks"]
                        ):
                            specific_content_str += f"\n💻 代码块 ({len(specific_content['code_blocks'])}):\n"
                            for i, code in enumerate(
                                specific_content["code_blocks"][:2]
                            ):  # 只显示前2个代码块
                                specific_content_str += f"```\n{code}\n```\n"

                        analysis_result += specific_content_str

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
            import os
            import json
            import time

            # 创建data目录（如果不存在）
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)

            # 生成文件名
            timestamp = int(time.time())
            if len(export_results) == 1:
                # 单个URL导出，使用域名作为文件名的一部分
                url = export_results[0]["url"]
                from urllib.parse import urlparse

                parsed = urlparse(url)
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
            from astrbot.api.message_components import Plain, File

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

    def _save_group_blacklist(self):
        """保存群聊黑名单到配置文件

        该方法负责将群聊黑名单列表转换为文本格式，并保存到配置中

        功能说明：
        - 将群聊ID列表转换为换行分隔的文本
        - 更新配置文件中的group_settings.group_blacklist字段
        - 保存配置更改
        - 处理保存过程中可能出现的异常
        """
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

    def _check_cache(self, url: str) -> dict:
        """检查指定URL的缓存是否存在且有效

        Args:
            url: 要检查缓存的网页URL

        Returns:
            - 如果缓存存在且有效，返回缓存的分析结果
            - 如果缓存不存在或无效，返回None
        """
        if not self.enable_cache:
            return None
        
        # 规范化URL，统一格式
        normalized_url = self.analyzer.normalize_url(url)
        return self.cache_manager.get(normalized_url)

    def _update_cache(self, url: str, result: dict):
        """更新指定URL的缓存

        Args:
            url: 要更新缓存的网页URL
            result: 包含分析结果的字典，格式与_check_cache返回值一致
        """
        if not self.enable_cache:
            return
        
        # 规范化URL，统一格式
        normalized_url = self.analyzer.normalize_url(url)
        self.cache_manager.set(normalized_url, result)

    def _clean_cache(self):
        """清理过期缓存

        注意：缓存管理器会自动清理过期缓存，因此该方法目前留空
        如需手动清理，可以在此方法中添加相应逻辑
        """
        # 缓存管理器会自动清理过期缓存，这里留空即可
        pass

    async def _translate_content(self, event: AstrMessageEvent, content: str) -> str:
        """翻译网页内容

        该方法负责调用LLM对网页内容进行翻译

        Args:
            event: 消息事件对象
            content: 要翻译的网页内容

        Returns:
            - 如果翻译成功，返回翻译后的内容
            - 如果翻译失败或未启用翻译，返回原始内容
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
                prompt = f"请将以下内容翻译成{self.target_language}语言，保持原文意思不变，语言流畅自然：\n\n{content}"

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

    def _extract_specific_content(self, html: str, url: str) -> dict:
        """提取特定类型的内容

        该方法负责从HTML中提取特定类型的内容，如图片、链接、代码块等

        Args:
            html: 网页HTML内容
            url: 网页URL

        Returns:
            - 如果提取成功，返回包含特定内容的字典
            - 如果提取失败或未启用特定内容提取，返回空字典
        """
        if not self.enable_specific_extraction:
            return {}

        try:
            # 直接使用已有analyzer实例，避免重复创建
            return self.analyzer.extract_specific_content(html, url, self.extract_types)
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            return {}

    async def _send_analysis_result(self, event, analysis_results):
        """发送分析结果，根据配置决定是否使用合并转发

        该方法负责将分析结果发送给用户，支持普通消息和合并转发两种方式

        Args:
            event: 消息事件对象
            analysis_results: 包含所有分析结果的列表
        """
        try:
            from astrbot.api.message_components import Node, Plain, Nodes, Image
            import tempfile
            import os

            # 检查是否为群聊消息且合并转发功能已启用
            group_id = None
            if hasattr(event, "group_id") and event.group_id:
                group_id = event.group_id
            elif (
                hasattr(event, "message_obj")
                and hasattr(event.message_obj, "group_id")
                and event.message_obj.group_id
            ):
                group_id = event.message_obj.group_id

            # 根据消息类型决定是否使用合并转发
            is_group = bool(group_id)
            is_private = not is_group

            # 如果是群聊且群聊合并转发已启用，或者是私聊且私聊合并转发已启用，且不是只发送截图
            if (self.send_content_type != "screenshot_only") and (
                (is_group and self.merge_forward_enabled["group"])
                or (is_private and self.merge_forward_enabled["private"])
            ):
                # 使用合并转发 - 将所有分析结果合并成一个合并转发消息
                nodes = []

                # 添加总标题节点
                total_title_node = Node(
                    uin=event.get_sender_id(),
                    name="网页分析结果汇总",
                    content=[Plain(f"共{len(analysis_results)}个网页分析结果")],
                )
                nodes.append(total_title_node)

                # 为每个URL添加分析结果节点
                for i, result_data in enumerate(analysis_results, 1):
                    url = result_data["url"]
                    analysis_result = result_data["result"]
                    screenshot = result_data.get("screenshot")

                    # 添加当前URL的标题节点
                    url_title_node = Node(
                        uin=event.get_sender_id(),
                        name=f"分析结果 {i}",
                        content=[Plain(f"第{i}个网页分析结果 - {url}")],
                    )
                    nodes.append(url_title_node)

                    # 处理截图，准备创建图片组件
                    image_component = None
                    if (
                        self.merge_forward_enabled.get("include_screenshot", False)
                        and screenshot
                        and self.send_content_type != "analysis_only"
                    ):
                        try:
                            # 根据截图格式设置文件后缀
                            suffix = (
                                f".{self.screenshot_format}"
                                if self.screenshot_format
                                else ".jpg"
                            )
                            # 创建临时文件保存截图
                            with tempfile.NamedTemporaryFile(
                                suffix=suffix, delete=False
                            ) as temp_file:
                                temp_file.write(screenshot)
                                temp_file_path = temp_file.name

                            # 创建图片组件
                            image_component = Image.fromFileSystem(temp_file_path)

                            # 保存临时文件路径，以便后续清理
                            if "temp_files" not in locals():
                                temp_files = []
                            temp_files.append(temp_file_path)
                        except Exception as e:
                            logger.error(f"处理截图失败: {e}")
                            # 确保临时文件被删除
                            if "temp_file_path" in locals() and os.path.exists(
                                temp_file_path
                            ):
                                os.unlink(temp_file_path)

                    # 根据发送内容类型决定是否添加分析结果节点
                    if self.send_content_type != "screenshot_only":
                        content = [Plain(analysis_result)]
                        content_node = Node(
                            uin=event.get_sender_id(),
                            name="详细分析",
                            content=content,
                        )
                        nodes.append(content_node)

                    # 如果启用了合并转发包含截图功能，并且有截图，且需要发送截图，则创建单独的截图节点
                    if (
                        self.merge_forward_enabled.get("include_screenshot", False)
                        and screenshot
                        and self.send_content_type != "analysis_only"
                    ):
                        try:
                            # 创建单独的截图节点
                            screenshot_node = Node(
                                uin=event.get_sender_id(),
                                name="网页截图",
                                content=[image_component],
                            )
                            nodes.append(screenshot_node)
                        except Exception as e:
                            logger.error(f"创建截图节点失败: {e}")

                # 使用Nodes包装所有节点，合并成一个合并转发消息
                merge_forward_message = Nodes(nodes)

                # 发送合并转发消息
                yield event.chain_result([merge_forward_message])

                # 如果未启用合并转发包含截图功能，且需要发送截图，则逐个发送截图
                if (
                    not self.merge_forward_enabled.get("include_screenshot", False)
                    and self.send_content_type != "analysis_only"
                ):
                    for result_data in analysis_results:
                        screenshot = result_data.get("screenshot")
                        if screenshot:
                            try:
                                # 根据截图格式设置文件后缀
                                suffix = (
                                    f".{self.screenshot_format}"
                                    if self.screenshot_format
                                    else ".jpg"
                                )
                                # 创建临时文件保存截图
                                with tempfile.NamedTemporaryFile(
                                    suffix=suffix, delete=False
                                ) as temp_file:
                                    temp_file.write(screenshot)
                                    temp_file_path = temp_file.name

                                # 使用Image.fromFileSystem()方法发送图片
                                image_component = Image.fromFileSystem(temp_file_path)
                                yield event.chain_result([image_component])
                                logger.info(
                                    f"群聊 {group_id} 使用合并转发发送分析结果，并发送截图"
                                )

                                # 删除临时文件
                                os.unlink(temp_file_path)
                            except Exception as e:
                                logger.error(f"发送截图失败: {e}")
                                # 确保临时文件被删除
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    os.unlink(temp_file_path)
                            if "temp_file_path" in locals() and os.path.exists(
                                temp_file_path
                            ):
                                os.unlink(temp_file_path)
                # 清理所有临时文件
                if "temp_files" in locals():
                    for temp_file_path in temp_files:
                        try:
                            if os.path.exists(temp_file_path):
                                os.unlink(temp_file_path)
                        except Exception as e:
                            logger.error(f"清理临时文件失败: {e}")
                logger.info(
                    f"群聊 {group_id} 使用合并转发发送{len(analysis_results)}个分析结果"
                )
            else:
                # 普通发送
                for i, result_data in enumerate(analysis_results, 1):
                    screenshot = result_data.get("screenshot")
                    analysis_result = result_data.get("result")

                    # 如果只发送截图
                    if self.send_content_type == "screenshot_only":
                        if screenshot:
                            try:
                                # 根据截图格式设置文件后缀
                                suffix = (
                                    f".{self.screenshot_format}"
                                    if self.screenshot_format
                                    else ".jpg"
                                )
                                # 创建临时文件保存截图
                                with tempfile.NamedTemporaryFile(
                                    suffix=suffix, delete=False
                                ) as temp_file:
                                    temp_file.write(screenshot)
                                    temp_file_path = temp_file.name

                                # 使用Image.fromFileSystem()方法发送图片
                                image_component = Image.fromFileSystem(temp_file_path)
                                yield event.chain_result([image_component])
                                logger.info("只发送截图")

                                # 删除临时文件
                                os.unlink(temp_file_path)
                            except Exception as e:
                                logger.error(f"发送截图失败: {e}")
                                # 确保临时文件被删除
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    os.unlink(temp_file_path)
                    # 发送分析结果或两者都发送
                    else:
                        url = result_data["url"]
                        # 根据发送内容类型决定是否发送分析结果文本
                        if self.send_content_type != "screenshot_only":
                            if len(analysis_results) == 1:
                                result_text = f"网页分析结果：\n{analysis_result}"
                            else:
                                result_text = f"第{i}/{len(analysis_results)}个网页分析结果：\n{analysis_result}"
                            yield event.plain_result(result_text)

                        # 根据发送内容类型决定是否发送截图
                        if screenshot and self.send_content_type != "analysis_only":
                            try:
                                # 根据截图格式设置文件后缀
                                suffix = (
                                    f".{self.screenshot_format}"
                                    if self.screenshot_format
                                    else ".jpg"
                                )
                                # 创建临时文件保存截图
                                with tempfile.NamedTemporaryFile(
                                    suffix=suffix, delete=False
                                ) as temp_file:
                                    temp_file.write(screenshot)
                                    temp_file_path = temp_file.name

                                # 使用Image.fromFileSystem()方法发送图片
                                image_component = Image.fromFileSystem(temp_file_path)
                                yield event.chain_result([image_component])
                                logger.info("普通发送分析结果，并发送截图")

                                # 删除临时文件
                                os.unlink(temp_file_path)
                            except Exception as e:
                                logger.error(f"发送截图失败: {e}")
                                # 确保临时文件被删除
                                if "temp_file_path" in locals() and os.path.exists(
                                    temp_file_path
                                ):
                                    os.unlink(temp_file_path)
                message_type = "群聊" if group_id else "私聊"
                logger.info(
                    f"{message_type}消息普通发送{len(analysis_results)}个分析结果"
                )
        except Exception as e:
            logger.error(f"发送分析结果失败: {e}")
            yield event.plain_result(f"❌ 发送分析结果失败: {str(e)}")

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("网页分析插件已卸载")
