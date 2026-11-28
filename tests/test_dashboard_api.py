"""Dashboard Web API tests for the read-only management panel."""

import base64
import json
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_support  # noqa: F401  (stubs astrbot.api before main imports)
from test_support import (
    ScreenshotCache,
    ScreenshotService,
    capture_pipeline_module,
    config_loader_module,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load_main_module():
    import importlib.util
    import sys
    import types

    main_name = "web_analyzer_test_package.main"
    if main_name in sys.modules:
        return sys.modules[main_name]

    event_module = sys.modules["astrbot.api.event"]

    class _Filter:
        EventMessageType = SimpleNamespace(ALL="all")
        PermissionType = SimpleNamespace(ADMIN="admin")

        @staticmethod
        def _passthrough(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        command = _passthrough
        llm_tool = _passthrough
        event_message_type = _passthrough
        permission_type = _passthrough

    _filter = _Filter()
    event_module.filter = _filter
    sys.modules["astrbot.api.event"].filter = _filter

    star_module = sys.modules["astrbot.api.star"]

    class _Star:
        def __init__(self, context):
            self.context = context

    star_module.Star = _Star
    star_module.register = lambda *args, **kwargs: lambda cls: cls

    components = types.ModuleType("astrbot.api.message_components")

    class _Image:
        def __init__(self, file):
            self.file = file

        @staticmethod
        def fromBytes(data):
            return _Image("base64://" + base64.b64encode(data).decode())

    components.Image = _Image
    sys.modules["astrbot.api.message_components"] = components

    spec = importlib.util.spec_from_file_location(main_name, PLUGIN_ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[main_name] = module
    spec.loader.exec_module(module)
    return module


main_module = _load_main_module()
WebScreenshotPlugin = main_module.WebScreenshotPlugin
PLUGIN_NAME = main_module.PLUGIN_NAME

DEFAULT_SETTINGS = config_loader_module.ConfigLoader.load(
    {
        "trigger": {},
        "screenshot": {},
        "access": {},
        "cache": {},
        "runtime": {},
    }
)


def make_plugin(settings_overrides=None):
    settings = {**DEFAULT_SETTINGS, **(settings_overrides or {})}
    cache_dir = tempfile.mkdtemp(prefix="wa_dashboard_test_")
    cache = ScreenshotCache(cache_dir=cache_dir)
    service = ScreenshotService.__new__(ScreenshotService)
    service.timeout = 30
    service.screenshot_retry_count = 1
    plugin = WebScreenshotPlugin.__new__(WebScreenshotPlugin)
    plugin._settings = settings
    plugin.cache = cache
    plugin.screenshot_service = service
    plugin.pipeline = capture_pipeline_module.CapturePipeline(service, cache, 3)
    return plugin


class FakeContext:
    def __init__(self):
        self.routes = []

    def register_web_api(self, path, handler, methods, description):
        self.routes.append((path, handler, methods))


def make_event():
    """最小事件桩：plain_result/chain_result 记录产生的消息链。"""
    produced = []

    def plain(text):
        produced.append(("text", text))
        return ("text", text)

    def chain(components):
        produced.append(("chain", components))
        return ("chain", components)

    event = SimpleNamespace(
        unified_msg_origin="platform:group:1",
        plain_result=plain,
        chain_result=chain,
        platform_meta=SimpleNamespace(support_ui_interaction=False),
    )
    return event, produced


class CaptureToolTests(unittest.IsolatedAsyncioTestCase):
    def _make_tool_plugin(self, settings_overrides=None):
        plugin = make_plugin(settings_overrides)
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        return plugin

    async def test_tool_sends_images_explicitly_and_validates_urls(self):
        plugin = self._make_tool_plugin()
        event, produced = make_event()

        outcomes = [
            capture_pipeline_module.CaptureOutcome(
                url="https://ok.example/",
                ok=True,
                screenshot=b"\x89PNG-bytes",
                title="页面",
                final_url="https://ok.example/",
            )
        ]
        plugin.pipeline.capture_batch = AsyncMock(return_value=outcomes)

        result = await plugin.capture_webpage_tool(
            event, ["https://ok.example/", "http://127.0.0.1:6185/"]
        )

        # 图片必须显式发送（宿主不会派发工具 handler 的 yield）
        plugin.context.send_message.assert_awaited()
        chains = [call.args[1] for call in plugin.context.send_message.await_args_list]
        self.assertEqual(len(chains), 1)
        image = chains[0][1][0]
        self.assertTrue(str(image.file).startswith("base64://"))

        # 回环地址被默认规则拒绝，并向模型报告
        plugin.pipeline.capture_batch.assert_awaited_once()
        self.assertEqual(
            plugin.pipeline.capture_batch.await_args.args[0], ["https://ok.example/"]
        )
        self.assertIn("127.0.0.1", result)
        self.assertIn("已拒绝", result)
        self.assertIn("截图已发送", result)

    async def test_tool_allow_local_screenshots_loopback(self):
        plugin = self._make_tool_plugin({"allow_local_addresses": True})
        event, produced = make_event()
        outcomes = [
            capture_pipeline_module.CaptureOutcome(
                url="http://127.0.0.1:6185/", ok=True, screenshot=b"\x89PNG"
            )
        ]
        plugin.pipeline.capture_batch = AsyncMock(return_value=outcomes)

        result = await plugin.capture_webpage_tool(event, ["http://127.0.0.1:6185/"])
        self.assertEqual(
            plugin.pipeline.capture_batch.await_args.args[0], ["http://127.0.0.1:6185/"]
        )
        self.assertIn("截图已发送", result)
        self.assertNotIn("已拒绝", result)

    async def test_direct_send_routes_cards_through_emit_view(self):
        """ViewResult 不能交给 context.send_message（适配器只收消息链），
        直接发送路径必须经由宿主 emit_view。"""
        import sys

        emit_calls = []

        async def fake_emit_view(event, module, result):
            emit_calls.append((module, result.name))

        chatui_stub = types.ModuleType("astrbot.core.chatui")
        chatui_stub.emit_view = fake_emit_view
        sys.modules["astrbot.core.chatui"] = chatui_stub

        plugin = self._make_tool_plugin()
        event, produced = make_event()
        event.platform_meta = SimpleNamespace(support_ui_interaction=True)
        # 事件需提供 view_result 与 send（emit_view 用 event.send 发消息链）
        view_results = []

        def view_result(**kwargs):
            view_results.append(kwargs)
            return SimpleNamespace(**kwargs)

        event.view_result = view_result
        event.send = AsyncMock()

        outcomes = [
            capture_pipeline_module.CaptureOutcome(
                url="https://ok.example/",
                ok=True,
                screenshot=b"\x89PNG",
                thumbnail=b"thumb-bytes",
            )
        ]
        plugin.pipeline.capture_batch = AsyncMock(return_value=outcomes)

        async for _ in plugin._deliver(event, outcomes, send_directly=True):
            pass

        # 图片走 send_message；卡片走 emit_view，而不是 send_message
        plugin.context.send_message.assert_awaited_once()
        self.assertEqual(len(emit_calls), 1)
        self.assertEqual(emit_calls[0][1], "screenshot_card")
        self.assertEqual(
            emit_calls[0][0],
            "web_analyzer_test_package.main",
        )


class RegistrationTests(unittest.TestCase):
    def test_handlers_keep_expected_calling_conventions(self):
        """Regression guards: auto/command paths iterate _run_and_deliver with
        `async for` (it must be an async generator); tool handlers are
        coroutines whose return value goes to the model."""
        import inspect

        self.assertTrue(
            inspect.isasyncgenfunction(WebScreenshotPlugin._run_and_deliver)
        )
        self.assertTrue(inspect.isasyncgenfunction(WebScreenshotPlugin._deliver))
        self.assertTrue(
            inspect.iscoroutinefunction(WebScreenshotPlugin.capture_webpage_tool)
        )
        self.assertTrue(
            inspect.iscoroutinefunction(WebScreenshotPlugin.get_webpage_content_tool)
        )

    def test_all_dashboard_routes_are_registered(self):
        plugin = WebScreenshotPlugin.__new__(WebScreenshotPlugin)
        plugin._web_api_registered = False
        context = FakeContext()
        plugin._register_web_api(context)
        paths = [route[0] for route in context.routes]
        prefix = f"/{PLUGIN_NAME}/dashboard"
        for expected in (
            f"{prefix}/overview",
            f"{prefix}/cache",
            f"{prefix}/cache/clear",
            f"{prefix}/cache/delete",
            f"{prefix}/cache/preview",
            f"{prefix}/rules",
            f"{prefix}/browser",
            f"{prefix}/browser/recheck",
            f"{prefix}/browser/cleanup",
        ):
            self.assertIn(expected, paths)

    def test_registration_is_idempotent(self):
        plugin = WebScreenshotPlugin.__new__(WebScreenshotPlugin)
        plugin._web_api_registered = False
        context = FakeContext()
        plugin._register_web_api(context)
        plugin._register_web_api(context)
        self.assertEqual(len(context.routes), 9)


class OverviewApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_overview_reports_cache_and_capture_settings(self):
        plugin = make_plugin({"auto_capture": False, "max_concurrency": 7})
        response = await plugin._api_overview()
        data = json.loads(response.body)
        self.assertIn("cache_stats", data)
        self.assertFalse(data["auto_capture"])
        self.assertEqual(data["max_concurrency"], 7)
        self.assertEqual(data["screenshot"]["width"], 1280)
        self.assertTrue(data["handoff_to_model"])

    async def test_rules_return_effective_config_only(self):
        plugin = make_plugin({"group_blacklist": ["1", "2"]})
        response = await plugin._api_rules()
        data = json.loads(response.body)
        self.assertEqual(data["group_blacklist"], ["1", "2"])
        self.assertIn("allowed_domains", data)
        self.assertIn("blocked_domains", data)


class CacheApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_list_delete_and_clear(self):
        plugin = make_plugin()
        from test_support import cache_module

        key = cache_module.build_cache_key(
            "https://example.com/",
            {
                "width": 1,
                "height": 1,
                "full_page": 1,
                "format": 1,
                "quality": 1,
                "wait_strategy": 1,
                "wait_time": 1,
            },
        )
        plugin.cache.put(
            key, "https://example.com/", {}, {"title": "T"}, b"\x89PNG-data"
        )

        response = await plugin._api_cache()
        data = json.loads(response.body)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["id"], key)

        # search miss
        import astrbot.api.web as web

        with patch.object(web.request, "query", {"query": "other"}):
            response = await plugin._api_cache()
        data = json.loads(response.body)
        self.assertEqual(data["items"], [])

        with patch.object(web.request, "json", new=AsyncMock(return_value={"id": key})):
            response = await plugin._api_cache_delete()
        self.assertEqual(json.loads(response.body)["message"], "已删除缓存")
        self.assertEqual(plugin.cache.get_stats()["total"], 0)

    async def test_cache_preview_returns_data_url(self):
        plugin = make_plugin()
        from test_support import cache_module

        import astrbot.api.web as web

        key = cache_module.build_cache_key(
            "https://preview.example/",
            {
                "width": 1,
                "height": 1,
                "full_page": 1,
                "format": 1,
                "quality": 1,
                "wait_strategy": 1,
                "wait_time": 1,
            },
        )
        payload = b"\x89PNG\r\n\x1a\n" + b"fake"
        plugin.cache.put(key, "https://preview.example/", {}, {}, payload)

        with patch.object(web.request, "query", {"id": key}):
            response = await plugin._api_cache_preview()
        data = json.loads(response.body)
        self.assertTrue(data["data_url"].startswith("data:image/png;base64,"))
        decoded = base64.b64decode(data["data_url"].split(",", 1)[1])
        self.assertEqual(decoded, payload)

    async def test_cache_preview_rejects_bad_ids(self):
        plugin = make_plugin()
        import astrbot.api.web as web

        with patch.object(web.request, "query", {"id": "../escape"}):
            response = await plugin._api_cache_preview()
        self.assertEqual(response.status_code, 400)

    async def test_cache_clear(self):
        plugin = make_plugin()
        from test_support import cache_module

        key = cache_module.build_cache_key(
            "https://x.example/",
            {
                "width": 1,
                "height": 1,
                "full_page": 1,
                "format": 1,
                "quality": 1,
                "wait_strategy": 1,
                "wait_time": 1,
            },
        )
        plugin.cache.put(key, "https://x.example/", {}, {}, b"b")
        response = await plugin._api_cache_clear()
        data = json.loads(response.body)
        self.assertEqual(data["stats"]["total"], 0)


class BrowserApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_status_and_recheck(self):
        plugin = make_plugin()
        fake_status = {
            "installed": True,
            "install_path": "/usr/bin/chrome",
            "browser_type": "Google Chrome",
            "browser_version": "130",
            "browser_pool_size": 0,
            "browser_instances": 0,
            "max_browser_instances": 3,
            "skipped_browsers": {},
            "legacy_dir_exists": False,
            "legacy_dir_size_mb": 0.0,
        }
        with (
            patch.object(
                plugin.screenshot_service,
                "get_browser_status",
                new=AsyncMock(return_value=fake_status),
            ),
            patch.object(
                plugin.screenshot_service, "_reset_browser_detection"
            ) as reset,
        ):
            response = await plugin._api_browser_recheck()
        reset.assert_called_once()
        data = json.loads(response.body)
        self.assertTrue(data["installed"])

    async def test_cleanup_reports_result_and_status(self):
        plugin = make_plugin()
        with (
            patch.object(
                plugin.screenshot_service,
                "uninstall_legacy_artifacts",
                new=AsyncMock(return_value={"success": True, "message": "done"}),
            ),
            patch.object(
                plugin.screenshot_service,
                "get_browser_status",
                new=AsyncMock(return_value={"installed": False}),
            ),
        ):
            response = await plugin._api_browser_cleanup()
        data = json.loads(response.body)
        self.assertTrue(data["success"])
        self.assertIn("status", data)


if __name__ == "__main__":
    unittest.main()
