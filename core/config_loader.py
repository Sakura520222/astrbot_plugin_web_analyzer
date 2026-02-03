"""
配置加载模块

负责加载、验证和初始化所有配置项。
支持新旧配置格式的兼容性映射。
"""

from typing import Any
import sys
from pathlib import Path

# 确保父目录在 Python 路径中
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from astrbot.api import logger
from astrbot.api.star import Context

from core.cache import CacheManager
from core.analyzer import WebAnalyzer
from core.utils import WebAnalyzerUtils


class ConfigLoader:
    """配置加载器类"""

    # 旧配置键名到新配置键名的映射表
    OLD_TO_NEW_MAPPING = {
        # 网络设置
        "request_timeout": "request_timeout_s",
        "retry_delay": "retry_delay_s",
        "cache_expire_time": "cache_expire_time_min",
        "memory_threshold": "memory_threshold_percent",
        "screenshot_wait_time": "screenshot_wait_ms",
        "recall_time": "recall_time_s",
        # 合并转发旧格式（v1.4.5之前）
        "merge_forward_enabled": "_merge_forward_legacy",
    }

    # 需要特殊处理的嵌套配置路径
    NESTED_CONFIG_PATHS = {
        "网络设置": {
            "max_content_length": "max_content_length",
            "request_timeout_s": "request_timeout_s",
            "retry_count": "retry_count",
            "retry_delay_s": "retry_delay_s",
            "user_agent": "user_agent",
            "proxy": "proxy",
            "max_concurrency": "max_concurrency",
        },
        "域名管理": {
            "enable_unified_domain": "enable_unified_domain",
            "allowed_domains": "allowed_domains",
            "blocked_domains": "blocked_domains",
        },
        "缓存设置": {
            "enable_cache": "enable_cache",
            "cache_expire_time_min": "cache_expire_time_min",
            "max_cache_size": "max_cache_size",
            "cache_preload_enabled": "cache_preload_enabled",
            "cache_preload_count": "cache_preload_count",
        },
        "资源管理": {
            "enable_memory_monitor": "enable_memory_monitor",
            "memory_threshold_percent": "memory_threshold_percent",
        },
        "分析设置": {
            "analysis_mode": "analysis_mode",
            "max_summary_length": "max_summary_length",
            "enable_emoji": "enable_emoji",
            "enable_statistics": "enable_statistics",
        },
        "内容提取": {
            "enable_specific_extraction": "enable_specific_extraction",
            "extract_types": "extract_types",
        },
        "展示设置": {
            "send_content_type": "send_content_type",
            "result_template": "result_template",
        },
        "结果折叠": {
            "enable_collapsible": "enable_collapsible",
            "collapse_threshold": "collapse_threshold",
        },
        "自定义模板": {
            "enable_custom_template": "enable_custom_template",
            "template_content": "template_content",
            "template_format": "template_format",
        },
        "URL识别": {
            "enable_no_protocol_url": "enable_no_protocol_url",
            "default_protocol": "default_protocol",
        },
        "网页截图": {
            "enable_screenshot": "enable_screenshot",
            "screenshot_quality": "screenshot_quality",
            "screenshot_width": "screenshot_width",
            "screenshot_height": "screenshot_height",
            "screenshot_full_page": "screenshot_full_page",
            "screenshot_wait_ms": "screenshot_wait_ms",
            "screenshot_format": "screenshot_format",
            "enable_crop": "enable_crop",
            "crop_area": "crop_area",
        },
        "智能分析": {
            "llm_enabled": "llm_enabled",
            "llm_provider": "llm_provider",
            "enable_llm_decision": "enable_llm_decision",
            "custom_prompt": "custom_prompt",
        },
        "翻译功能": {
            "enable_translation": "enable_translation",
            "target_language": "target_language",
            "translation_provider": "translation_provider",
            "custom_translation_prompt": "custom_translation_prompt",
        },
        "合并转发": {
            "group": "merge_forward_group",
            "private": "merge_forward_private",
            "include_screenshot": "merge_forward_include_screenshot",
        },
        "群聊设置": {
            "group_blacklist": "group_blacklist",
        },
        "消息撤回": {
            "enable_recall": "enable_recall",
            "recall_type": "recall_type",
            "recall_time_s": "recall_time_s",
            "smart_recall_enabled": "smart_recall_enabled",
        },
    }

    @staticmethod
    def load_all_config(config: Any, context: Context) -> dict:
        """加载所有配置项

        Args:
            config: AstrBot配置对象
            context: AstrBot上下文对象

        Returns:
            包含所有配置项的字典
        """
        # 先进行兼容性转换
        config = ConfigLoader._apply_compatibility_mapping(config)

        config_dict = {}

        # 加载各类配置
        config_dict.update(ConfigLoader._load_basic_settings(config))
        config_dict.update(ConfigLoader._load_analysis_settings(config))
        config_dict.update(ConfigLoader._load_display_settings(config))
        config_dict.update(ConfigLoader._load_llm_settings(config))
        config_dict.update(ConfigLoader._load_message_settings(config))

        return config_dict

    @staticmethod
    def _apply_compatibility_mapping(config: Any) -> dict:
        """应用兼容性映射，将旧配置转换为新格式

        Args:
            config: 原始配置对象

        Returns:
            转换后的配置字典
        """
        # 将config对象转换为字典（如果不是字典的话）
        if not isinstance(config, dict):
            config_dict = {}
            # 尝试获取所有配置键
            try:
                for key in dir(config):
                    if not key.startswith('_'):
                        try:
                            config_dict[key] = getattr(config, key)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"配置对象转换失败: {e}")
                return {}
        else:
            config_dict = config.copy()

        # 检测是否为新格式配置（包含"基础设置"等顶级键）
        is_new_format = any(
            key in config_dict
            for key in ["基础设置", "分析设置", "展示设置", "智能分析", "消息管理"]
        )

        if is_new_format:
            # 新格式配置，直接返回
            return config_dict

        # 旧格式配置，需要转换
        logger.info("检测到旧格式配置，正在自动转换为新格式...")
        new_config = {}

        # 映射网络设置
        network_settings = {}
        old_network = config_dict.get("network_settings", {})
        network_settings["max_content_length"] = old_network.get("max_content_length", 10000)
        network_settings["request_timeout_s"] = old_network.get("request_timeout", 30)
        network_settings["retry_count"] = old_network.get("retry_count", 3)
        network_settings["retry_delay_s"] = old_network.get("retry_delay", 2)
        network_settings["user_agent"] = old_network.get("user_agent", "Mozilla/5.0")
        network_settings["proxy"] = old_network.get("proxy", "")
        network_settings["max_concurrency"] = old_network.get("max_concurrency", 5)

        # 映射域名设置
        domain_settings = {}
        old_domain = config_dict.get("domain_settings", {})
        domain_settings["enable_unified_domain"] = old_domain.get("enable_unified_domain", True)
        domain_settings["allowed_domains"] = old_domain.get("allowed_domains", "")
        domain_settings["blocked_domains"] = old_domain.get("blocked_domains", "")

        # 映射缓存设置
        cache_settings = {}
        old_cache = config_dict.get("cache_settings", {})
        cache_settings["enable_cache"] = old_cache.get("enable_cache", True)
        cache_settings["cache_expire_time_min"] = old_cache.get("cache_expire_time", 1440)
        cache_settings["max_cache_size"] = old_cache.get("max_cache_size", 100)
        cache_settings["cache_preload_enabled"] = old_cache.get("cache_preload_enabled", False)
        cache_settings["cache_preload_count"] = old_cache.get("cache_preload_count", 20)

        # 映射资源设置
        resource_settings = {}
        old_resource = config_dict.get("resource_settings", {})
        resource_settings["enable_memory_monitor"] = old_resource.get("enable_memory_monitor", True)
        resource_settings["memory_threshold_percent"] = old_resource.get("memory_threshold", 80.0)

        # 构建基础设置
        new_config["基础设置"] = {
            "网络设置": network_settings,
            "域名管理": domain_settings,
            "缓存设置": cache_settings,
            "资源管理": resource_settings,
        }

        # 映射分析设置
        analysis_settings = {}
        old_analysis = config_dict.get("analysis_settings", {})
        analysis_settings["analysis_mode"] = old_analysis.get("analysis_mode", "auto")
        analysis_settings["max_summary_length"] = old_analysis.get("max_summary_length", 2000)
        analysis_settings["enable_emoji"] = old_analysis.get("enable_emoji", True)
        analysis_settings["enable_statistics"] = old_analysis.get("enable_statistics", True)

        # 内容提取设置
        content_extraction = {}
        old_extraction = config_dict.get("content_extraction_settings", {})
        content_extraction["enable_specific_extraction"] = old_extraction.get(
            "enable_specific_extraction", False
        )
        content_extraction["extract_types"] = old_extraction.get("extract_types", "title\ncontent")

        new_config["分析设置"] = {
            **analysis_settings,
            "内容提取": content_extraction,
        }

        # 映射展示设置
        display_settings = {}
        old_analysis = config_dict.get("analysis_settings", {})
        display_settings["send_content_type"] = old_analysis.get("send_content_type", "both")
        display_settings["result_template"] = old_analysis.get("result_template", "default")

        # 结果折叠
        collapsible = {}
        collapsible["enable_collapsible"] = old_analysis.get("enable_collapsible", False)
        collapsible["collapse_threshold"] = old_analysis.get("collapse_threshold", 1500)

        # 自定义模板
        old_template = config_dict.get("template_settings", {})
        custom_template = {}
        custom_template["enable_custom_template"] = old_template.get("enable_custom_template", False)
        custom_template["template_content"] = old_template.get("template_content", "")
        custom_template["template_format"] = old_template.get("template_format", "markdown")

        # URL识别
        url_recognition = {}
        url_recognition["enable_no_protocol_url"] = old_analysis.get("enable_no_protocol_url", False)
        url_recognition["default_protocol"] = old_analysis.get("default_protocol", "https")

        # 网页截图
        old_screenshot = config_dict.get("screenshot_settings", {})
        screenshot = {}
        screenshot["enable_screenshot"] = old_screenshot.get("enable_screenshot", True)
        screenshot["screenshot_quality"] = old_screenshot.get("screenshot_quality", 80)
        screenshot["screenshot_width"] = old_screenshot.get("screenshot_width", 1280)
        screenshot["screenshot_height"] = old_screenshot.get("screenshot_height", 720)
        screenshot["screenshot_full_page"] = old_screenshot.get("screenshot_full_page", False)
        screenshot["screenshot_wait_ms"] = old_screenshot.get("screenshot_wait_time", 2000)
        screenshot["screenshot_format"] = old_screenshot.get("screenshot_format", "jpeg")
        screenshot["enable_crop"] = old_screenshot.get("enable_crop", False)
        screenshot["crop_area"] = old_screenshot.get("crop_area", "[0, 0, 1280, 720]")

        new_config["展示设置"] = {
            **display_settings,
            "结果折叠": collapsible,
            "自定义模板": custom_template,
            "URL识别": url_recognition,
            "网页截图": screenshot,
        }

        # 映射智能分析
        old_llm = config_dict.get("llm_settings", {})
        llm_settings = {}
        llm_settings["llm_enabled"] = old_llm.get("llm_enabled", True)
        llm_settings["llm_provider"] = old_llm.get("llm_provider", "")
        llm_settings["enable_llm_decision"] = old_analysis.get("enable_llm_decision", False)
        llm_settings["custom_prompt"] = old_llm.get("custom_prompt", "")

        # 翻译功能
        old_translation = config_dict.get("translation_settings", {})
        translation = {}
        translation["enable_translation"] = old_translation.get("enable_translation", False)
        translation["target_language"] = old_translation.get("target_language", "zh")
        translation["translation_provider"] = old_translation.get("translation_provider", "llm")
        translation["custom_translation_prompt"] = old_translation.get("custom_translation_prompt", "")

        new_config["智能分析"] = {
            **llm_settings,
            "翻译功能": translation,
        }

        # 映射消息管理
        # 合并转发
        old_merge = config_dict.get("merge_forward_settings", {})
        merge_forward = {}
        # 处理新旧格式
        if "group" in old_merge:
            # 新格式
            merge_forward["group"] = old_merge.get("group", False)
            merge_forward["private"] = old_merge.get("private", False)
            merge_forward["include_screenshot"] = old_merge.get("include_screenshot", False)
        else:
            # 旧格式兼容
            merge_forward["group"] = False
            merge_forward["private"] = False
            merge_forward["include_screenshot"] = False

        # 群聊设置
        old_group = config_dict.get("group_settings", {})
        group_settings = {}
        group_settings["group_blacklist"] = old_group.get("group_blacklist", "")

        # 消息撤回
        old_recall = config_dict.get("recall_settings", {})
        recall = {}
        recall["enable_recall"] = old_recall.get("enable_recall", True)
        recall["recall_type"] = old_recall.get("recall_type", "smart")
        recall["recall_time_s"] = old_recall.get("recall_time", 10)
        recall["smart_recall_enabled"] = old_recall.get("smart_recall_enabled", True)

        new_config["消息管理"] = {
            "合并转发": merge_forward,
            "群聊设置": group_settings,
            "消息撤回": recall,
        }

        logger.info("旧格式配置已成功转换为新格式")
        return new_config

    @staticmethod
    def _get_nested_value(config: dict, category: str, subcategory: str, key: str, default=None):
        """从嵌套配置中获取值

        Args:
            config: 配置字典
            category: 一级分类（如"基础设置"）
            subcategory: 二级分类（如"网络设置"）
            key: 配置键名
            default: 默认值

        Returns:
            配置值或默认值
        """
        try:
            return config.get(category, {}).get(subcategory, {}).get(key, default)
        except (AttributeError, KeyError):
            return default

    @staticmethod
    def _get_direct_value(config: dict, category: str, key: str, default=None):
        """从一级分类中直接获取值（非嵌套）

        Args:
            config: 配置字典
            category: 一级分类
            key: 配置键名
            default: 默认值

        Returns:
            配置值或默认值
        """
        try:
            return config.get(category, {}).get(key, default)
        except (AttributeError, KeyError):
            return default

    @staticmethod
    def _load_basic_settings(config: dict) -> dict:
        """加载基础设置（网络、域名、缓存、资源）"""
        config_dict = {}

        # 网络设置
        config_dict["max_content_length"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "max_content_length", 10000
        )
        config_dict["request_timeout_s"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "request_timeout_s", 30
        )
        config_dict["retry_count"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "retry_count", 3
        )
        config_dict["retry_delay_s"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "retry_delay_s", 2
        )
        config_dict["user_agent"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "user_agent", "Mozilla/5.0"
        )
        proxy = ConfigLoader._get_nested_value(config, "基础设置", "网络设置", "proxy", "")
        config_dict["proxy"] = ConfigLoader._validate_proxy(proxy)
        config_dict["max_concurrency"] = ConfigLoader._get_nested_value(
            config, "基础设置", "网络设置", "max_concurrency", 5
        )

        # 域名管理
        allowed_text = ConfigLoader._get_nested_value(
            config, "基础设置", "域名管理", "allowed_domains", ""
        )
        config_dict["allowed_domains"] = WebAnalyzerUtils.parse_domain_list(allowed_text)
        blocked_text = ConfigLoader._get_nested_value(
            config, "基础设置", "域名管理", "blocked_domains", ""
        )
        config_dict["blocked_domains"] = WebAnalyzerUtils.parse_domain_list(blocked_text)
        config_dict["enable_unified_domain"] = ConfigLoader._get_nested_value(
            config, "基础设置", "域名管理", "enable_unified_domain", True
        )

        # 缓存设置
        config_dict["enable_cache"] = ConfigLoader._get_nested_value(
            config, "基础设置", "缓存设置", "enable_cache", True
        )
        config_dict["cache_expire_time_min"] = ConfigLoader._get_nested_value(
            config, "基础设置", "缓存设置", "cache_expire_time_min", 1440
        )
        config_dict["max_cache_size"] = ConfigLoader._get_nested_value(
            config, "基础设置", "缓存设置", "max_cache_size", 100
        )
        config_dict["cache_preload_enabled"] = ConfigLoader._get_nested_value(
            config, "基础设置", "缓存设置", "cache_preload_enabled", False
        )
        config_dict["cache_preload_count"] = ConfigLoader._get_nested_value(
            config, "基础设置", "缓存设置", "cache_preload_count", 20
        )

        # 资源管理
        config_dict["enable_memory_monitor"] = ConfigLoader._get_nested_value(
            config, "基础设置", "资源管理", "enable_memory_monitor", True
        )
        config_dict["memory_threshold_percent"] = ConfigLoader._get_nested_value(
            config, "基础设置", "资源管理", "memory_threshold_percent", 80.0
        )

        return config_dict

    @staticmethod
    def _load_analysis_settings(config: dict) -> dict:
        """加载分析设置"""
        config_dict = {}

        config_dict["analysis_mode"] = ConfigLoader._get_direct_value(
            config, "分析设置", "analysis_mode", "auto"
        )
        config_dict["auto_analyze"] = config_dict["analysis_mode"] == "auto"
        config_dict["max_summary_length"] = ConfigLoader._get_direct_value(
            config, "分析设置", "max_summary_length", 2000
        )
        config_dict["enable_emoji"] = ConfigLoader._get_direct_value(
            config, "分析设置", "enable_emoji", True
        )
        config_dict["enable_statistics"] = ConfigLoader._get_direct_value(
            config, "分析设置", "enable_statistics", True
        )

        # 内容提取
        config_dict["enable_specific_extraction"] = ConfigLoader._get_nested_value(
            config, "分析设置", "内容提取", "enable_specific_extraction", False
        )
        extract_types_text = ConfigLoader._get_nested_value(
            config, "分析设置", "内容提取", "extract_types", "title\ncontent"
        )
        config_dict["extract_types"] = WebAnalyzerUtils.parse_extract_types(extract_types_text)
        config_dict["extract_types"] = WebAnalyzerUtils.validate_extract_types(
            config_dict["extract_types"]
        )
        config_dict["extract_types"] = WebAnalyzerUtils.ensure_minimal_extract_types(
            config_dict["extract_types"]
        )
        config_dict["extract_types"] = WebAnalyzerUtils.add_required_extract_types(
            config_dict["extract_types"]
        )

        return config_dict

    @staticmethod
    def _load_display_settings(config: dict) -> dict:
        """加载展示设置"""
        config_dict = {}

        # 基本展示设置
        config_dict["send_content_type"] = ConfigLoader._get_direct_value(
            config, "展示设置", "send_content_type", "both"
        )
        config_dict["result_template"] = ConfigLoader._get_direct_value(
            config, "展示设置", "result_template", "default"
        )

        # 结果折叠
        config_dict["enable_collapsible"] = ConfigLoader._get_nested_value(
            config, "展示设置", "结果折叠", "enable_collapsible", False
        )
        config_dict["collapse_threshold"] = ConfigLoader._get_nested_value(
            config, "展示设置", "结果折叠", "collapse_threshold", 1500
        )

        # 自定义模板
        config_dict["enable_custom_template"] = ConfigLoader._get_nested_value(
            config, "展示设置", "自定义模板", "enable_custom_template", False
        )
        config_dict["template_content"] = ConfigLoader._get_nested_value(
            config,
            "展示设置",
            "自定义模板",
            "template_content",
            "# 网页分析结果\n\n## 基本信息\n- 标题: {title}\n- 链接: {url}\n- 内容类型: {content_type}\n- 分析时间: {date} {time}\n\n## 内容摘要\n{summary}\n\n## 详细分析\n{analysis_result}\n\n## 内容统计\n{stats}",
        )
        config_dict["template_format"] = ConfigLoader._get_nested_value(
            config, "展示设置", "自定义模板", "template_format", "markdown"
        )

        # URL识别
        config_dict["enable_no_protocol_url"] = ConfigLoader._get_nested_value(
            config, "展示设置", "URL识别", "enable_no_protocol_url", False
        )
        config_dict["default_protocol"] = ConfigLoader._get_nested_value(
            config, "展示设置", "URL识别", "default_protocol", "https"
        )

        # 网页截图
        config_dict["enable_screenshot"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "enable_screenshot", True
        )
        config_dict["screenshot_quality"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_quality", 80
        )
        config_dict["screenshot_width"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_width", 1280
        )
        config_dict["screenshot_height"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_height", 720
        )
        config_dict["screenshot_full_page"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_full_page", False
        )
        config_dict["screenshot_wait_ms"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_wait_ms", 2000
        )
        config_dict["screenshot_format"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "screenshot_format", "jpeg"
        )
        config_dict["enable_crop"] = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "enable_crop", False
        )
        crop_area = ConfigLoader._get_nested_value(
            config, "展示设置", "网页截图", "crop_area", "[0, 0, 1280, 720]"
        )
        default_crop_area = [0, 0, 1280, 720]
        if isinstance(crop_area, str):
            config_dict["crop_area"] = ConfigLoader._validate_crop_area(crop_area, default_crop_area)
        else:
            config_dict["crop_area"] = crop_area if isinstance(crop_area, list) else default_crop_area

        return config_dict

    @staticmethod
    def _load_llm_settings(config: dict) -> dict:
        """加载LLM智能分析设置"""
        config_dict = {}

        config_dict["llm_enabled"] = ConfigLoader._get_direct_value(
            config, "智能分析", "llm_enabled", True
        )
        config_dict["llm_provider"] = ConfigLoader._get_direct_value(
            config, "智能分析", "llm_provider", ""
        )
        config_dict["enable_llm_decision"] = ConfigLoader._get_direct_value(
            config, "智能分析", "enable_llm_decision", False
        )
        config_dict["custom_prompt"] = ConfigLoader._get_direct_value(
            config, "智能分析", "custom_prompt", ""
        )

        # 翻译功能
        config_dict["enable_translation"] = ConfigLoader._get_nested_value(
            config, "智能分析", "翻译功能", "enable_translation", False
        )
        config_dict["target_language"] = ConfigLoader._get_nested_value(
            config, "智能分析", "翻译功能", "target_language", "zh"
        )
        config_dict["translation_provider"] = ConfigLoader._get_nested_value(
            config, "智能分析", "翻译功能", "translation_provider", "llm"
        )
        config_dict["custom_translation_prompt"] = ConfigLoader._get_nested_value(
            config, "智能分析", "翻译功能", "custom_translation_prompt", ""
        )

        return config_dict

    @staticmethod
    def _load_message_settings(config: dict) -> dict:
        """加载消息管理设置"""
        config_dict = {}

        # 合并转发
        config_dict["merge_forward_group"] = ConfigLoader._get_nested_value(
            config, "消息管理", "合并转发", "group", False
        )
        config_dict["merge_forward_private"] = ConfigLoader._get_nested_value(
            config, "消息管理", "合并转发", "private", False
        )
        config_dict["merge_forward_include_screenshot"] = ConfigLoader._get_nested_value(
            config, "消息管理", "合并转发", "include_screenshot", False
        )

        # 群聊设置
        group_blacklist_text = ConfigLoader._get_nested_value(
            config, "消息管理", "群聊设置", "group_blacklist", ""
        )
        config_dict["group_blacklist"] = WebAnalyzerUtils.parse_group_list(group_blacklist_text)

        # 消息撤回
        config_dict["enable_recall"] = ConfigLoader._get_nested_value(
            config, "消息管理", "消息撤回", "enable_recall", True
        )
        config_dict["recall_type"] = ConfigLoader._get_nested_value(
            config, "消息管理", "消息撤回", "recall_type", "smart"
        )
        config_dict["recall_time_s"] = ConfigLoader._get_nested_value(
            config, "消息管理", "消息撤回", "recall_time_s", 10
        )
        config_dict["smart_recall_enabled"] = ConfigLoader._get_nested_value(
            config, "消息管理", "消息撤回", "smart_recall_enabled", True
        )

        return config_dict

    @staticmethod
    def _validate_proxy(proxy: str) -> str:
        """验证代理格式是否正确"""
        if not proxy:
            return ""

        try:
            from urllib.parse import urlparse

            parsed = urlparse(proxy)
            if not all([parsed.scheme, parsed.netloc]):
                logger.warning(f"无效的代理格式: {proxy}，将忽略代理设置")
                return ""
        except Exception as e:
            logger.warning(f"解析代理失败: {proxy}，将忽略代理设置，错误: {e}")
            return ""

        return proxy

    @staticmethod
    def _validate_crop_area(crop_area_str: str, default_area: list) -> list:
        """验证和处理裁剪区域配置"""
        try:
            crop_area = eval(crop_area_str)
            if isinstance(crop_area, list) and len(crop_area) == 4:
                return crop_area
            else:
                logger.warning(f"裁剪区域格式无效: {crop_area_str}，将使用默认值")
                return default_area
        except Exception as e:
            logger.warning(
                f"解析裁剪区域失败: {crop_area_str}，错误: {e}，将使用默认值"
            )
            return default_area