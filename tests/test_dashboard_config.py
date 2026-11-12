"""Exercise dashboard configuration transactions without loading a live bot."""

import ast
import asyncio
import copy
import hashlib
import json
import math
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlparse

from test_config_http import ConfigLoader

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))


def defaults(items):
    return {
        key: defaults(value["items"])
        if value["type"] == "object"
        else copy.deepcopy(value.get("default", ""))
        for key, value in items.items()
    }


def load_dashboard_class():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    start = next(
        index
        for index, node in enumerate(plugin.body)
        if isinstance(node, ast.FunctionDef) and node.name == "_register_dashboard_api"
    )
    body = []
    for node in plugin.body[start:]:
        if getattr(node, "name", "") == "terminate":
            break
        body.append(node)
    module = ast.Module(
        body=[
            ast.ClassDef(
                name="Dashboard", bases=[], keywords=[], body=body, decorator_list=[]
            )
        ],
        type_ignores=[],
    )
    namespace = {
        "asyncio": asyncio,
        "copy": copy,
        "json": json,
        "math": math,
        "Path": Path,
        "urlparse": urlparse,
        "ConfigLoader": ConfigLoader,
        "Context": object,
        "logger": Mock(),
        "__file__": str(ROOT / "main.py"),
    }
    exec(
        compile(ast.fix_missing_locations(module), str(ROOT / "main.py"), "exec"),
        namespace,
    )
    return namespace["Dashboard"]


Dashboard = load_dashboard_class()


class Config(dict):
    def __init__(self, value):
        super().__init__(value)
        self.saved = copy.deepcopy(value)
        self.fail_save = False

    def save_config(self):
        if self.fail_save:
            raise OSError("write failed")
        self.saved = copy.deepcopy(dict(self))


class DashboardConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = Dashboard()
        self.plugin.config = Config(defaults(SCHEMA))
        self.plugin._cached_schema = copy.deepcopy(SCHEMA)
        self.plugin._config_update_lock = asyncio.Lock()
        self.plugin.context = object()
        self.plugin.analyzer = types.SimpleNamespace(apply_runtime_config=AsyncMock())
        self.plugin.message_handler = types.SimpleNamespace(apply_runtime_config=Mock())
        self.plugin.cache_manager = types.SimpleNamespace(apply_runtime_config=Mock())
        self.plugin.llm_analyzer = types.SimpleNamespace()
        self.plugin.result_formatter = types.SimpleNamespace()

    async def test_every_schema_field_can_be_saved_and_is_forwarded_to_live_components(
        self,
    ):
        fields = self.plugin._load_schema_field_map()
        updates = {
            path: copy.deepcopy(spec.get("default", ""))
            for path, spec in fields.items()
        }
        self.assertEqual(len(updates), 66)
        payload, status = await self.plugin._update_dashboard_config(updates)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["applied"], len(fields))
        self.assertEqual(set(payload["applied_paths"]), set(fields))
        normalized = ConfigLoader.load_all_config(
            self.plugin.config, self.plugin.context
        )
        self.plugin.analyzer.apply_runtime_config.assert_awaited_once_with(normalized)
        self.plugin.message_handler.apply_runtime_config.assert_called_once_with(
            normalized
        )
        self.plugin.cache_manager.apply_runtime_config.assert_called_once_with(
            normalized
        )
        self.assertEqual(
            self.plugin.llm_analyzer.llm_provider, normalized["llm_provider"]
        )
        self.assertEqual(
            self.plugin.result_formatter.enable_emoji, normalized["enable_emoji"]
        )
        for name, value in normalized.items():
            self.assertEqual(getattr(self.plugin, name), value, name)

    async def test_changes_apply_to_model_screenshot_and_message_flags(self):
        updates = {
            "分析设置.analysis_mode": "manual",
            "智能分析.llm_provider": "configured-provider",
            "智能分析.custom_prompt": "Read {title}",
            "展示设置.网页截图.screenshot_format": "png",
            "展示设置.网页截图.裁剪设置.enable_crop": True,
            "展示设置.网页截图.裁剪设置.crop_area": "[10, 20, 600, 400]",
            "消息管理.合并转发.group": True,
            "消息管理.合并转发.private": False,
            "基础设置.缓存设置.cache_expire_time_min": 60,
        }
        payload, status = await self.plugin._update_dashboard_config(updates)
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.plugin.analysis_mode, "manual")
        self.assertFalse(self.plugin.auto_analyze)
        self.assertEqual(self.plugin.llm_analyzer.llm_provider, "configured-provider")
        settings = self.plugin.message_handler.apply_runtime_config.call_args.args[0]
        self.assertTrue(settings["merge_forward_group"])
        self.assertFalse(settings["merge_forward_private"])
        self.assertEqual(settings["screenshot_format"], "png")
        self.assertTrue(settings["enable_crop"])
        self.assertEqual(settings["crop_area"], [10, 20, 600, 400])
        self.assertEqual(self.plugin.config.saved, self.plugin.config)

    async def test_each_analysis_mode_enables_its_appropriate_event_path(self):
        for mode in ("auto", "manual", "hybrid", "LLMTOOL"):
            payload, status = await self.plugin._update_dashboard_config(
                {"分析设置.analysis_mode": mode}
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(self.plugin.auto_analyze, mode != "manual")

    async def test_legacy_config_is_migrated_before_applying_a_partial_update(self):
        self.plugin.config = Config(
            {
                "network_settings": {"request_timeout": 9},
                "analysis_settings": {"analysis_mode": "manual"},
                "llm_settings": {"llm_provider": "legacy-provider"},
            }
        )
        field = self.plugin._build_config_field(
            "analysis_mode",
            SCHEMA["分析设置"]["items"]["analysis_mode"],
            ["分析设置"],
        )
        self.assertEqual(field["value"], "manual")
        payload, status = await self.plugin._update_dashboard_config(
            {"分析设置.enable_statistics": False}
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.plugin.request_timeout_s, 9)
        self.assertEqual(self.plugin.analysis_mode, "manual")
        self.assertEqual(self.plugin.llm_provider, "legacy-provider")
        self.assertFalse(self.plugin.enable_statistics)

    async def test_invalid_batch_has_no_partial_effect(self):
        cases = [
            {"not.real.proxy": "value"},
            {"分析设置.analysis_mode": "bogus"},
            {"分析设置.max_summary_length": True},
            {"分析设置.max_summary_length": 1},
            {"基础设置.资源管理.memory_threshold_percent": float("nan")},
            {"基础设置.网络设置.proxy": "not-a-proxy"},
            {"基础设置.网络设置.proxy": "http://localhost:999999"},
            {"展示设置.网页截图.裁剪设置.crop_area": "[10, 0, 1, 20]"},
            {"消息管理.事件传播.allow_llm_propagation": "false"},
        ]
        original = copy.deepcopy(dict(self.plugin.config))
        for update in cases:
            with self.subTest(update=update):
                update["分析设置.enable_statistics"] = False
                payload, status = await self.plugin._update_dashboard_config(update)
                self.assertEqual(status, 400, payload)
                self.assertEqual(self.plugin.config, original)
        self.plugin.analyzer.apply_runtime_config.assert_not_awaited()

    async def test_save_failure_does_not_change_runtime_or_memory(self):
        original = copy.deepcopy(dict(self.plugin.config))
        self.plugin.config.fail_save = True
        payload, status = await self.plugin._update_dashboard_config(
            {"分析设置.enable_emoji": False}
        )
        self.assertEqual(status, 500, payload)
        self.assertEqual(self.plugin.config, original)
        self.plugin.analyzer.apply_runtime_config.assert_not_awaited()

    async def test_apply_failure_restores_saved_and_live_settings(self):
        original = copy.deepcopy(dict(self.plugin.config))
        self.plugin.analyzer.apply_runtime_config.side_effect = [
            RuntimeError("apply failed"),
            None,
        ]
        payload, status = await self.plugin._update_dashboard_config(
            {"分析设置.enable_emoji": False}
        )
        self.assertEqual(status, 500, payload)
        self.assertEqual(self.plugin.config, original)
        self.assertEqual(self.plugin.config.saved, original)
        self.assertTrue(self.plugin.enable_emoji)
        self.assertEqual(self.plugin.analyzer.apply_runtime_config.await_count, 2)

    async def test_proxy_is_editable_and_clearable_without_credential_echo(self):
        path = "基础设置.网络设置.proxy"
        secret = "http://test-user:test-password@localhost:8080"
        payload, status = await self.plugin._update_dashboard_config({path: secret})
        self.assertEqual(status, 200, payload)
        self.assertNotIn("test-password", json.dumps(payload))
        self.assertEqual(self.plugin.proxy, secret)
        field = self.plugin._build_config_field(
            "proxy", self.plugin._load_schema_field_map()[path], path.split(".")[:-1]
        )
        self.assertEqual(field["value"], "")
        self.assertTrue(field["has_value"])
        self.assertTrue(field["secret"])
        payload, status = await self.plugin._update_dashboard_config({path: ""})
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.plugin.proxy, "")
        self.assertFalse(payload["secret_fields"][path])

    def test_field_getters_use_nested_values_and_option_labels(self):
        self.plugin.config["消息管理"]["合并转发"]["group"] = True
        self.plugin.config["消息管理"]["合并转发"]["private"] = False
        for name, expected in (("group", True), ("private", False)):
            spec = SCHEMA["消息管理"]["items"]["合并转发"]["items"][name]
            self.assertEqual(
                self.plugin._build_config_field(name, spec, ["消息管理", "合并转发"])[
                    "value"
                ],
                expected,
            )
        spec = SCHEMA["分析设置"]["items"]["analysis_mode"]
        field = self.plugin._build_config_field("analysis_mode", spec, ["分析设置"])
        self.assertEqual(len(field["labels"]), len(field["options"]))
        self.assertEqual(field["value"], "auto")

    def test_schema_paths_and_semantics_match_compatibility_snapshot(self):
        fields = {}
        self.plugin._collect_schema_ranges(SCHEMA, fields)
        semantics = {
            path: {
                key: spec[key]
                for key in ("type", "default", "options", "minimum", "maximum")
                if key in spec
            }
            for path, spec in fields.items()
        }
        encoded = json.dumps(semantics, sort_keys=True, ensure_ascii=False).encode()
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            "5181869d829e6ca94c781a900e940aa70184e0083e1bfa6801071c89d9f90509",
        )


if __name__ == "__main__":
    unittest.main()
