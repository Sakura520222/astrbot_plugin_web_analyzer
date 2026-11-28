"""Legacy config migration tests."""

import unittest

from test_support import ConfigLoader

LEGACY_FULL = {
    "trigger": {},
    "screenshot": {},
    "access": {},
    "cache": {},
    "runtime": {},
    "基础设置": {
        "网络设置": {
            "proxy": "http://user:pass@1.2.3.4:8080",
            "user_agent": "UA-old",
            "fetch_mode": "playwright",
            "max_content_length": 20000,
            "request_timeout_s": 45,
            "max_concurrency": 3,
            "retry_count": 1,
            "retry_delay_s": 3,
            "hide_ip": True,
        },
        "域名管理": {
            "allowed_domains": "example.com",
            "blocked_domains": "ads.com",
            "enable_unified_domain": True,
        },
        "缓存设置": {
            "enable_cache": False,
            "cache_expire_time_min": 2880,
            "max_cache_size": 50,
        },
        "浏览器设置": {
            "sandbox_mode": "always_disabled",
            "max_browser_instances": 2,
        },
        "资源管理": {
            "enable_memory_monitor": True,
            "memory_threshold_percent": 90.0,
        },
    },
    "分析设置": {"analysis_mode": "auto"},
    "展示设置": {
        "send_content_type": "both",
        "URL识别": {"enable_no_protocol_url": True, "default_protocol": "http"},
        "网页截图": {
            "enable_screenshot": True,
            "screenshot_quality": 90,
            "截图尺寸": {"screenshot_width": 1920, "screenshot_height": 1080},
            "screenshot_full_page": True,
            "screenshot_wait_ms": 3000,
            "screenshot_wait_strategy": "smart",
            "screenshot_retry_count": 2,
            "screenshot_format": "png",
            "裁剪设置": {"enable_crop": True, "crop_area": "[0,0,800,600]"},
        },
    },
    "智能分析": {"llm_enabled": True},
    "消息管理": {
        "群聊设置": {"group_blacklist": "123\n456"},
        "事件传播": {"allow_llm_propagation": False},
        "消息撤回": {
            "enable_processing_message": False,
            "recall_type": "time_based",
            "recall_time_s": 20,
            "smart_recall_enabled": False,
        },
    },
}


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = 0

    def save_config(self):
        self.saved += 1


