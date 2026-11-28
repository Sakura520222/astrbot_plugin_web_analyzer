"""
配置加载与迁移模块

读取新版五组配置（触发与发送 / 截图 / 访问规则 / 缓存 / 浏览器与网络），
并在检测到旧版中文分组时一次性迁移到新键。

迁移说明：框架在插件代码运行前会按新 Schema 移除未知键，因此新 Schema
把旧版五个分组保留为隐藏的 dict 类型条目；插件首次运行时读取它们完成
迁移后删除，下一次加载即得到干净的配置。
"""

from typing import Any

from astrbot.api import logger

from .urls import parse_domain_list, parse_group_list

# 旧版五个顶层分组，迁移完成后从配置中移除
_LEGACY_GROUPS = ("基础设置", "分析设置", "展示设置", "智能分析", "消息管理")
_MIGRATION_MARKER = "_legacy_migrated"


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_int(value, default: int, min_val=None, max_val=None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if min_val is not None and result < min_val:
        return default
    if max_val is not None and result > max_val:
        return default
    return result


class ConfigLoader:
    """配置加载器。"""

    @staticmethod
    def load(config) -> dict:
        """读取并规范化全部配置；必要时执行一次旧版迁移。

        Args:
            config: AstrBotConfig 注入的配置字典。

        Returns:
            扁平化的配置字典（键为新配置的最终字段名）。
        """
        migrated = ConfigLoader.migrate_legacy(config)
        if migrated:
            try:
                config.save_config()
            except Exception as e:
                logger.warning(f"保存迁移后的配置失败: {e}")

        settings = {
            # 触发与发送
            "auto_capture": _as_bool(
                config.get("trigger", {}).get("auto_capture"), True
            ),
            "handoff_to_model": _as_bool(
                config.get("trigger", {}).get("handoff_to_model"), True
            ),
            "enable_no_protocol_url": _as_bool(
                config.get("trigger", {}).get("enable_no_protocol_url"), False
            ),
            "default_protocol": (
                "http"
                if config.get("trigger", {}).get("default_protocol") == "http"
                else "https"
            ),
            "group_blacklist": parse_group_list(
                config.get("trigger", {}).get("group_blacklist", "")
            ),
            "enable_processing_message": _as_bool(
                config.get("trigger", {}).get("enable_processing_message"), True
            ),
            "enable_recall": _as_bool(
                config.get("trigger", {}).get("enable_recall"), True
            ),
            "recall_type": (
                "time_based"
                if config.get("trigger", {}).get("recall_type") == "time_based"
                else "smart"
            ),
            "recall_time_s": _as_int(
                config.get("trigger", {}).get("recall_time_s"), 10, 0, 120
            ),
            "smart_recall_enabled": _as_bool(
                config.get("trigger", {}).get("smart_recall_enabled"), True
            ),
            # 截图
            "screenshot_width": _as_int(
                config.get("screenshot", {}).get("screenshot_width"), 1280, 320, 4096
            ),
            "screenshot_height": _as_int(
                config.get("screenshot", {}).get("screenshot_height"), 720, 240, 4096
            ),
            "screenshot_full_page": _as_bool(
                config.get("screenshot", {}).get("screenshot_full_page"), False
            ),
            "screenshot_format": (
                "png"
                if config.get("screenshot", {}).get("screenshot_format") == "png"
                else "jpeg"
            ),
            "screenshot_quality": _as_int(
                config.get("screenshot", {}).get("screenshot_quality"), 80, 10, 100
            ),
            "screenshot_wait_strategy": (
                config.get("screenshot", {}).get("screenshot_wait_strategy")
                if config.get("screenshot", {}).get("screenshot_wait_strategy")
                in ("fixed", "networkidle", "smart")
                else "fixed"
            ),
            "screenshot_wait_ms": _as_int(
                config.get("screenshot", {}).get("screenshot_wait_ms"), 2000, 0, 10000
            ),
            "screenshot_retry_count": _as_int(
                config.get("screenshot", {}).get("screenshot_retry_count"), 1, 0, 3
            ),
            "enable_crop": _as_bool(
                config.get("screenshot", {}).get("enable_crop"), False
            ),
            "crop_area": ConfigLoader._validate_crop_area(
                config.get("screenshot", {}).get("crop_area", "[0, 0, 1280, 720]")
            ),
            # 访问规则
            "allowed_domains": parse_domain_list(
                config.get("access", {}).get("allowed_domains", "")
            ),
            "blocked_domains": parse_domain_list(
                config.get("access", {}).get("blocked_domains", "")
            ),
            "enable_unified_domain": _as_bool(
                config.get("access", {}).get("enable_unified_domain"), False
            ),
            "allow_local_addresses": _as_bool(
                config.get("access", {}).get("allow_local_addresses"), False
            ),
            # 缓存
            "enable_cache": _as_bool(config.get("cache", {}).get("enable_cache"), True),
            "cache_expire_time_min": _as_int(
                config.get("cache", {}).get("cache_expire_time_min"), 1440, 5, 10080
            ),
            "max_cache_size": _as_int(
                config.get("cache", {}).get("max_cache_size"), 100, 10, 1000
            ),
            # 浏览器与网络
            "fetch_mode": (
                "browser"
                if config.get("runtime", {}).get("fetch_mode") == "browser"
                else "httpx"
            ),
            "max_content_length": _as_int(
                config.get("runtime", {}).get("max_content_length"),
                10000,
                1000,
                1000000,
            ),
            "request_timeout_s": _as_int(
                config.get("runtime", {}).get("request_timeout_s"), 30, 5, 300
            ),
            "retry_count": _as_int(
                config.get("runtime", {}).get("retry_count"), 3, 0, 10
            ),
            "retry_delay_s": _as_int(
                config.get("runtime", {}).get("retry_delay_s"), 2, 0, 10
            ),
            "max_concurrency": _as_int(
                config.get("runtime", {}).get("max_concurrency"), 5, 1, 20
            ),
            "user_agent": str(config.get("runtime", {}).get("user_agent", "") or ""),
            "proxy": ConfigLoader._validate_proxy(
                config.get("runtime", {}).get("proxy", "")
            ),
            "hide_ip": _as_bool(config.get("runtime", {}).get("hide_ip"), False),
            "sandbox_mode": (
                config.get("runtime", {}).get("sandbox_mode")
                if config.get("runtime", {}).get("sandbox_mode")
                in ("auto", "always_disabled", "always_enabled")
                else "auto"
            ),
            "max_browser_instances": _as_int(
                config.get("runtime", {}).get("max_browser_instances"), 3, 1, 10
            ),
            "enable_memory_monitor": _as_bool(
                config.get("runtime", {}).get("enable_memory_monitor"), False
            ),
            "memory_threshold_percent": float(
                config.get("runtime", {}).get("memory_threshold_percent", 80.0)
            ),
        }
        return settings

    # ==================== 旧版迁移 ====================

    @staticmethod
    def migrate_legacy(config) -> bool:
        """把旧版中文分组迁移到新键；无旧配置或已迁移时返回 False。"""
        if config.get(_MIGRATION_MARKER):
            return False
        legacy = {
            name: config.get(name)
            for name in _LEGACY_GROUPS
            if isinstance(config.get(name), dict) and config.get(name)
        }
        if not legacy:
            return False

        logger.info("检测到旧版配置，正在迁移为网页截图插件的新配置...")

        base = (
            legacy.get("基础设置", {})
            if isinstance(legacy.get("基础设置"), dict)
            else {}
        )
        network = (
            base.get("网络设置", {}) if isinstance(base.get("网络设置"), dict) else {}
        )
        browser = (
            base.get("浏览器设置", {})
            if isinstance(base.get("浏览器设置"), dict)
            else {}
        )
        domains = (
            base.get("域名管理", {}) if isinstance(base.get("域名管理"), dict) else {}
        )
        cache_old = (
            base.get("缓存设置", {}) if isinstance(base.get("缓存设置"), dict) else {}
        )
        resource = (
            base.get("资源管理", {}) if isinstance(base.get("资源管理"), dict) else {}
        )

        display = (
            legacy.get("展示设置", {})
            if isinstance(legacy.get("展示设置"), dict)
            else {}
        )
        url_recognition = (
            display.get("URL识别", {})
            if isinstance(display.get("URL识别"), dict)
            else {}
        )
        screenshot_old = (
            display.get("网页截图", {})
            if isinstance(display.get("网页截图"), dict)
            else {}
        )
        size_old = (
            screenshot_old.get("截图尺寸", {})
            if isinstance(screenshot_old.get("截图尺寸"), dict)
            else {}
        )
        crop_old = (
            screenshot_old.get("裁剪设置", {})
            if isinstance(screenshot_old.get("裁剪设置"), dict)
            else {}
        )

        messages = (
            legacy.get("消息管理", {})
            if isinstance(legacy.get("消息管理"), dict)
            else {}
        )
        groups_old = (
            messages.get("群聊设置", {})
            if isinstance(messages.get("群聊设置"), dict)
            else {}
        )
        propagation = (
            messages.get("事件传播", {})
            if isinstance(messages.get("事件传播"), dict)
            else {}
        )
        recall_old = (
            messages.get("消息撤回", {})
            if isinstance(messages.get("消息撤回"), dict)
            else {}
        )

        analysis = (
            legacy.get("分析设置", {})
            if isinstance(legacy.get("分析设置"), dict)
            else {}
        )

        # 迁移策略：旧配置为手动、仅分析或关闭截图时，迁移后使用手动截图
        analysis_mode = analysis.get("analysis_mode", "auto")
        send_content_type = display.get("send_content_type", "both")
        screenshot_enabled = _as_bool(screenshot_old.get("enable_screenshot"), True)
        manual_only = (
            analysis_mode == "manual"
            or send_content_type == "analysis_only"
            or not screenshot_enabled
        )

        def set_new(group: str, key: str, value):
            node = config.get(group)
            if isinstance(node, dict):
                node[key] = value

        # 触发与发送
        set_new("trigger", "auto_capture", not manual_only)
        set_new(
            "trigger",
            "handoff_to_model",
            _as_bool(propagation.get("allow_llm_propagation"), True),
        )
        set_new(
            "trigger",
            "enable_no_protocol_url",
            _as_bool(url_recognition.get("enable_no_protocol_url"), False),
        )
        set_new(
            "trigger",
            "default_protocol",
            url_recognition.get("default_protocol", "https"),
        )
        set_new("trigger", "group_blacklist", groups_old.get("group_blacklist", ""))
        set_new(
            "trigger",
            "enable_processing_message",
            _as_bool(recall_old.get("enable_processing_message"), True),
        )
        set_new(
            "trigger", "enable_recall", _as_bool(recall_old.get("enable_recall"), True)
        )
        set_new("trigger", "recall_type", recall_old.get("recall_type", "smart"))
        set_new(
            "trigger",
            "recall_time_s",
            _as_int(
                recall_old.get("recall_time_s", recall_old.get("recall_time", 10)),
                10,
                0,
                120,
            ),
        )
        set_new(
            "trigger",
            "smart_recall_enabled",
            _as_bool(recall_old.get("smart_recall_enabled"), True),
        )

        # 截图
        set_new(
            "screenshot",
            "screenshot_width",
            _as_int(size_old.get("screenshot_width", 1280), 1280, 320, 4096),
        )
        set_new(
            "screenshot",
            "screenshot_height",
            _as_int(size_old.get("screenshot_height", 720), 720, 240, 4096),
        )
        set_new(
            "screenshot",
            "screenshot_full_page",
            _as_bool(screenshot_old.get("screenshot_full_page"), False),
        )
        set_new(
            "screenshot",
            "screenshot_format",
            screenshot_old.get("screenshot_format", "jpeg"),
        )
        set_new(
            "screenshot",
            "screenshot_quality",
            _as_int(screenshot_old.get("screenshot_quality", 80), 80, 10, 100),
        )
        set_new(
            "screenshot",
            "screenshot_wait_strategy",
            screenshot_old.get("screenshot_wait_strategy", "fixed"),
        )
        set_new(
            "screenshot",
            "screenshot_wait_ms",
            _as_int(
                screenshot_old.get(
                    "screenshot_wait_ms",
                    screenshot_old.get("screenshot_wait_time", 2000),
                ),
                2000,
                0,
                10000,
            ),
        )
        set_new(
            "screenshot",
            "screenshot_retry_count",
            _as_int(screenshot_old.get("screenshot_retry_count", 1), 1, 0, 3),
        )
        set_new(
            "screenshot",
            "enable_crop",
            _as_bool(
                crop_old.get("enable_crop", screenshot_old.get("enable_crop")), False
            ),
        )
        set_new(
            "screenshot",
            "crop_area",
            crop_old.get(
                "crop_area", screenshot_old.get("crop_area", "[0, 0, 1280, 720]")
            ),
        )

        # 访问规则
        set_new(
            "access",
            "allowed_domains",
            domains.get("allowed_domains", ""),
        )
        set_new(
            "access",
            "blocked_domains",
            domains.get("blocked_domains", ""),
        )
        set_new(
            "access",
            "enable_unified_domain",
            _as_bool(domains.get("enable_unified_domain"), False),
        )

        # 缓存
        set_new("cache", "enable_cache", _as_bool(cache_old.get("enable_cache"), True))
        set_new(
            "cache",
            "cache_expire_time_min",
            _as_int(
                cache_old.get(
                    "cache_expire_time_min", cache_old.get("cache_expire_time", 1440)
                ),
                1440,
                5,
                10080,
            ),
        )
        set_new(
            "cache",
            "max_cache_size",
            _as_int(cache_old.get("max_cache_size", 100), 100, 10, 1000),
        )

        # 浏览器与网络
        fetch_mode = network.get("fetch_mode", "httpx")
        set_new(
            "runtime",
            "fetch_mode",
            "browser" if fetch_mode == "playwright" else fetch_mode,
        )
        set_new(
            "runtime",
            "max_content_length",
            _as_int(network.get("max_content_length", 10000), 10000, 1000, 1000000),
        )
        set_new(
            "runtime",
            "request_timeout_s",
            _as_int(
                network.get("request_timeout_s", network.get("request_timeout", 30)),
                30,
                5,
                300,
            ),
        )
        set_new(
            "runtime", "retry_count", _as_int(network.get("retry_count", 3), 3, 0, 10)
        )
        set_new(
            "runtime",
            "retry_delay_s",
            _as_int(
                network.get("retry_delay_s", network.get("retry_delay", 2)), 2, 0, 10
            ),
        )
        set_new(
            "runtime",
            "max_concurrency",
            _as_int(network.get("max_concurrency", 5), 5, 1, 20),
        )
        set_new("runtime", "user_agent", network.get("user_agent", ""))
        set_new("runtime", "proxy", network.get("proxy", ""))
        set_new("runtime", "hide_ip", _as_bool(network.get("hide_ip"), False))
        set_new("runtime", "sandbox_mode", browser.get("sandbox_mode", "auto"))
        set_new(
            "runtime",
            "max_browser_instances",
            _as_int(browser.get("max_browser_instances", 3), 3, 1, 10),
        )
        set_new(
            "runtime",
            "enable_memory_monitor",
            _as_bool(resource.get("enable_memory_monitor"), False),
        )
        set_new(
            "runtime",
            "memory_threshold_percent",
            float(
                resource.get(
                    "memory_threshold_percent", resource.get("memory_threshold", 80.0)
                )
            ),
        )

        # 标记迁移完成并移除旧分组
        try:
            config[_MIGRATION_MARKER] = True
        except Exception:
            pass
        for name in _LEGACY_GROUPS:
            config.pop(name, None)

        logger.info(
            "旧版配置迁移完成"
            + ("；旧配置为手动/仅分析模式，已切换为手动截图" if manual_only else "")
        )
        return True

    # ==================== 校验 ====================

    @staticmethod
    def _validate_proxy(proxy: str) -> str:
        """校验代理格式；无效时忽略并告警（脱敏日志）。"""
        from urllib.parse import urlparse

        if not proxy:
            return ""
        try:
            parsed = urlparse(proxy)
            if not all([parsed.scheme, parsed.netloc]):
                logger.warning(
                    f"无效的代理格式: {ConfigLoader._mask_proxy(proxy)}，将忽略代理设置"
                )
                return ""
        except Exception:
            logger.warning(
                f"解析代理失败: {ConfigLoader._mask_proxy(proxy)}，将忽略代理设置"
            )
            return ""
        return proxy

    @staticmethod
    def _mask_proxy(proxy: str) -> str:
        """脱敏代理 URL，隐藏认证信息。"""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(proxy)
            if parsed.username:
                netloc = f"{parsed.username}:****@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return parsed._replace(netloc=netloc).geturl()
            return proxy
        except Exception:
            return "***"

    @staticmethod
    def _validate_crop_area(crop_value: Any) -> tuple[int, int, int, int]:
        """解析裁剪区域，支持字符串 "[l, t, r, b]" 或列表；非法时用默认值。"""
        import ast

        default = (0, 0, 1280, 720)
        if isinstance(crop_value, (list, tuple)) and len(crop_value) == 4:
            try:
                return tuple(int(v) for v in crop_value)
            except (TypeError, ValueError):
                return default
        if isinstance(crop_value, str) and crop_value.strip():
            try:
                value = ast.literal_eval(crop_value)
                if isinstance(value, (list, tuple)) and len(value) == 4:
                    return tuple(int(v) for v in value)
            except (ValueError, SyntaxError):
                pass
            logger.warning(f"裁剪区域格式无效: {crop_value}，将使用默认值")
        return default
