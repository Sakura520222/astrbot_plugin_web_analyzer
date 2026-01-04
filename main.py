"""
AstrBot 网页分析插件

自动识别网页链接，智能抓取解析内容，集成大语言模型进行深度分析和总结，支持网页截图、缓存机制和多种管理命令。
"""

from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .analyzer import WebAnalyzer
from .cache import CacheManager
from .utils import WebAnalyzerUtils


# 错误类型枚举
class ErrorType:
    """错误类型枚举"""
    # 网络相关
    NETWORK_ERROR = "network_error"  # 网络错误
    NETWORK_TIMEOUT = "network_timeout"  # 网络超时
    NETWORK_CONNECTION = "network_connection"  # 连接失败

    # 解析相关
    PARSING_ERROR = "parsing_error"  # 解析错误
    CONTENT_EMPTY = "content_empty"  # 内容为空
    HTML_PARSING = "html_parsing"  # HTML解析错误

    # LLM相关
    LLM_ERROR = "llm_error"  # LLM错误
    LLM_TIMEOUT = "llm_timeout"  # LLM超时
    LLM_INVALID_RESPONSE = "llm_invalid_response"  # LLM无效响应
    LLM_PERMISSION = "llm_permission"  # LLM权限错误

    # 截图相关
    SCREENSHOT_ERROR = "screenshot_error"  # 截图错误
    BROWSER_ERROR = "browser_error"  # 浏览器错误

    # 缓存相关
    CACHE_ERROR = "cache_error"  # 缓存错误
    CACHE_WRITE = "cache_write"  # 缓存写入错误
    CACHE_READ = "cache_read"  # 缓存读取错误

    # 配置相关
    CONFIG_ERROR = "config_error"  # 配置错误
    CONFIG_INVALID = "config_invalid"  # 配置无效

    # 权限相关
    PERMISSION_ERROR = "permission_error"  # 权限错误
    DOMAIN_BLOCKED = "domain_blocked"  # 域名被阻止

    # 其他错误
    UNKNOWN_ERROR = "unknown_error"  # 未知错误
    INTERNAL_ERROR = "internal_error"  # 内部错误


# 错误严重程度枚举
class ErrorSeverity:
    """错误严重程度枚举"""
    INFO = "info"  # 信息级
    WARNING = "warning"  # 警告级
    ERROR = "error"  # 错误级
    CRITICAL = "critical"  # 严重错误


# 错误处理配置
ERROR_MESSAGES: dict[str, dict[str, Any]] = {
    "network_error": {
        "message": "网络请求失败",
        "solution": "请检查网络连接或URL是否正确，或尝试调整请求超时设置",
        "severity": ErrorSeverity.ERROR
    },
    "network_timeout": {
        "message": "网络请求超时",
        "solution": "目标网站响应缓慢，请稍后重试或调整请求超时设置",
        "severity": ErrorSeverity.ERROR
    },
    "network_connection": {
        "message": "网络连接失败",
        "solution": "无法连接到服务器，请检查网络连接或目标网站是否可访问",
        "severity": ErrorSeverity.ERROR
    },
    "parsing_error": {
        "message": "网页内容解析失败",
        "solution": "该网页结构可能较为特殊，建议尝试其他分析方式",
        "severity": ErrorSeverity.WARNING
    },
    "content_empty": {
        "message": "提取的内容为空",
        "solution": "目标网页可能没有可提取的内容，或内容格式不支持",
        "severity": ErrorSeverity.WARNING
    },
    "html_parsing": {
        "message": "HTML解析错误",
        "solution": "网页HTML格式异常，无法正确解析",
        "severity": ErrorSeverity.ERROR
    },
    "llm_error": {
        "message": "大语言模型分析失败",
        "solution": "请检查LLM配置是否正确，或尝试调整分析参数",
        "severity": ErrorSeverity.ERROR
    },
    "llm_timeout": {
        "message": "大语言模型响应超时",
        "solution": "LLM响应缓慢，请稍后重试或调整LLM超时设置",
        "severity": ErrorSeverity.ERROR
    },
    "llm_invalid_response": {
        "message": "大语言模型返回无效响应",
        "solution": "LLM返回格式异常，请检查LLM配置或稍后重试",
        "severity": ErrorSeverity.ERROR
    },
    "llm_permission": {
        "message": "大语言模型权限不足",
        "solution": "请检查LLM API密钥或权限配置",
        "severity": ErrorSeverity.ERROR
    },
    "screenshot_error": {
        "message": "网页截图失败",
        "solution": "请检查浏览器配置或网络连接，或尝试调整截图参数",
        "severity": ErrorSeverity.WARNING
    },
    "browser_error": {
        "message": "浏览器操作失败",
        "solution": "浏览器初始化或操作失败，请检查浏览器配置或重启插件",
        "severity": ErrorSeverity.ERROR
    },
    "cache_error": {
        "message": "缓存操作失败",
        "solution": "请检查缓存目录权限或存储空间",
        "severity": ErrorSeverity.WARNING
    },
    "cache_write": {
        "message": "缓存写入失败",
        "solution": "无法写入缓存文件，请检查缓存目录权限或存储空间",
        "severity": ErrorSeverity.WARNING
    },
    "cache_read": {
        "message": "缓存读取失败",
        "solution": "无法读取缓存文件，缓存可能已损坏",
        "severity": ErrorSeverity.WARNING
    },
    "config_error": {
        "message": "配置错误",
        "solution": "请检查插件配置是否正确，或尝试重置配置",
        "severity": ErrorSeverity.ERROR
    },
    "config_invalid": {
        "message": "配置无效",
        "solution": "插件配置格式无效，请检查配置项是否正确",
        "severity": ErrorSeverity.ERROR
    },
    "permission_error": {
        "message": "权限不足",
        "solution": "请检查插件权限配置，或联系管理员获取权限",
        "severity": ErrorSeverity.ERROR
    },
    "domain_blocked": {
        "message": "域名被阻止",
        "solution": "该域名已被加入黑名单，无法访问",
        "severity": ErrorSeverity.ERROR
    },
    "unknown_error": {
        "message": "未知错误",
        "solution": "请检查日志获取详细信息，或尝试重启插件",
        "severity": ErrorSeverity.CRITICAL
    },
    "internal_error": {
        "message": "内部错误",
        "solution": "插件内部发生错误，请检查日志或联系开发者",
        "severity": ErrorSeverity.CRITICAL
    }
}