class LegacyMigrationTests(unittest.TestCase):
    def test_full_legacy_config_maps_every_group(self):
        config = FakeConfig(LEGACY_FULL)
        self.assertTrue(ConfigLoader.migrate_legacy(config))
        self.assertEqual(config.saved, 0)  # load() 负责 save，迁移本身不落盘
        settings = ConfigLoader.load(config)
        checks = {
            "auto_capture stays auto": settings["auto_capture"] is True,
            "handoff False": settings["handoff_to_model"] is False,
            "proxy": settings["proxy"] == "http://user:pass@1.2.3.4:8080",
            "user_agent": settings["user_agent"] == "UA-old",
            "fetch_mode playwright->browser": settings["fetch_mode"] == "browser",
            "max_content_length": settings["max_content_length"] == 20000,
            "request_timeout_s": settings["request_timeout_s"] == 45,
            "max_concurrency": settings["max_concurrency"] == 3,
            "retry": settings["retry_count"] == 1,
            "retry_delay": settings["retry_delay_s"] == 3,
            "hide_ip": settings["hide_ip"] is True,
            "allowed_domains": settings["allowed_domains"] == ["example.com"],
            "blocked_domains": settings["blocked_domains"] == ["ads.com"],
            "unified_domain": settings["enable_unified_domain"] is True,
            "cache disabled": settings["enable_cache"] is False,
            "cache expire": settings["cache_expire_time_min"] == 2880,
            "cache max": settings["max_cache_size"] == 50,
            "sandbox": settings["sandbox_mode"] == "always_disabled",
            "max_instances": settings["max_browser_instances"] == 2,
            "memory_monitor": settings["enable_memory_monitor"] is True,
            "memory_threshold": settings["memory_threshold_percent"] == 90.0,
            "viewport width": settings["screenshot_width"] == 1920,
            "viewport height": settings["screenshot_height"] == 1080,
            "full_page": settings["screenshot_full_page"] is True,
            "format png": settings["screenshot_format"] == "png",
            "quality": settings["screenshot_quality"] == 90,
            "wait_strategy": settings["screenshot_wait_strategy"] == "smart",
            "wait_ms": settings["screenshot_wait_ms"] == 3000,
            "retry_count": settings["screenshot_retry_count"] == 2,
            "crop": settings["enable_crop"] is True,
            "crop_area": settings["crop_area"] == (0, 0, 800, 600),
            "no_protocol": settings["enable_no_protocol_url"] is True,
            "default_protocol": settings["default_protocol"] == "http",
            "group_blacklist": settings["group_blacklist"] == ["123", "456"],
            "processing_message": settings["enable_processing_message"] is False,
            "recall_type": settings["recall_type"] == "time_based",
            "recall_time": settings["recall_time_s"] == 20,
            "smart_recall": settings["smart_recall_enabled"] is False,
            "allow_local_default_false": settings["allow_local_addresses"] is False,
            "legacy groups removed": all(
                name not in config
                for name in ("基础设置", "分析设置", "展示设置", "智能分析", "消息管理")
            ),
            "marker set": config.get("_legacy_migrated") is True,
        }
        failed = [name for name, ok in checks.items() if not ok]
        self.assertEqual(failed, [])

    def test_manual_analysis_migrates_to_manual_capture(self):
        config = FakeConfig({**LEGACY_FULL, "分析设置": {"analysis_mode": "manual"}})
        ConfigLoader.migrate_legacy(config)
        self.assertFalse(config["trigger"]["auto_capture"])

    def test_analysis_only_migrates_to_manual_capture(self):
        legacy = {**LEGACY_FULL}
        legacy["展示设置"] = {
            **LEGACY_FULL["展示设置"],
            "send_content_type": "analysis_only",
        }
        config = FakeConfig(legacy)
        ConfigLoader.migrate_legacy(config)
        self.assertFalse(config["trigger"]["auto_capture"])

    def test_screenshot_disabled_migrates_to_manual_capture(self):
        legacy = {**LEGACY_FULL}
        legacy["展示设置"] = {
            **LEGACY_FULL["展示设置"],
            "网页截图": {
                **LEGACY_FULL["展示设置"]["网页截图"],
                "enable_screenshot": False,
            },
        }
        config = FakeConfig(legacy)
        ConfigLoader.migrate_legacy(config)
        self.assertFalse(config["trigger"]["auto_capture"])

    def test_active_screenshot_config_stays_automatic(self):
        legacy = {
            **LEGACY_FULL,
            "消息管理": {
                **LEGACY_FULL["消息管理"],
                "事件传播": {"allow_llm_propagation": True},
            },
        }
        config = FakeConfig(legacy)
        ConfigLoader.migrate_legacy(config)
        self.assertTrue(config["trigger"]["auto_capture"])
        self.assertTrue(config["trigger"]["handoff_to_model"])

    def test_migration_runs_only_once(self):
        config = FakeConfig(LEGACY_FULL)
        self.assertTrue(ConfigLoader.migrate_legacy(config))
        self.assertFalse(ConfigLoader.migrate_legacy(config))

    def test_fresh_config_is_not_migrated(self):
        config = FakeConfig({"trigger": {"auto_capture": True}})
        self.assertFalse(ConfigLoader.migrate_legacy(config))
        self.assertEqual(config.saved, 0)

    def test_load_saves_after_migration(self):
        config = FakeConfig(LEGACY_FULL)
        settings = ConfigLoader.load(config)
        self.assertEqual(config.saved, 1)
        self.assertIsInstance(settings, dict)


class CropAreaValidationTests(unittest.TestCase):
    def test_string_area_is_parsed(self):
        self.assertEqual(ConfigLoader._validate_crop_area("[1, 2, 3, 4]"), (1, 2, 3, 4))

    def test_list_area_is_accepted(self):
        self.assertEqual(ConfigLoader._validate_crop_area([5, 6, 7, 8]), (5, 6, 7, 8))

    def test_invalid_area_falls_back_to_default(self):
        self.assertEqual(
            ConfigLoader._validate_crop_area("not-a-list"), (0, 0, 1280, 720)
        )


class ProxyValidationTests(unittest.TestCase):
    def test_valid_proxy_is_kept(self):
        self.assertEqual(
            ConfigLoader._validate_proxy("http://127.0.0.1:7890"),
            "http://127.0.0.1:7890",
        )

    def test_invalid_proxy_is_dropped(self):
        self.assertEqual(ConfigLoader._validate_proxy("not-a-proxy"), "")


if __name__ == "__main__":
    unittest.main()
