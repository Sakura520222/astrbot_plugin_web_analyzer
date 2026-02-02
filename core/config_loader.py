# -*- coding: utf-8 -*-
"""
配置加载模块

负责加载、验证和初始化所有配置项。
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

from cache import CacheManager
from analyzer import WebAnalyzer
from utils import WebAnalyzerUtils


class ConfigLoader:
    """配置加载器类"""

    @staticmethod
    def load_all_config(config: Any, context: Context) -> dict:
        """加载所有配置项

        Args:
            config: AstrBot配置对象
            context: AstrBot上下文对象

        Returns:
            包含所有配置项的字典
        """
        config_dict = {}

        # 网络设置
        config_dict.update(ConfigLoader._load_network_settings(config))

        # 域名设置
        config_dict.update(ConfigLoader._load_domain_settings(config))

        # 分析设置
        config_dict.update(ConfigLoader._load_analysis_settings(config))

        # 截图设置
        config_dict.update(ConfigLoader._load_screenshot_settings(config))

        # LLM设置
        config_dict.update(ConfigLoader._load_llm_settings(config))

        # 群组设置
        config_dict.update(ConfigLoader._load_group_settings(config))

        # 翻译设置
        config_dict.update(ConfigLoader._load_translation_settings(config))

        # 缓存设置
        config_dict.update(ConfigLoader._load_cache_settings(config))

        # 内容提取设置
        config_dict.update(ConfigLoader._load_content_extraction_settings(config))

        # 撤回设置
        config_dict.update(ConfigLoader._load_recall_settings(config))

        # 命令设置
        config_dict.update(ConfigLoader._load_command_settings(config))

        # 资源设置
        config_dict.update(ConfigLoader._load_resource_settings(config))

        # 模板设置
        config_dict.update(ConfigLoader._load_template_settings(config))

        return config_dict

    @staticmethod
    def _load_network_settings(config: Any) -> dict:
        """加载和验证网络设置"""
        network_settings = config.get("network_settings", {})
        config_dict = {}

        # 基本网络设置
        config_dict["max_content_length"] = max(
            1000, network_settings.get("max_content_length", 10000)
        )
        config_dict["timeout"] = max(
            5, min(300, network_settings.get("request_timeout", 30))
        )
        config_dict["retry_count"] = max(0, min(10, network_settings.get("retry_count", 3)))
        config_dict["retry_delay"] = max(0, min(10, network_settings.get("retry_delay", 2)))
        config_dict["user_agent"] = network_settings.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        config_dict["proxy"] = network_settings.get("proxy", "")

        # 验证代理格式
        config_dict["proxy"] = ConfigLoader._validate_proxy(config_dict["proxy"])

        # 并发设置
        config_dict["max_concurrency"] = max(
            1, min(20, network_settings.get("max_concurrency", 5))
        )
        config_dict["dynamic_concurrency"] = bool(
            network_settings.get("dynamic_concurrency", True)
        )

        # 优先级设置
        config_dict["enable_priority_scheduling"] = bool(
            network_settings.get("enable_priority_scheduling", False)
        )

        # URL处理设置
        config_dict["enable_unified_domain"] = bool(
            network_settings.get("enable_unified_domain", True)
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
    def _load_domain_settings(config: Any) -> dict:
        """加载和验证域名设置"""
        domain_settings = config.get("domain_settings", {})
        config_dict = {}

        config_dict["allowed_domains"] = ConfigLoader._parse_domain_list(
            domain_settings.get("allowed_domains", "")
        )
        config_dict["blocked_domains"] = ConfigLoader._parse_domain_list(
            domain_settings.get("blocked_domains", "")
        )

        return config_dict

    @staticmethod
    def _parse_domain_list(domain_text: str) -> list[str]:
        """将多行域名文本转换为Python列表"""
        return WebAnalyzerUtils.parse_domain_list(domain_text)

    @staticmethod
    def _load_analysis_settings(config: Any) -> dict:
        """加载和验证分析设置"""
        analysis_settings = config.get("analysis_settings", {})
        config_dict = {}

        # 分析模式设置
        valid_modes = ["auto", "manual", "hybrid", "LLMTOOL"]
        config_dict["analysis_mode"] = analysis_settings.get("analysis_mode", "auto")
        if config_dict["analysis_mode"] not in valid_modes:
            logger.warning(
                f"无效的分析模式: {config_dict['analysis_mode']}，将使用默认值 auto"
            )
            config_dict["analysis_mode"] = "auto"

        config_dict["auto_analyze"] = bool(analysis_settings.get("auto_analyze", True))
        if "analysis_mode" in analysis_settings:
            config_dict["auto_analyze"] = config_dict["analysis_mode"] == "auto"

        # 结果样式设置
        config_dict["enable_emoji"] = bool(analysis_settings.get("enable_emoji", True))
        config_dict["enable_statistics"] = bool(
            analysis_settings.get("enable_statistics", True)
        )
        config_dict["max_summary_length"] = max(
            500, min(10000, analysis_settings.get("max_summary_length", 2000))
        )

        # 发送内容类型设置
        valid_content_types = ["both", "analysis_only", "screenshot_only"]
        config_dict["send_content_type"] = analysis_settings.get(
            "send_content_type", "both"
        )
        if config_dict["send_content_type"] not in valid_content_types:
            logger.warning(
                f"无效的发送内容类型: {config_dict['send_content_type']}，将使用默认值 both"
            )
            config_dict["send_content_type"] = "both"

        # 结果模板设置
        valid_templates = ["default", "detailed", "compact", "markdown", "simple"]
        config_dict["result_template"] = analysis_settings.get("result_template", "default")
        if config_dict["result_template"] not in valid_templates:
            logger.warning(
                f"无效的结果模板: {config_dict['result_template']}，将使用默认值 default"
            )
            config_dict["result_template"] = "default"

        # 结果折叠设置
        config_dict["enable_collapsible"] = bool(
            analysis_settings.get("enable_collapsible", False)
        )
        config_dict["collapse_threshold"] = max(
            500, min(5000, analysis_settings.get("collapse_threshold", 1500))
        )

        # URL识别设置
        config_dict["enable_no_protocol_url"] = bool(
            analysis_settings.get("enable_no_protocol_url", False)
        )
        valid_protocols = ["http", "https"]
        config_dict["default_protocol"] = analysis_settings.get("default_protocol", "https")
        if config_dict["default_protocol"] not in valid_protocols:
            logger.warning(
                f"无效的默认协议: {config_dict['default_protocol']}，将使用默认值 https"
            )
            config_dict["default_protocol"] = "https"

        # LLM决策设置
        config_dict["enable_llm_decision"] = bool(
            analysis_settings.get("enable_llm_decision", False)
        )

        return config_dict

    @staticmethod
    def _load_screenshot_settings(config: Any) -> dict:
        """加载和验证截图设置"""
        screenshot_settings = config.get("screenshot_settings", {})
        config_dict = {}

        # 基本截图设置
        config_dict["enable_screenshot"] = bool(
            screenshot_settings.get("enable_screenshot", True)
        )
        config_dict["screenshot_quality"] = max(
            10, min(100, screenshot_settings.get("screenshot_quality", 80))
        )
        config_dict["screenshot_width"] = max(
            320, min(4096, screenshot_settings.get("screenshot_width", 1280))
        )
        config_dict["screenshot_height"] = max(
            240, min(4096, screenshot_settings.get("screenshot_height", 720))
        )
        config_dict["screenshot_full_page"] = bool(
            screenshot_settings.get("screenshot_full_page", False)
        )
        config_dict["screenshot_wait_time"] = max(
            0, min(10000, screenshot_settings.get("screenshot_wait_time", 2000))
        )

        # 截图格式设置
        valid_formats = ["jpeg", "png"]
        screenshot_format = screenshot_settings.get("screenshot_format", "jpeg").lower()
        config_dict["screenshot_format"] = (
            screenshot_format if screenshot_format in valid_formats else "jpeg"
        )
        if config_dict["screenshot_format"] != screenshot_format:
            logger.warning(f"无效的截图格式: {screenshot_format}，将使用默认格式 jpeg")

        # 裁剪设置
        config_dict["enable_crop"] = bool(screenshot_settings.get("enable_crop", False))
        default_crop_area = [
            0,
            0,
            config_dict["screenshot_width"],
            config_dict["screenshot_height"],
        ]
        crop_area = screenshot_settings.get("crop_area", default_crop_area)

        if isinstance(crop_area, str):
            crop_area = ConfigLoader._validate_crop_area(crop_area, default_crop_area)
        elif not (isinstance(crop_area, list) and len(crop_area) == 4):
            logger.warning(f"无效的裁剪区域: {crop_area}，将使用默认值")
            crop_area = default_crop_area

        config_dict["crop_area"] = crop_area

        return config_dict

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

    @staticmethod
    def _load_llm_settings(config: Any) -> dict:
        """加载和验证LLM设置"""
        llm_settings = config.get("llm_settings", {})
        config_dict = {}

        config_dict["llm_enabled"] = bool(llm_settings.get("llm_enabled", True))
        config_dict["llm_provider"] = llm_settings.get("llm_provider", "")
        config_dict["custom_prompt"] = llm_settings.get("custom_prompt", "")

        return config_dict

    @staticmethod
    def _load_group_settings(config: Any) -> dict:
        """加载和验证群聊设置"""
        group_settings = config.get("group_settings", {})
        config_dict = {}

        group_blacklist_text = group_settings.get("group_blacklist", "")
        config_dict["group_blacklist"] = ConfigLoader._parse_group_list(group_blacklist_text)

        merge_forward_config = config.get("merge_forward_settings", {})
        config_dict["merge_forward_enabled"] = {
            "group": bool(merge_forward_config.get("group", False)),
            "private": bool(merge_forward_config.get("private", False)),
            "include_screenshot": bool(merge_forward_config.get("include_screenshot", False)),
        }

        return config_dict

    @staticmethod
    def _parse_group_list(group_text: str) -> list[str]:
        """将多行群聊ID文本转换为Python列表"""
        return WebAnalyzerUtils.parse_group_list(group_text)

    @staticmethod
    def _load_translation_settings(config: Any) -> dict:
        """加载和验证翻译设置"""
        translation_settings = config.get("translation_settings", {})
        config_dict = {}

        config_dict["enable_translation"] = bool(
            translation_settings.get("enable_translation", False)
        )

        config_dict["target_language"] = translation_settings.get("target_language", "zh").lower()
        valid_languages = ["zh", "en", "ja", "ko", "fr", "de", "es", "ru", "ar", "pt"]
        if config_dict["target_language"] not in valid_languages:
            logger.warning(
                f"无效的目标语言: {config_dict['target_language']}，将使用默认语言 zh"
            )
            config_dict["target_language"] = "zh"

        config_dict["translation_provider"] = translation_settings.get(
            "translation_provider", "llm"
        )
        config_dict["custom_translation_prompt"] = translation_settings.get(
            "custom_translation_prompt", ""
        )

        return config_dict

    @staticmethod
    def _load_cache_settings(config: Any) -> dict:
        """加载和验证缓存设置"""
        cache_settings = config.get("cache_settings", {})
        config_dict = {}

        config_dict["enable_cache"] = bool(cache_settings.get("enable_cache", True))
        config_dict["cache_expire_time"] = max(
            5, min(10080, cache_settings.get("cache_expire_time", 1440))
        )
        config_dict["max_cache_size"] = max(
            10, min(1000, cache_settings.get("max_cache_size", 100))
        )
        config_dict["cache_preload_enabled"] = bool(
            cache_settings.get("cache_preload_enabled", False)
        )
        config_dict["cache_preload_count"] = max(
            0, min(100, cache_settings.get("cache_preload_count", 20))
        )

        return config_dict

    @staticmethod
    def _load_content_extraction_settings(config: Any) -> dict:
        """加载和验证内容提取设置"""
        content_extraction_settings = config.get("content_extraction_settings", {})
        config_dict = {}

        config_dict["enable_specific_extraction"] = bool(
            content_extraction_settings.get("enable_specific_extraction", False)
        )
        extract_types_text = content_extraction_settings.get("extract_types", "title\ncontent")
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
    def _load_recall_settings(config: Any) -> dict:
        """加载和验证撤回设置"""
        recall_settings = config.get("recall_settings", {})
        config_dict = {}

        config_dict["enable_recall"] = bool(recall_settings.get("enable_recall", True))
        config_dict["recall_type"] = recall_settings.get("recall_type", "smart")
        config_dict["recall_time"] = max(0, min(120, recall_settings.get("recall_time", 10)))
        config_dict["smart_recall_enabled"] = bool(
            recall_settings.get("smart_recall_enabled", True)
        )

        return config_dict

    @staticmethod
    def _load_command_settings(config: Any) -> dict:
        """加载和验证命令设置"""
        command_settings = config.get("command_settings", {})
        config_dict = {}

        custom_aliases = command_settings.get("custom_aliases", {})

        if isinstance(custom_aliases, str):
            try:
                parsed_aliases = {}
                lines = custom_aliases.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    command, aliases = line.split("=", 1)
                    command = command.strip()
                    alias_list = [
                        alias.strip() for alias in aliases.split(",") if alias.strip()
                    ]
                    if command and alias_list:
                        parsed_aliases[command] = alias_list
                config_dict["custom_command_aliases"] = parsed_aliases
            except Exception as e:
                logger.warning(f"解析自定义命令别名失败: {e}，将使用默认值")
                config_dict["custom_command_aliases"] = {}
        else:
            config_dict["custom_command_aliases"] = custom_aliases

        config_dict["enable_command_completion"] = bool(
            command_settings.get("enable_completion", True)
        )
        config_dict["enable_command_help"] = bool(command_settings.get("enable_help", True))
        config_dict["enable_param_hints"] = bool(command_settings.get("enable_param_hints", True))

        return config_dict

    @staticmethod
    def _load_resource_settings(config: Any) -> dict:
        """加载和验证资源管理设置"""
        resource_settings = config.get("resource_settings", {})
        config_dict = {}

        config_dict["enable_memory_monitor"] = bool(
            resource_settings.get("enable_memory_monitor", True)
        )
        config_dict["memory_threshold"] = max(
            0.0, min(100.0, resource_settings.get("memory_threshold", 80.0))
        )

        return config_dict

    @staticmethod
    def _load_template_settings(config: Any) -> dict:
        """加载和验证模板设置"""
        template_settings = config.get("template_settings", {})
        config_dict = {}

        config_dict["enable_custom_template"] = bool(
            template_settings.get("enable_custom_template", False)
        )
        config_dict["template_content"] = template_settings.get(
            "template_content",
            "# 网页分析结果\n\n## 基本信息\n- 标题: {title}\n- 链接: {url}\n- 内容类型: {content_type}\n- 分析时间: {date} {time}\n\n## 内容摘要\n{summary}\n\n## 详细分析\n{analysis_result}\n\n## 内容统计\n{stats}",
        )
        valid_formats = ["markdown", "plain", "html"]
        config_dict["template_format"] = template_settings.get("template_format", "markdown")
        if config_dict["template_format"] not in valid_formats:
            logger.warning(
                f"无效的模板格式: {config_dict['template_format']}，将使用默认格式 markdown"
            )
            config_dict["template_format"] = "markdown"

        return config_dict