@register(
    "astrbot_plugin_web_analyzer",
    "Sakura520222",
    "自动识别网页链接，智能抓取解析内容，集成大语言模型进行深度分析和总结，支持网页截图、缓存机制和多种管理命令",
    "1.3.6",
    "https://github.com/Sakura520222/astrbot_plugin_web_analyzer",
)
class WebAnalyzerPlugin(Star):
    """网页分析插件主类，负责管理和调度所有功能模块"""

    def __init__(self, context: Context, config: AstrBotConfig):
        """插件初始化方法，负责加载、验证和初始化所有配置项"""
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
        self._load_recall_settings()
        self._load_command_settings()
        self._load_resource_settings()

        # URL处理标志集合：用于避免重复处理同一URL
        self.processing_urls = set()

        # 初始化组件
        self._init_cache_manager()
        self._init_web_analyzer()

        # 撤回任务列表：用于管理所有撤回任务
        self.recall_tasks = []

        # 记录配置初始化完成
        logger.info("插件配置初始化完成")

    def _load_network_settings(self):
        """加载和验证网络设置"""
        network_settings = self.config.get("network_settings", {})
        # 最大内容长度
        self.max_content_length = max(1000, network_settings.get("max_content_length", 10000))
        # 请求超时时间
        self.timeout = max(5, min(300, network_settings.get("request_timeout", 30)))
        # 重试次数
        self.retry_count = max(0, min(10, network_settings.get("retry_count", 3)))
        # 重试延迟
        self.retry_delay = max(0, min(10, network_settings.get("retry_delay", 2)))
        # 用户代理
        self.user_agent = network_settings.get(
            "user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        # 代理设置
        self.proxy = network_settings.get("proxy", "")
        # 并发处理设置
        self.max_concurrency = max(1, min(20, network_settings.get("max_concurrency", 5)))
        self.dynamic_concurrency = bool(network_settings.get("dynamic_concurrency", True))
        # 优先级设置
        self.enable_priority_scheduling = bool(network_settings.get("enable_priority_scheduling", False))
        # URL处理设置
        self.enable_unified_domain = bool(network_settings.get("enable_unified_domain", True))

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
        self.allowed_domains = self._parse_domain_list(domain_settings.get("allowed_domains", ""))
        self.blocked_domains = self._parse_domain_list(domain_settings.get("blocked_domains", ""))

    def _load_analysis_settings(self):
        """加载和验证分析设置"""
        analysis_settings = self.config.get("analysis_settings", {})
        # 分析模式
        self.analysis_mode = analysis_settings.get("analysis_mode", "auto")
        # 验证分析模式是否有效
        valid_modes = ["auto", "manual", "hybrid", "LLMTOOL"]
        if self.analysis_mode not in valid_modes:
            logger.warning(f"无效的分析模式: {self.analysis_mode}，将使用默认值 auto")
            self.analysis_mode = "auto"
        # 兼容旧的auto_analyze配置
        self.auto_analyze = bool(analysis_settings.get("auto_analyze", True))
        # 如果设置了analysis_mode，优先使用新配置
        if "analysis_mode" in analysis_settings:
            self.auto_analyze = (self.analysis_mode == "auto")
        # 是否在结果中使用emoji
        self.enable_emoji = bool(analysis_settings.get("enable_emoji", True))
        # 是否显示内容统计信息
        self.enable_statistics = bool(analysis_settings.get("enable_statistics", True))
        # 最大摘要长度
        self.max_summary_length = max(500, min(10000, analysis_settings.get("max_summary_length", 2000)))

        # 发送内容类型设置
        self.send_content_type = analysis_settings.get("send_content_type", "both")
        # 验证发送内容类型是否有效
        if self.send_content_type not in ["both", "analysis_only", "screenshot_only"]:
            logger.warning(
                f"无效的发送内容类型: {self.send_content_type}，将使用默认值 both"
            )
            self.send_content_type = "both"

        # 结果展示设置
        self.result_template = analysis_settings.get("result_template", "default")
        # 验证结果模板是否有效
        valid_templates = ["default", "detailed", "compact", "markdown", "simple"]
        if self.result_template not in valid_templates:
            logger.warning(
                f"无效的结果模板: {self.result_template}，将使用默认值 default"
            )
            self.result_template = "default"

        # 结果折叠设置
        self.enable_collapsible = bool(analysis_settings.get("enable_collapsible", False))
        self.collapse_threshold = max(500, min(5000, analysis_settings.get("collapse_threshold", 1500)))

        # 无协议头URL识别设置
        self.enable_no_protocol_url = bool(analysis_settings.get("enable_no_protocol_url", False))
        self.default_protocol = analysis_settings.get("default_protocol", "https")
        # 验证默认协议是否有效
        if self.default_protocol not in ["http", "https"]:
            logger.warning(f"无效的默认协议: {self.default_protocol}，将使用默认值 https")
            self.default_protocol = "https"
        # 是否允许LLM自主决策：允许LLM决定是发送分析结果还是截图
        self.enable_llm_decision = bool(analysis_settings.get("enable_llm_decision", False))

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

        # 截图裁剪设置
        self.enable_crop = bool(screenshot_settings.get("enable_crop", False))
        # 裁剪区域，格式为 [left, top, right, bottom]
        crop_area = screenshot_settings.get("crop_area", [0, 0, self.screenshot_width, self.screenshot_height])

        # 处理字符串格式的裁剪区域
        if isinstance(crop_area, str):
            try:
                # 尝试将字符串转换为列表
                crop_area = eval(crop_area)
            except Exception as e:
                logger.warning(f"解析裁剪区域失败: {crop_area}，错误: {e}，将使用默认值")
                crop_area = [0, 0, self.screenshot_width, self.screenshot_height]

        # 验证裁剪区域是否有效
        if not isinstance(crop_area, list) or len(crop_area) != 4:
            logger.warning(f"无效的裁剪区域: {crop_area}，将使用默认值")
            crop_area = [0, 0, self.screenshot_width, self.screenshot_height]

        self.crop_area = crop_area



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
        # 缓存预加载设置
        self.cache_preload_enabled = bool(cache_settings.get("cache_preload_enabled", False))
        self.cache_preload_count = max(
            0, min(100, cache_settings.get("cache_preload_count", 20))
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
        self.extract_types = WebAnalyzerUtils.parse_extract_types(extract_types_text)
        self.extract_types = WebAnalyzerUtils.validate_extract_types(self.extract_types)
        self.extract_types = WebAnalyzerUtils.ensure_minimal_extract_types(self.extract_types)
        self.extract_types = WebAnalyzerUtils.add_required_extract_types(self.extract_types)

    def _load_recall_settings(self):
        """加载和验证撤回设置"""
        recall_settings = self.config.get("recall_settings", {})
        # 是否启用自动撤回功能
        self.enable_recall = bool(recall_settings.get("enable_recall", True))
        # 撤回类型：time_based(定时撤回)或smart(智能撤回)
        self.recall_type = recall_settings.get("recall_type", "smart")
        # 撤回延迟时间：设置合理的范围，避免过短或过长
        self.recall_time = max(0, min(120, recall_settings.get("recall_time", 10)))
        # 是否启用智能撤回
        self.smart_recall_enabled = bool(recall_settings.get("smart_recall_enabled", True))

    def _load_command_settings(self):
        """加载和验证命令设置"""
        command_settings = self.config.get("command_settings", {})
        # 自定义命令别名配置
        custom_aliases = command_settings.get("custom_aliases", {})

        # 处理字符串格式的自定义别名
        if isinstance(custom_aliases, str):
            try:
                # 解析自定义别名，格式为：原命令=别名1,别名2
                parsed_aliases = {}
                lines = custom_aliases.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    command, aliases = line.split("=", 1)
                    command = command.strip()
                    alias_list = [alias.strip() for alias in aliases.split(",") if alias.strip()]
                    if command and alias_list:
                        parsed_aliases[command] = alias_list
                self.custom_command_aliases = parsed_aliases
            except Exception as e:
                logger.warning(f"解析自定义命令别名失败: {e}，将使用默认值")
                self.custom_command_aliases = {}
        else:
            self.custom_command_aliases = custom_aliases

        # 命令补全设置
        self.enable_command_completion = bool(command_settings.get("enable_completion", True))
        # 命令帮助设置
        self.enable_command_help = bool(command_settings.get("enable_help", True))
        # 命令参数提示设置
        self.enable_param_hints = bool(command_settings.get("enable_param_hints", True))

    def _load_resource_settings(self):
        """加载和验证资源管理设置"""
        resource_settings = self.config.get("resource_settings", {})
        # 内存监控设置
        self.enable_memory_monitor = bool(resource_settings.get("enable_memory_monitor", True))
        # 内存使用阈值，确保在合理范围内
        self.memory_threshold = max(0.0, min(100.0, resource_settings.get("memory_threshold", 80.0)))


    def _init_cache_manager(self):
        """初始化缓存管理器"""
        self.cache_manager = CacheManager(
            max_size=self.max_cache_size,
            expire_time=self.cache_expire_time,
            preload_enabled=self.cache_preload_enabled,
            preload_count=self.cache_preload_count
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
            enable_memory_monitor=self.enable_memory_monitor,  # 启用内存监控
            memory_threshold=self.memory_threshold,  # 内存使用阈值，超过此阈值时自动释放内存
            enable_unified_domain=self.enable_unified_domain,  # 是否启用域名统一处理
        )

    def _parse_domain_list(self, domain_text: str) -> list[str]:
        """将多行域名文本转换为Python列表"""
        return WebAnalyzerUtils.parse_domain_list(domain_text)

    def _parse_group_list(self, group_text: str) -> list[str]:
        """将多行群聊ID文本转换为Python列表"""
        return WebAnalyzerUtils.parse_group_list(group_text)

    def _is_group_blacklisted(self, group_id: str) -> bool:
        """检查指定群聊是否在黑名单中"""
        if not group_id or not self.group_blacklist:
            return False
        return group_id in self.group_blacklist

    def _is_domain_allowed(self, url: str) -> bool:
        """检查指定URL的域名是否允许访问"""
        return WebAnalyzerUtils.is_domain_allowed(url, self.allowed_domains, self.blocked_domains)

    @filter.command("网页分析", alias={"分析", "总结", "web", "analyze"})
    async def analyze_webpage(self, event: AstrMessageEvent):
        """手动触发网页分析命令"""
        message_text = event.message_str

        # 从消息中提取所有URL
        urls = self.analyzer.extract_urls(message_text, self.enable_no_protocol_url, self.default_protocol)
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

        # 直接调用发送方法，不使用yield，获取message_id和bot实例
        processing_message_id, bot = await self._send_processing_message(event, message)

        # 批量处理所有允许访问的URL
        async for result in self._batch_process_urls(event, allowed_urls, processing_message_id, bot):
            yield result

    @filter.llm_tool(name="analyze_webpage")
    async def analyze_webpage_tool(self, event: AstrMessageEvent, url: str) -> Any:
        """智能网页分析工具"""
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
        if not self._is_domain_allowed(normalized_url):
            error_msg = f"该域名不在允许访问的列表中: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 发送处理提示消息，告知用户正在分析
        message = f"正在分析网页: {normalized_url}"
        processing_message_id, bot = await self._send_processing_message(event, message)

        # 处理单个URL
        async for result in self._batch_process_urls(event, [normalized_url], processing_message_id, bot):
            yield result

    @filter.llm_tool(name="analyze_webpage_with_decision")
    async def analyze_webpage_with_decision_tool(self, event: AstrMessageEvent, url: str, return_type: str = "both") -> Any:
        """智能网页分析工具（带自主决策）"""
        # 检查是否启用了LLMTOOL模式，未启用则不执行
        if self.analysis_mode != "LLMTOOL":
            logger.info(f"当前未启用LLMTOOL模式，拒绝analyze_webpage_with_decision_tool调用: {url}")
            yield event.plain_result("当前未启用网页分析工具模式")
            return

        # 检查是否启用了LLM自主决策功能
        if not self.enable_llm_decision:
            logger.info(f"当前未启用LLM自主决策功能，拒绝analyze_webpage_with_decision_tool调用: {url}")
            yield event.plain_result("当前未启用LLM自主决策功能")
            return

        logger.info(f"收到analyze_webpage_with_decision_tool调用，原始URL: {url}，返回类型: {return_type}")

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
        if not self._is_domain_allowed(normalized_url):
            error_msg = f"该域名不在允许访问的列表中: {normalized_url}"
            logger.warning(error_msg)
            yield event.plain_result(error_msg)
            return

        # 发送处理提示消息，告知用户正在分析
        message = f"正在分析网页: {normalized_url}"
        processing_message_id, bot = await self._send_processing_message(event, message)

        # 创建临时WebAnalyzer实例
        async with WebAnalyzer(
            self.max_content_length,
            self.timeout,
            self.user_agent,
            self.proxy,
            self.retry_count,
            self.retry_delay,
        ) as analyzer:
            # 处理单个URL，获取分析结果
            result = await self._process_single_url(event, normalized_url, analyzer)

            # 保存原始send_content_type配置
            original_send_content_type = self.send_content_type

            try:
                # 根据LLM的决策设置send_content_type
                self.send_content_type = return_type
                logger.info(f"临时设置send_content_type为: {return_type}")

                # 发送分析结果
                async for result_msg in self._send_analysis_result(event, [result]):
                    yield result_msg
            finally:
                # 恢复原始send_content_type配置
                self.send_content_type = original_send_content_type
                logger.info(f"恢复send_content_type为: {original_send_content_type}")

            # 智能撤回：分析完成后立即撤回处理中消息
            if (self.enable_recall and
                self.recall_type == "smart" and
                self.smart_recall_enabled and
                processing_message_id and
                bot):
                try:
                    await bot.delete_msg(message_id=processing_message_id)
                    logger.info(f"已撤回处理中消息: {processing_message_id}")
                except Exception as e:
                    logger.error(f"撤回处理中消息失败: {e}")

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
        urls = self.analyzer.extract_urls(message_text, self.enable_no_protocol_url, self.default_protocol)
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

        # 根据analysis_mode配置决定是否使用旧版直接分析方式
        if self.analysis_mode == "LLMTOOL":
            # 启用了LLM函数工具模式，不使用旧版直接分析
            # 让LLM自己决定是否调用analyze_webpage工具
            logger.info(f"启用了LLM函数工具模式，不自动分析链接，让LLM自己决定: {allowed_urls}")
            return
        else:
            # 未启用LLM函数工具模式，使用旧版直接分析方式
            # 发送处理提示消息，告知用户正在分析
            if len(allowed_urls) == 1:
                message = f"检测到网页链接，正在分析: {allowed_urls[0]}"
            else:
                message = f"检测到{len(allowed_urls)}个网页链接，正在分析..."

            # 直接调用发送方法，不使用yield，获取message_id和bot实例
            processing_message_id, bot = await self._send_processing_message(event, message)

            # 批量处理所有允许访问的URL
            async for result in self._batch_process_urls(event, allowed_urls, processing_message_id, bot):
                yield result

    async def _use_llm_tool_mode(self, event: AstrMessageEvent, message_text: str, allowed_urls: list):
        """使用LLM Tool模式处理消息"""
        try:
            # 检查是否支持tool_loop_agent
            if not hasattr(self.context, "tool_loop_agent"):
                logger.warning("不支持tool_loop_agent，回退到旧版解析方式")
                # 回退到旧版解析方式
                async for result in self._fallback_to_old_mode(event, allowed_urls):
                    yield result
                return

            # 优先使用配置的LLM提供商，如果没有配置则使用当前会话的模型
            provider_id = self.llm_provider
            if not provider_id:
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)

            if not provider_id:
                logger.warning("无法获取LLM提供商，回退到旧版解析方式")
                # 回退到旧版解析方式
                async for result in self._fallback_to_old_mode(event, allowed_urls):
                    yield result
                return

            # 构建提示词
            prompt = f"请根据用户消息判断是否需要分析其中的网页链接，如果需要分析，请调用analyze_webpage工具进行分析。\n\n用户消息：{message_text}"

            # 调用tool_loop_agent让LLM决定是否使用工具
            logger.info(f"调用tool_loop_agent处理消息，URLs: {allowed_urls}")

            try:
                # 尝试导入ToolSet
                from astrbot.core.agent.tool import ToolSet
                # 调用tool_loop_agent
                llm_resp = await self.context.tool_loop_agent(
                    event=event,
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    tools=ToolSet([]),  # 空ToolSet，依赖装饰器注册的工具
                    max_steps=30,  # Agent最大执行步骤
                    tool_call_timeout=60,  # 工具调用超时时间
                )
                logger.info(f"tool_loop_agent执行完成，结果: {llm_resp.completion_text if hasattr(llm_resp, 'completion_text') else '无文本结果'}")
            except Exception as e_inner:
                logger.error(f"调用tool_loop_agent失败: {e_inner}")
                # 尝试不使用ToolSet参数调用（兼容不同版本）
                try:
                    llm_resp = await self.context.tool_loop_agent(
                        event=event,
                        chat_provider_id=provider_id,
                        prompt=prompt,
                        max_steps=30,
                        tool_call_timeout=60,
                    )
                    logger.info(f"tool_loop_agent执行完成（无ToolSet），结果: {llm_resp.completion_text if hasattr(llm_resp, 'completion_text') else '无文本结果'}")
                except Exception as e_inner2:
                    logger.error(f"调用tool_loop_agent（无ToolSet）失败: {e_inner2}")
                    # 回退到旧版解析方式
                    logger.warning("tool_loop_agent调用失败，回退到旧版解析方式")
                    async for result in self._fallback_to_old_mode(event, allowed_urls):
                        yield result
                    return
        except Exception as e:
            logger.error(f"LLM Tool模式处理失败: {e}")
            # 出错时回退到旧版解析方式
            async for result in self._fallback_to_old_mode(event, allowed_urls):
                yield result

    async def _fallback_to_old_mode(self, event: AstrMessageEvent, allowed_urls: list):
        """回退到旧版解析方式"""
        # 发送处理提示消息，告知用户正在分析
        if len(allowed_urls) == 1:
            message = f"检测到网页链接，正在分析: {allowed_urls[0]}"
        else:
            message = f"检测到{len(allowed_urls)}个网页链接，正在分析..."

        # 直接调用发送方法，不使用yield，获取message_id和bot实例
        processing_message_id, bot = await self._send_processing_message(event, message)

        # 批量处理所有允许访问的URL
        async for result in self._batch_process_urls(event, allowed_urls, processing_message_id, bot):
            yield result



    async def _process_single_url(
        self, event: AstrMessageEvent, url: str, analyzer: WebAnalyzer
    ) -> dict:
        """处理单个网页URL，生成完整的分析结果"""
        try:
            # 1. 检查缓存
            cached_result = self._check_cache(url)
            if cached_result:
                logger.info(f"使用URL缓存结果: {url}")
                return cached_result

            # 2. 抓取网页内容
            html = await self._fetch_webpage_content(analyzer, url)
            if not html:
                error_msg = self._handle_error(ErrorType.NETWORK_ERROR, Exception("无法获取网页内容"), url)
                return {
                    "url": url,
                    "result": error_msg,
                    "screenshot": None,
                }

            # 3. 提取结构化内容
            content_data = await self._extract_structured_content(analyzer, html, url)
            if not content_data:
                error_msg = self._handle_error(ErrorType.PARSING_ERROR, Exception("无法解析网页内容"), url)
                return {
                    "url": url,
                    "result": error_msg,
                    "screenshot": None,
                }

            # 4. 调用LLM进行分析
            analysis_result = await self._analyze_content(event, content_data)

            # 5. 提取特定内容
            analysis_result = await self._extract_and_add_specific_content(analysis_result, html, url)

            # 6. 生成截图
            screenshot = await self._generate_screenshot(analyzer, url, analysis_result)

            # 7. 应用结果设置
            final_result = self._apply_result_settings(analysis_result, url)

            # 8. 准备结果数据
            result_data = {
                "url": url,
                "result": final_result,
                "screenshot": screenshot,
            }

            # 9. 更新缓存
            self._update_cache(url, result_data, content_data["content"])

            return result_data
        except Exception as e:
            # 捕获所有异常，确保方法始终返回有效结果
            error_type = self._get_error_type(e)
            error_msg = self._handle_error(error_type, e, url)
            return {
                "url": url,
                "result": error_msg,
                "screenshot": None,
            }

    async def _fetch_webpage_content(self, analyzer: WebAnalyzer, url: str) -> str:
        """抓取网页HTML内容
        
        Args:
            analyzer: WebAnalyzer实例
            url: 要抓取的URL
        
        Returns:
            网页HTML内容，如果抓取失败则返回空字符串
        """
        try:
            html = await analyzer.fetch_webpage(url)
            return html
        except Exception as e:
            logger.error(f"抓取网页失败: {url}, 错误: {e}")
            return ""

    async def _extract_structured_content(self, analyzer: WebAnalyzer, html: str, url: str) -> dict:
        """从HTML中提取结构化内容
        
        Args:
            analyzer: WebAnalyzer实例
            html: 网页HTML内容
            url: 网页URL
        
        Returns:
            包含结构化内容的字典，如果提取失败则返回None
        """
        try:
            content_data = analyzer.extract_content(html, url)
            return content_data
        except Exception as e:
            logger.error(f"提取结构化内容失败: {url}, 错误: {e}")
            return None

    async def _analyze_content(self, event: AstrMessageEvent, content_data: dict) -> str:
        """调用LLM或基础分析方法分析内容
        
        Args:
            event: 消息事件对象
            content_data: 结构化内容数据
        
        Returns:
            分析结果文本
        """
        try:
            # 如果启用了翻译功能，先翻译内容
            if self.enable_translation:
                try:
                    translated_content = await self._translate_content(
                        event, content_data["content"]
                    )
                    # 创建翻译后的内容数据副本
                    translated_content_data = content_data.copy()
                    translated_content_data["content"] = translated_content
                    # 调用LLM进行分析（使用翻译后的内容）
                    return await self.analyze_with_llm(event, translated_content_data)
                except Exception as e:
                    # 翻译失败时，使用原始内容进行分析
                    logger.warning(f"翻译失败，使用原始内容进行分析: {content_data['url']}, 错误: {e}")

            # 直接调用LLM进行分析
            return await self.analyze_with_llm(event, content_data)
        except Exception as e:
            logger.error(f"分析内容失败: {content_data['url']}, 错误: {e}")
            return self.get_enhanced_analysis(content_data)

    async def _extract_and_add_specific_content(self, analysis_result: str, html: str, url: str) -> str:
        """提取特定类型内容并添加到分析结果中
        
        Args:
            analysis_result: 当前的分析结果
            html: 网页HTML内容
            url: 网页URL
        
        Returns:
            更新后的分析结果
        """
        try:
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
            return analysis_result
        except Exception as e:
            # 特定内容提取失败时，记录警告但不影响主分析结果
            logger.warning(f"特定内容提取失败: {url}, 错误: {e}")
            return analysis_result

    async def _generate_screenshot(self, analyzer: WebAnalyzer, url: str, analysis_result: str) -> bytes:
        """生成网页截图
        
        Args:
            analyzer: WebAnalyzer实例
            url: 网页URL
            analysis_result: 当前的分析结果
        
        Returns:
            截图二进制数据，如果生成失败则返回None
        """
        if not self.enable_screenshot or self.send_content_type == "analysis_only":
            return None

        try:
            screenshot = await analyzer.capture_screenshot(
                url,
                quality=self.screenshot_quality,
                width=self.screenshot_width,
                height=self.screenshot_height,
                full_page=self.screenshot_full_page,
                wait_time=self.screenshot_wait_time,
                format=self.screenshot_format,
            )

            # 应用截图裁剪
            if self.enable_crop and screenshot:
                try:
                    screenshot = analyzer.crop_screenshot(screenshot, tuple(self.crop_area))
                except Exception as e:
                    logger.warning(f"裁剪截图失败: {url}, 错误: {e}")

            return screenshot
        except Exception as e:
            # 截图失败时，记录错误但不影响主分析结果
            error_msg = self._handle_error(ErrorType.SCREENSHOT_ERROR, e, url)
            # 将截图错误信息添加到分析结果中
            analysis_result += f"\n\n⚠️ 截图功能提示: {error_msg.splitlines()[0]}"
            return None



    def _get_url_priority(self, url: str) -> int:
        """评估URL的处理优先级"""
        return WebAnalyzerUtils.get_url_priority(url)

    def _render_result_template(self, result: str, url: str, template_type: str) -> str:
        """根据模板类型渲染分析结果"""
        # 定义不同模板的渲染逻辑
        if template_type == "detailed":
            # 详细模板：包含完整信息和格式
            return f"【详细分析结果】\n\n📌 分析URL：{url}\n\n{result}\n\n--- 分析结束 ---"
        elif template_type == "compact":
            # 紧凑模板：简洁展示核心信息
            lines = result.splitlines()
            compact_result = []
            for line in lines:
                if line.strip() and not line.startswith("⚠️"):
                    compact_result.append(line)
                    if len(compact_result) >= 10:  # 最多显示10行
                        break
            return f"【紧凑分析结果】\n{url}\n\n" + "\n".join(compact_result) + "\n\n... 更多内容请查看完整分析"
        elif template_type == "markdown":
            # Markdown模板：使用Markdown格式
            return f"# 网页分析结果\n\n## URL\n{url}\n\n## 分析内容\n{result}\n\n---\n*分析完成于 {self._get_current_time()}*"
        elif template_type == "simple":
            # 简单模板：极简展示
            return f"{url}\n\n{result}"
        else:
            # 默认模板：标准格式
            return f"【网页分析结果】\n{url}\n\n{result}"

    def _get_current_time(self) -> str:
        """获取当前时间的格式化字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _collapse_result(self, result: str) -> str:
        """根据配置折叠长结果"""
        if self.enable_collapsible and len(result) > self.collapse_threshold:
            # 计算折叠位置，寻找合适的换行点
            collapse_pos = self.collapse_threshold
            # 尽量在段落结束处折叠
            while collapse_pos < len(result) and result[collapse_pos] != "\n":
                collapse_pos += 1
            if collapse_pos == len(result):
                # 如果没有找到换行，直接截断
                collapse_pos = self.collapse_threshold

            collapsed_content = result[:collapse_pos]
            remaining_content = result[collapse_pos:]
            return f"{collapsed_content}\n\n[展开全文]\n\n{remaining_content}"
        return result

    def _apply_result_settings(self, result: str, url: str) -> str:
        """应用所有结果设置（模板渲染和折叠）"""
        # 首先应用模板渲染
        rendered_result = self._render_result_template(result, url, self.result_template)
        # 然后应用结果折叠
        final_result = self._collapse_result(rendered_result)
        return final_result

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

    def _get_available_commands(self) -> dict:
        """获取所有可用命令的信息
        
        Returns:
            包含所有命令信息的字典
        """
        return {
            "网页分析": {
                "aliases": ["分析", "总结", "web", "analyze"],
                "description": "手动分析指定网页链接",
                "usage": "/网页分析 <URL1> <URL2>...",
                "options": [],
                "example": "/网页分析 https://example.com"
            },
            "web_config": {
                "aliases": ["网页分析配置", "网页分析设置"],
                "description": "查看当前插件配置",
                "usage": "/web_config",
                "options": [],
                "example": "/web_config"
            },
            "web_cache": {
                "aliases": ["网页缓存", "清理缓存"],
                "description": "管理分析结果缓存",
                "usage": "/web_cache [clear]",
                "options": ["clear"],
                "example": "/web_cache clear"
            },
            "group_blacklist": {
                "aliases": ["群黑名单", "黑名单"],
                "description": "管理群聊黑名单",
                "usage": "/group_blacklist [add/remove/clear] <群号>",
                "options": ["add", "remove", "clear"],
                "example": "/群黑名单 add 123456789"
            },
            "web_export": {
                "aliases": ["导出分析结果", "网页导出"],
                "description": "导出分析结果",
                "usage": "/web_export",
                "options": [],
                "example": "/web_export"
            },
            "test_merge": {
                "aliases": ["测试合并转发", "测试转发"],
                "description": "测试合并转发功能",
                "usage": "/test_merge",
                "options": [],
                "example": "/test_merge"
            },
            "web_help": {
                "aliases": ["网页分析帮助", "网页分析命令"],
                "description": "显示命令帮助信息",
                "usage": "/web_help",
                "options": [],
                "example": "/web_help"
            }
        }

    def _get_command_completions(self, input_text: str) -> list:
        """根据用户输入获取命令补全建议"""
        if not input_text.startswith("/"):
            return []

        # 提取当前输入的命令前缀
        input_cmd = input_text[1:].lower()
        completions = []

        # 获取所有可用命令
        commands = self._get_available_commands()

        # 检查主命令
        for cmd_name, cmd_info in commands.items():
            if cmd_name.lower().startswith(input_cmd):
                completions.append(f"/{cmd_name}")

            # 检查别名
            for alias in cmd_info["aliases"]:
                if alias.lower().startswith(input_cmd):
                    completions.append(f"/{alias}")

        return completions

    def _get_param_hints(self, command: str, current_params: list) -> list:
        """获取命令参数提示"""
        commands = self._get_available_commands()

        # 查找命令信息
        cmd_info = None
        for cmd_name, info in commands.items():
            if command == cmd_name or command in info["aliases"]:
                cmd_info = info
                break

        if not cmd_info:
            return []

        # 根据命令和已输入参数返回提示
        if cmd_name == "group_blacklist":
            if len(current_params) == 0:
                return ["add", "remove", "clear"]
            elif len(current_params) == 1 and current_params[0] in ["add", "remove"]:
                return ["<群号>"]
        elif cmd_name == "web_cache":
            if len(current_params) == 0:
                return ["clear"]

        return []

    async def _batch_process_urls(self, event: AstrMessageEvent, urls: list[str], processing_message_id: int | None = None, bot = None):
        """批量处理多个URL，实现高效的并发分析"""
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

        # 根据优先级对URL进行排序
        if self.enable_priority_scheduling:
            filtered_urls = sorted(filtered_urls, key=lambda url: self._get_url_priority(url), reverse=True)
            logger.info(f"URL优先级排序完成: {[(url, self._get_url_priority(url)) for url in filtered_urls]}")

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

                # 动态调整并发数
                concurrency = self.max_concurrency
                if self.dynamic_concurrency:
                    # 根据URL数量动态调整并发数
                    # 计算合理的并发数：URL数量的平方根，不超过max_concurrency
                    dynamic_concurrency = min(self.max_concurrency, max(1, int(len(filtered_urls) ** 0.5) + 1))
                    concurrency = dynamic_concurrency

                logger.info(f"使用并发数: {concurrency} 处理 {len(filtered_urls)} 个URL")

                # 分批次处理URL，控制并发数
                batch_size = concurrency
                results = []

                # 如果并发数大于等于URL数量，直接处理所有URL
                if batch_size >= len(filtered_urls):
                    tasks = [self._process_single_url(event, url, analyzer) for url in filtered_urls]
                    results = await asyncio.gather(*tasks)
                else:
                    # 分批次处理
                    for i in range(0, len(filtered_urls), batch_size):
                        batch_urls = filtered_urls[i:i+batch_size]
                        logger.info(f"处理批次 {i//batch_size + 1}/{(len(filtered_urls) + batch_size - 1)//batch_size}: {batch_urls}")
                        tasks = [self._process_single_url(event, url, analyzer) for url in batch_urls]
                        batch_results = await asyncio.gather(*tasks)
                        results.extend(batch_results)

                analysis_results = results

            # 发送所有分析结果
            async for result in self._send_analysis_result(event, analysis_results):
                yield result
        finally:
            # 无论处理成功还是失败，都要从处理集合中移除URL
            for url in filtered_urls:
                if url in self.processing_urls:
                    self.processing_urls.remove(url)

            # 智能撤回：分析完成后立即撤回处理中消息
            if (self.enable_recall and
                self.recall_type == "smart" and
                self.smart_recall_enabled and
                processing_message_id and
                bot):
                try:
                    logger.info(f"智能撤回：分析完成，立即撤回处理中消息，message_id: {processing_message_id}")
                    await bot.delete_msg(message_id=processing_message_id)
                    logger.info(f"智能撤回成功，已撤回消息: {processing_message_id}")
                except Exception as e:
                    logger.error(f"智能撤回消息失败: {e}")

    def _get_analysis_template(self, content_type: str, emoji_prefix: str, max_length: int) -> str:
        """根据内容类型获取相应的分析模板"""
        # 定义多种分析模板
        templates = {
            "新闻资讯": f"""请对以下新闻资讯进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**新闻内容**：
{{content}}

**分析要求**：
1. **核心事件**：用50-100字概括新闻的核心事件和背景
2. **关键信息**：提取3-5个最重要的事实要点
3. **事件影响**：分析事件可能产生的影响和意义
4. **相关背景**：补充必要的相关背景信息
5. **适用人群**：说明这条新闻对哪些人群最有价值

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "教程指南": f"""请对以下教程指南进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**教程内容**：
{{content}}

**分析要求**：
1. **核心目标**：用50-100字概括教程的核心目标和适用场景
2. **学习价值**：分析该教程对学习者的价值和意义
3. **关键步骤**：提取教程的主要步骤和关键点
4. **技术要点**：总结教程中涉及的核心技术或知识点
5. **注意事项**：整理教程中的重要提示和注意事项
6. **适用人群**：说明适合学习该教程的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "个人博客": f"""请对以下个人博客进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**博客内容**：
{{content}}

**分析要求**：
1. **核心观点**：用50-100字概括博客作者的核心观点和立场
2. **主要内容**：提取博客的主要内容和论述要点
3. **写作风格**：分析博客的写作风格和特点
4. **价值评估**：评价博客内容的价值和实用性
5. **适用人群**：说明适合阅读该博客的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "产品介绍": f"""请对以下产品介绍进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**产品内容**：
{{content}}

**分析要求**：
1. **产品定位**：用50-100字概括产品的定位和核心价值
2. **核心功能**：提取产品的主要功能和特性
3. **技术参数**：总结产品的关键技术参数和规格
4. **适用场景**：分析产品的适用场景和使用方法
5. **竞争优势**：分析产品相比同类产品的优势
6. **适用人群**：说明适合使用该产品的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "技术文档": f"""请对以下技术文档进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**文档内容**：
{{content}}

**分析要求**：
1. **文档目的**：用50-100字概括文档的核心目的和适用范围
2. **核心概念**：提取文档中涉及的核心概念和术语
3. **技术架构**：分析文档中描述的技术架构和设计思路
4. **使用方法**：总结文档中介绍的使用方法和最佳实践
5. **关键特性**：整理文档中提及的关键特性和功能
6. **适用人群**：说明适合阅读该文档的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "学术论文": f"""请对以下学术论文进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**论文内容**：
{{content}}

**分析要求**：
1. **研究背景**：用50-100字概括论文的研究背景和意义
2. **核心问题**：提取论文试图解决的核心问题
3. **研究方法**：分析论文采用的研究方法和技术路线
4. **主要发现**：总结论文的主要研究发现和结论
5. **创新点**：分析论文的创新点和贡献
6. **适用领域**：说明该研究成果的适用领域和应用前景

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "商业分析": f"""请对以下商业分析进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**分析内容**：
{{content}}

**分析要求**：
1. **核心主题**：用50-100字概括分析报告的核心主题和目的
2. **市场趋势**：提取报告中指出的主要市场趋势和变化
3. **关键数据**：总结报告中的关键数据和统计信息
4. **分析结论**：分析报告的主要结论和预测
5. **商业价值**：评价报告对企业和投资者的价值
6. **适用人群**：说明适合阅读该报告的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "娱乐资讯": f"""请对以下娱乐资讯进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**娱乐内容**：
{{content}}

**分析要求**：
1. **核心事件**：用50-100字概括娱乐资讯的核心事件
2. **关键信息**：提取3-5个最重要的事实要点
3. **相关背景**：补充必要的相关背景信息（如明星背景、作品信息等）
4. **受众价值**：分析该资讯对不同受众群体的吸引力和价值
5. **行业影响**：简要分析该事件对娱乐行业的可能影响
6. **适用人群**：说明这条资讯对哪些人群最有价值

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言生动有趣，符合娱乐资讯的特点
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "体育新闻": f"""请对以下体育新闻进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**体育内容**：
{{content}}

**分析要求**：
1. **核心事件**：用50-100字概括体育新闻的核心事件
2. **比赛概况**：提取比赛的关键信息（如比分、参赛队伍/选手、关键表现等）
3. **技术分析**：简要分析比赛中的技术亮点或战术安排
4. **历史背景**：补充必要的历史背景（如球队/选手历史战绩、赛事重要性等）
5. **事件影响**：分析该事件对相关球队、选手或体育项目的影响
6. **适用人群**：说明这条新闻对哪些人群最有价值

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言充满活力，符合体育新闻的特点
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            "教育资讯": f"""请对以下教育资讯进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**教育内容**：
{{content}}

**分析要求**：
1. **核心主题**：用50-100字概括教育资讯的核心主题和目的
2. **关键信息**：提取3-5个最重要的事实要点或政策内容
3. **适用范围**：明确该资讯适用的人群、地区或教育阶段
4. **实施影响**：分析该政策或资讯可能产生的教育影响和效果
5. **应对建议**：针对相关受众提供合理的应对建议或行动指南
6. **适用人群**：说明这条资讯对哪些人群最有价值

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁明了，符合教育资讯的特点
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",

            # 默认模板
            "默认": f"""请对以下网页内容进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**网页内容**：
{{content}}

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
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。"""
        }

        # 返回对应的模板，如果没有则使用默认模板
        return templates.get(content_type, templates["默认"])

    def _check_llm_availability(self) -> bool:
        """检查LLM是否可用和启用"""
        return hasattr(self.context, "llm_generate") and self.llm_enabled

    async def _get_llm_provider(self, event: AstrMessageEvent) -> str:
        """获取合适的LLM提供商"""
        # 优先使用配置的LLM提供商
        if self.llm_provider:
            return self.llm_provider

        # 如果没有配置，则使用当前会话的模型
        try:
            umo = event.unified_msg_origin
            return await self.context.get_current_chat_provider_id(umo=umo)
        except Exception as e:
            logger.error(f"获取当前会话的聊天模型ID失败: {e}")
            return ""

    def _build_llm_prompt(self, content_data: dict, content_type: str) -> str:
        """构建优化的LLM提示词"""
        title = content_data["title"]
        content = content_data["content"]
        url = content_data["url"]

        emoji_prefix = "每个要点用emoji图标标记" if self.enable_emoji else ""

        if self.custom_prompt:
            # 使用自定义提示词，替换变量
            return self.custom_prompt.format(
                title=title,
                url=url,
                content=content,
                max_length=self.max_summary_length,
                content_type=content_type
            )
        else:
            # 根据内容类型获取相应的分析模板
            template = self._get_analysis_template(content_type, emoji_prefix, self.max_summary_length)
            # 替换模板中的变量
            return template.format(
                title=title,
                url=url,
                content=content
            )

    def _format_llm_result(self, content_data: dict, analysis_text: str, content_type: str) -> str:
        """格式化LLM返回的结果"""
        title = content_data["title"]
        url = content_data["url"]

        # 限制摘要长度，避免结果过长
        if len(analysis_text) > self.max_summary_length:
            analysis_text = analysis_text[: self.max_summary_length] + "..."

        # 添加标题和格式美化
        link_emoji = "🔗" if self.enable_emoji else ""
        title_emoji = "📝" if self.enable_emoji else ""
        type_emoji = "📋" if self.enable_emoji else ""

        formatted_result = "**AI智能网页分析报告**\n\n"
        formatted_result += f"{link_emoji} **分析链接**: {url}\n"
        formatted_result += f"{title_emoji} **网页标题**: {title}\n"
        formatted_result += f"{type_emoji} **内容类型**: {content_type}\n\n"
        formatted_result += "---\n\n"
        formatted_result += analysis_text
        formatted_result += "\n\n---\n"
        formatted_result += "*分析完成，希望对您有帮助！*"

        return formatted_result

    async def analyze_with_llm(
        self, event: AstrMessageEvent, content_data: dict
    ) -> str:
        """调用大语言模型(LLM)进行智能内容分析和总结"""
        try:
            title = content_data["title"]
            content = content_data["content"]
            url = content_data["url"]

            # 检查LLM是否可用和启用
            if not self._check_llm_availability():
                # LLM不可用或未启用，使用基础分析
                return self.get_enhanced_analysis(content_data)

            # 获取LLM提供商
            provider_id = await self._get_llm_provider(event)
            if not provider_id:
                # 无法获取LLM提供商，使用基础分析
                return self.get_enhanced_analysis(content_data)

            # 智能检测内容类型
            content_type = self._detect_content_type(content)

            # 构建LLM提示词
            prompt = self._build_llm_prompt(content_data, content_type)

            # 调用LLM生成结果
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )

            if llm_resp and llm_resp.completion_text:
                # 格式化LLM结果
                return self._format_llm_result(
                    content_data,
                    llm_resp.completion_text.strip(),
                    content_type
                )
            else:
                # LLM调用失败，使用基础分析
                return self.get_enhanced_analysis(content_data)

        except Exception as e:
            # 使用统一错误处理
            return self._handle_error(ErrorType.LLM_ERROR, e, url)

    def get_enhanced_analysis(self, content_data: dict) -> str:
        """增强版基础分析 - LLM不可用时的智能回退方案"""
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
        """计算内容统计信息"""
        char_count = len(content)
        word_count = len(content.split())
        return {
            "char_count": char_count,
            "word_count": word_count
        }

    def _detect_content_type(self, content: str) -> str:
        """智能检测内容类型"""
        content_lower = content.lower()

        content_type_rules = [
            ("新闻资讯", ["新闻", "报道", "消息", "时事", "快讯", "头条", "要闻", "热点", "事件"]),
            ("教程指南", ["教程", "指南", "教学", "步骤", "方法", "如何", "怎样", "教程", "指南", "攻略", "技巧"]),
            ("个人博客", ["博客", "随笔", "日记", "个人", "观点", "感想", "感悟", "思考", "分享"]),
            ("产品介绍", ["产品", "服务", "购买", "价格", "优惠", "功能", "特性", "参数", "规格", "评测"]),
            ("技术文档", ["技术", "开发", "编程", "代码", "API", "SDK", "文档", "教程", "指南", "说明"]),
            ("学术论文", ["论文", "研究", "实验", "结论", "摘要", "关键词", "引用", "参考文献"]),
            ("商业分析", ["分析", "报告", "数据", "统计", "趋势", "预测", "市场", "行业"]),
            ("娱乐资讯", ["娱乐", "明星", "电影", "音乐", "综艺", "演唱会", "首映", "新歌"]),
            ("体育新闻", ["体育", "比赛", "赛事", "比分", "运动员", "冠军", "亚军", "季军"]),
            ("教育资讯", ["教育", "学校", "招生", "考试", "培训", "学习", "课程", "教材"])
        ]

        for type_name, keywords in content_type_rules:
            if any(keyword in content_lower for keyword in keywords):
                return type_name

        return "文章"

    def _extract_key_sentences(self, paragraphs: list) -> list:
        """提取关键句子作为内容摘要"""
        # 提取前3个段落作为关键句子
        return paragraphs[:3]

    def _evaluate_content_quality(self, char_count: int) -> str:
        """评估内容质量"""
        if char_count > 5000:
            return "内容详实"
        elif char_count > 1000:
            return "内容丰富"
        else:
            return "内容简洁"

    def _build_analysis_header(self) -> str:
        """构建分析结果的标题部分"""
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
        """构建分析结果的统计信息部分"""
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
        """构建分析结果的内容摘要部分"""
        search_emoji = "🔍" if self.enable_emoji else ""

        summary_info = []
        if self.enable_emoji:
            summary_info.append(f"**{search_emoji} 内容摘要**\n")
        else:
            summary_info.append("**内容摘要**\n")

        # 格式化关键句子
        formatted_sentences = []
        for sentence in key_sentences:
            truncated = sentence[:100] + ("..." if len(sentence) > 100 else "")
            formatted_sentences.append(f"• {truncated}")

        summary_info.append(f"{chr(10).join(formatted_sentences)}\n\n")
        return "".join(summary_info)

    def _build_analysis_note(self) -> str:
        """构建分析结果的分析说明部分"""
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
        """构建最终的分析结果"""
        # 构建分析结果
        result_parts = []
        result_parts.append(self._build_analysis_header())
        result_parts.append(self._build_basic_info(title, url, content_type, quality_indicator))
        result_parts.append(self._build_statistics_info(content_stats, paragraphs))
        result_parts.append(self._build_content_summary(key_sentences))
        result_parts.append(self._build_analysis_note())

        return "".join(result_parts)



    def _handle_error(self, error_type: str, original_error: Exception, url: str | None = None, context: dict | None = None) -> str:
        """统一错误处理方法"""
        # 获取错误配置
        error_config = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES["unknown_error"])
        error_message = error_config["message"]
        solution = error_config["solution"]
        severity = error_config["severity"]

        # 构建完整的上下文信息
        context_info = []
        if url:
            context_info.append(f"URL: {url}")
        if context:
            for key, value in context.items():
                context_info.append(f"{key}: {value}")
        context_str = " | ".join(context_info)

        # 构建日志信息
        log_message = f"{error_message}: {str(original_error)}"
        if context_str:
            log_message += f" ({context_str})"

        # 根据严重程度记录日志，所有错误级别都包含堆栈跟踪
        if severity == ErrorSeverity.INFO:
            logger.info(log_message, exc_info=True)
        elif severity == ErrorSeverity.WARNING:
            logger.warning(log_message, exc_info=True)
        elif severity == ErrorSeverity.ERROR:
            logger.error(log_message, exc_info=True)
        elif severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=True)

        # 生成用户友好的错误信息
        user_message = []
        user_message.append(f"❌ {error_message}")

        # 添加上下文信息
        if url:
            user_message.append(f"🔗 相关链接: {url}")

        # 添加错误详情，仅显示关键信息，避免过长
        error_detail = str(original_error)
        if len(error_detail) > 100:
            error_detail = error_detail[:100] + "..."
        user_message.append(f"📋 错误详情: {error_detail}")

        # 添加建议解决方案
        user_message.append(f"💡 建议解决方案: {solution}")

        # 添加错误类型和严重程度（仅在调试模式或严重错误时显示）
        if severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
            user_message.append(f"⚠️  错误类型: {error_type}")
            user_message.append(f"🔴 严重程度: {severity.upper()}")

        return "\n".join(user_message)

    def _get_error_type(self, exception: Exception) -> str:
        """根据异常类型获取对应的错误类型"""

        from httpx import ConnectError, HTTPError, TimeoutException

        exception_type = type(exception).__name__
        exception_msg = str(exception).lower()

        # 网络相关错误
        if isinstance(exception, HTTPError):
            if isinstance(exception, TimeoutException):
                return ErrorType.NETWORK_TIMEOUT
            elif isinstance(exception, ConnectError):
                return ErrorType.NETWORK_CONNECTION
            else:
                return ErrorType.NETWORK_ERROR
        elif "timeout" in exception_type.lower() or "timeout" in exception_msg:
            return ErrorType.NETWORK_TIMEOUT
        elif "connect" in exception_type.lower() or "connection" in exception_msg:
            return ErrorType.NETWORK_CONNECTION
        elif "network" in exception_type.lower() or "http" in exception_type.lower():
            return ErrorType.NETWORK_ERROR

        # 解析相关错误
        elif "parse" in exception_type.lower() or "soup" in exception_type.lower() or "lxml" in exception_type.lower():
            return ErrorType.HTML_PARSING
        elif "empty" in exception_msg or "none" in exception_msg or "null" in exception_msg:
            return ErrorType.CONTENT_EMPTY
        elif "parse" in exception_msg:
            return ErrorType.PARSING_ERROR

        # LLM相关错误
        elif "llm" in exception_type.lower() or "llm" in exception_msg:
            return ErrorType.LLM_ERROR
        elif "generate" in exception_type.lower() or "generate" in exception_msg:
            return ErrorType.LLM_ERROR
        elif "timeout" in exception_msg and "llm" in exception_msg:
            return ErrorType.LLM_TIMEOUT
        elif "invalid" in exception_msg or "format" in exception_msg:
            return ErrorType.LLM_INVALID_RESPONSE
        elif "permission" in exception_msg or "auth" in exception_msg or "key" in exception_msg:
            return ErrorType.LLM_PERMISSION

        # 截图相关错误
        elif "screenshot" in exception_type.lower() or "screenshot" in exception_msg:
            return ErrorType.SCREENSHOT_ERROR
        elif "browser" in exception_type.lower() or "playwright" in exception_type.lower():
            return ErrorType.BROWSER_ERROR

        # 缓存相关错误
        elif "cache" in exception_type.lower() or "cache" in exception_msg:
            return ErrorType.CACHE_ERROR
        elif "write" in exception_msg or "save" in exception_msg:
            return ErrorType.CACHE_WRITE
        elif "read" in exception_msg or "load" in exception_msg:
            return ErrorType.CACHE_READ

        # 配置相关错误
        elif "config" in exception_type.lower() or "setting" in exception_type.lower():
            return ErrorType.CONFIG_ERROR
        elif "invalid" in exception_msg:
            return ErrorType.CONFIG_INVALID

        # 权限相关错误
        elif "permission" in exception_type.lower() or "auth" in exception_type.lower():
            return ErrorType.PERMISSION_ERROR
        elif "blocked" in exception_msg or "deny" in exception_msg:
            return ErrorType.DOMAIN_BLOCKED

        # 其他错误
        elif "internal" in exception_type.lower() or "internal" in exception_msg:
            return ErrorType.INTERNAL_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR

    async def _auto_recall_message(self, bot, message_id: int, recall_time: int) -> None:
        """自动撤回消息"""
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

    async def _send_processing_message(self, event: AstrMessageEvent, message: str) -> tuple:
        """发送正在分析的消息并设置自动撤回"""
        import asyncio

        # 获取bot实例
        bot = event.bot
        message_id = None

        # 直接调用bot的发送消息方法，获取消息ID
        try:
            # 根据事件类型选择发送方法
            send_result = None
            group_id = None
            user_id = None

            # 方法1：使用AiocqhttpMessageEvent的方法获取
            if hasattr(event, "get_group_id"):
                group_id = event.get_group_id()
            if hasattr(event, "get_sender_id"):
                user_id = event.get_sender_id()

            # 方法2：判断是否为私聊
            is_private = False
            if hasattr(event, "is_private_chat"):
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
                if not user_id and hasattr(event, "get_sender_id"):
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
                    if hasattr(event, "send"):
                        await event.send(response)
                    return None, bot
            else:
                # 无法确定消息类型，使用原始方式发送并记录详细信息
                logger.error(f"无法确定消息类型，event类型: {type(event)}, event方法: get_group_id={hasattr(event, 'get_group_id')}, get_sender_id={hasattr(event, 'get_sender_id')}, is_private_chat={hasattr(event, 'is_private_chat')}")
                # 尝试使用event.plain_result发送，虽然无法获取message_id
                response = event.plain_result(message)
                # 使用event的send方法发送
                if hasattr(event, "send"):
                    await event.send(response)
                return None, bot

            # 检查send_result是否包含message_id
            if isinstance(send_result, dict):
                message_id = send_result.get("message_id")
            elif hasattr(send_result, "message_id"):
                message_id = send_result.message_id

            logger.debug(f"发送处理消息成功，message_id: {message_id}")

            # 如果获取到message_id且启用了自动撤回
            if message_id and self.enable_recall:
                # 定时撤回模式
                if self.recall_type == "time_based":
                    logger.info(f"创建定时撤回任务，message_id: {message_id}，延迟: {self.recall_time}秒")

                    async def _recall_task():
                        try:
                            await asyncio.sleep(self.recall_time)
                            await bot.delete_msg(message_id=message_id)
                            logger.info(f"已定时撤回消息: {message_id}")
                        except Exception as e:
                            logger.error(f"定时撤回消息失败: {e}")

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
                # 智能撤回模式 - 只发送消息，不创建定时任务，等待分析完成后立即撤回
                elif self.recall_type == "smart" and self.smart_recall_enabled:
                    logger.info(f"已发送智能撤回消息，message_id: {message_id}，等待分析完成后立即撤回")

        except Exception as e:
            logger.error(f"发送处理消息或设置撤回失败: {e}")

        return message_id, bot

    @filter.command("web_config", alias={"网页分析配置", "网页分析设置"})
    async def show_config(self, event: AstrMessageEvent):
        """显示当前插件的详细配置信息"""
        config_info = f"""**网页分析插件配置信息**

**基本设置**
- 最大内容长度: {self.max_content_length} 字符
- 请求超时时间: {self.timeout} 秒
- LLM智能分析: {"✅ 已启用" if self.llm_enabled else "❌ 已禁用"}
- 分析模式: {self.analysis_mode}
- 自动分析链接: {"✅ 已启用" if self.auto_analyze else "❌ 已禁用"}
- 合并转发功能(群聊): {"✅ 已启用" if self.merge_forward_enabled["group"] else "❌ 已禁用"}
- 合并转发功能(私聊): {"✅ 已启用" if self.merge_forward_enabled["private"] else "❌ 已禁用"}
- 合并转发包含截图: {"✅ 已启用" if self.merge_forward_enabled["include_screenshot"] else "❌ 已禁用"}

**并发处理设置**
- 最大并发数: {self.max_concurrency}
- 动态并发控制: {"✅ 已启用" if self.dynamic_concurrency else "❌ 已禁用"}
- 优先级调度: {"✅ 已启用" if self.enable_priority_scheduling else "❌ 已禁用"}

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
- 启用截图裁剪: {"✅ 已启用" if self.enable_crop else "❌ 已禁用"}
- 裁剪区域: {self.crop_area}
- 启用水印: {"✅ 已启用" if self.enable_watermark else "❌ 已禁用"}
- 水印文本: {self.watermark_text}
- 水印字体大小: {self.watermark_font_size}
- 水印透明度: {self.watermark_opacity}%
- 水印位置: {self.watermark_position}
- 启用LLM自主决策: {"✅ 已启用" if self.enable_llm_decision else "❌ 已禁用"}

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
- 启用缓存预加载: {"✅ 已启用" if self.cache_preload_enabled else "❌ 已禁用"}
- 预加载缓存数量: {self.cache_preload_count} 个

**内容提取设置**
- 启用特定内容提取: {"✅ 已启用" if self.enable_specific_extraction else "❌ 已禁用"}
- 提取内容类型: {", ".join(self.extract_types)}

*提示: 如需修改配置，请在AstrBot管理面板中编辑插件配置*"""

        yield event.plain_result(config_info)

    @filter.command("test_merge", alias={"测试合并转发", "测试转发"})
    async def test_merge_forward(self, event: AstrMessageEvent):
        """测试合并转发功能"""
        from astrbot.api.message_components import Node, Nodes, Plain

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
                "hybrid": "混合模式"
            }
            mode_info = "**当前分析模式**\n\n"
            mode_info += f"- 模式: {mode_names.get(self.analysis_mode, self.analysis_mode)} ({self.analysis_mode})\n"
            mode_info += f"- 自动分析: {'✅ 已启用' if self.auto_analyze else '❌ 已禁用'}\n\n"
            mode_info += "使用 `/web_mode <模式>` 切换模式\n"
            mode_info += "支持的模式: auto, manual, hybrid"

            yield event.plain_result(mode_info)
            return

        # 解析模式参数
        mode = message_parts[1].lower() if len(message_parts) > 1 else ""
        valid_modes = ["auto", "manual", "hybrid"]

        # 验证模式是否有效
        if mode not in valid_modes:
            yield event.plain_result(
                f"无效的模式，请使用: {', '.join(valid_modes)}"
            )
            return

        # 更新分析模式
        self.analysis_mode = mode
        self.auto_analyze = (mode == "auto")

        # 保存配置
        analysis_settings = self.config.get("analysis_settings", {})
        analysis_settings["analysis_mode"] = mode
        self.config["analysis_settings"] = analysis_settings
        self.config.save_config()

        mode_names = {
            "auto": "自动分析",
            "manual": "手动分析",
            "hybrid": "混合模式"
        }
        yield event.plain_result(
            f"✅ 已切换到 {mode_names.get(mode, mode)} 模式"
        )

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
            import json
            import os
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
            from astrbot.api.message_components import File, Plain

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

    def _check_cache(self, url: str) -> dict:
        """检查指定URL的缓存是否存在且有效"""
        if not self.enable_cache:
            return None

        # 规范化URL，统一格式
        normalized_url = self.analyzer.normalize_url(url)
        return self.cache_manager.get(normalized_url)

    def _update_cache(self, url: str, result: dict, content: str = None):
        """更新指定URL的缓存，支持基于内容哈希的缓存策略"""
        if not self.enable_cache:
            return

        # 规范化URL，统一格式
        normalized_url = self.analyzer.normalize_url(url)

        # 如果提供了内容，使用基于内容哈希的缓存策略
        if content:
            self.cache_manager.set_with_content_hash(normalized_url, result, content)
        else:
            # 否则使用普通的URL缓存策略
            self.cache_manager.set(normalized_url, result)

    def _clean_cache(self):
        """清理过期缓存"""
        # 缓存管理器会自动清理过期缓存，这里留空即可
        pass

    async def _translate_content(self, event: AstrMessageEvent, content: str) -> str:
        """翻译网页内容"""
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
        """提取特定类型的内容"""
        if not self.enable_specific_extraction:
            return {}

        try:
            # 直接使用已有analyzer实例，避免重复创建
            return self.analyzer.extract_specific_content(html, url, self.extract_types)
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            return {}

    async def _send_analysis_result(self, event, analysis_results):
        """发送分析结果，根据配置决定是否使用合并转发"""
        # 检查是否有有效的分析结果
        if not analysis_results:
            logger.info("没有分析结果，不发送消息")
            return

        # 检查是否所有结果都是错误结果（没有截图且结果包含错误关键词）
        all_errors = True
        for result in analysis_results:
            # 如果有截图，说明至少有一个成功的结果
            if result.get("screenshot"):
                all_errors = False
                break
            # 检查结果是否包含错误关键词
            result_text = result.get("result", "")
            if not any(keyword in result_text for keyword in ["失败", "错误", "无法", "❌"]):
                all_errors = False
                break

        # 如果所有结果都是错误，不发送消息
        if all_errors:
            logger.info("所有URL分析失败，不发送消息")
            return

        try:
            import os
            import tempfile

            from astrbot.api.message_components import Image, Node, Nodes, Plain

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
