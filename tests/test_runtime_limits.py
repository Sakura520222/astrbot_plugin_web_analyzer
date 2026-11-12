import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load_modules():
    package_name = "web_analyzer_runtime_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT / "core")]
    sys.modules[package_name] = package
    core_name = f"{package_name}.core"
    core = types.ModuleType(core_name)
    core.__path__ = [str(PLUGIN_ROOT / "core")]
    sys.modules[core_name] = core

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = type("AstrMessageEvent", (), {})
    components = types.ModuleType("astrbot.api.message_components")
    for name in ("Image", "Node", "Nodes", "Plain"):
        setattr(components, name, type(name, (), {}))
    sys.modules.setdefault("astrbot", astrbot)
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.message_components"] = components

    # 注入 mock 的 AstrBot 路径辅助模块，使缓存/临时目录使用标准数据路径
    core = types.ModuleType("astrbot.core")
    core.__path__ = []
    sys.modules["astrbot.core"] = core
    utils = types.ModuleType("astrbot.core.utils")
    utils.__path__ = []
    sys.modules["astrbot.core.utils"] = utils
    astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
    plugin_data = str(PLUGIN_ROOT / "data" / "plugin_data" / "astrbot_plugin_web_analyzer")
    astrbot_path.get_astrbot_plugin_data_path = lambda: plugin_data
    astrbot_path.get_astrbot_data_path = lambda: str(PLUGIN_ROOT / "data")
    sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path

    for name in (
        "constants",
        "error_handler",
        "screenshot_temp_manager",
        "cache",
        "message_handler",
    ):
        path = PLUGIN_ROOT / "core" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"{core_name}.{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{core_name}.cache"].CacheManager, sys.modules[
        f"{core_name}.message_handler"
    ].MessageHandler


CacheManager, MessageHandler = _load_modules()


class MessageHandlerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_handler(self, concurrency=2):
        return MessageHandler(
            types.SimpleNamespace(normalize_url=lambda url: url),
            types.SimpleNamespace(),
            max_concurrency=concurrency,
        )

    async def test_limit_can_grow_and_shrink_with_existing_waiters(self):
        handler = self.make_handler(2)
        await handler._acquire_concurrency_slot()
        second_acquired = asyncio.Event()
        release_second = asyncio.Event()

        async def hold_second_slot():
            await handler._acquire_concurrency_slot()
            second_acquired.set()
            await release_second.wait()
            handler._release_concurrency_slot()

        second = asyncio.create_task(hold_second_slot())
        await second_acquired.wait()
        third_acquired = asyncio.Event()
        release_third = asyncio.Event()

        async def hold_third_slot():
            await handler._acquire_concurrency_slot()
            third_acquired.set()
            await release_third.wait()
            handler._release_concurrency_slot()

        third = asyncio.create_task(hold_third_slot())
        await asyncio.sleep(0)
        self.assertFalse(third_acquired.is_set())

        handler.apply_runtime_config({"max_concurrency": 3})
        await asyncio.wait_for(third_acquired.wait(), 1)
        self.assertEqual(handler._active_concurrency, 3)
        handler.apply_runtime_config({"max_concurrency": 1})
        waiter_acquired = asyncio.Event()
        release_waiter = asyncio.Event()
        waiter = asyncio.create_task(
            self._acquire_and_signal(handler, waiter_acquired, release_waiter)
        )
        await asyncio.sleep(0)
        self.assertFalse(waiter_acquired.is_set())
        release_second.set()
        await second
        release_third.set()
        await third
        handler._release_concurrency_slot()
        await asyncio.wait_for(waiter_acquired.wait(), 1)
        self.assertEqual(handler._active_concurrency, 1)
        release_waiter.set()
        await waiter
        self.assertEqual(handler._active_concurrency, 0)

    async def _acquire_and_signal(self, handler, acquired, release):
        await handler._acquire_concurrency_slot()
        acquired.set()
        await release.wait()
        handler._release_concurrency_slot()

    async def test_cancelled_waiter_does_not_leak_slot(self):
        handler = self.make_handler(1)
        await handler._acquire_concurrency_slot()
        waiter = asyncio.create_task(handler._acquire_concurrency_slot())
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        self.assertEqual(handler._active_concurrency, 1)
        handler._release_concurrency_slot()
        await handler._acquire_concurrency_slot()
        handler._release_concurrency_slot()

    async def test_runtime_config_updates_message_and_screenshot_fields(self):
        handler = self.make_handler()
        settings = {
            "enable_cache": False,
            "enable_screenshot": False,
            "send_content_type": "screenshot_only",
            "screenshot_format": "png",
            "screenshot_quality": 61,
            "screenshot_width": 800,
            "screenshot_height": 600,
            "screenshot_full_page": True,
            "screenshot_wait_ms": 1250,
            "screenshot_wait_strategy": "networkidle",
            "enable_crop": True,
            "crop_area": [1, 2, 3, 4],
            "merge_forward_group": True,
            "merge_forward_private": True,
            "merge_forward_include_screenshot": True,
        }
        handler.apply_runtime_config(settings)
        for key, value in settings.items():
            self.assertEqual(getattr(handler, key), value, key)

    async def test_cached_result_is_reformatted_with_current_settings(self):
        analyzer = types.SimpleNamespace(normalize_url=lambda url: url)
        cached_content = {
            "title": "Title",
            "content": "Text",
            "url": "https://example.test",
        }
        cache = types.SimpleNamespace(
            get=lambda url: {
                "result": {
                    "url": url,
                    "result": "raw",
                    "screenshot": None,
                    "has_screenshot": False,
                    "content_data": cached_content,
                    "_settings_revision": "old",
                }
            }
        )
        handler = MessageHandler(analyzer, cache)
        handler.apply_runtime_config({"result_template": "current"})
        handler.check_cache = lambda url: {
            "url": url,
            "result": "raw",
            "screenshot": None,
            "has_screenshot": False,
            "content_data": cached_content,
            "_settings_revision": handler._runtime_settings_revision,
        }
        event = object()
        formatter = types.SimpleNamespace(
            apply_result_settings=lambda **kwargs: (
                f"{kwargs['result']}:{kwargs['result_template']}"
            )
        )
        result = await handler.process_single_url(
            event,
            "https://example.test",
            analyzer,
            result_formatter=formatter,
        )
        self.assertEqual(result["result"], "raw:current")

    async def test_fresh_result_translates_then_uses_enhanced_formatter(self):
        content_data = {
            "title": "Title",
            "content": "original",
            "url": "https://example.test",
        }

        class AnalyzerStub:
            def __init__(self):
                self.normalize_url = lambda url: url
                self.fetch_webpage = AsyncMock(return_value="html")
                self.extract_content = lambda html, url: dict(content_data)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        analyzer = AnalyzerStub()
        cache = types.SimpleNamespace(
            get=lambda url: None,
            set_with_content_hash=lambda *args: None,
            set=lambda *args: None,
        )
        handler = self.make_handler()
        handler.cache_manager = cache
        handler.analyzer = analyzer
        handler._generate_screenshot = AsyncMock(return_value=None)
        formatter = types.SimpleNamespace(
            build_enhanced_analysis=lambda data: f"enhanced:{data['content']}",
            apply_result_settings=lambda **kwargs: f"formatted:{kwargs['result']}",
        )
        translator = AsyncMock(return_value="translated")
        result = await handler.process_single_url(
            object(),
            "https://example.test",
            analyzer,
            enable_translation=True,
            result_formatter=formatter,
            translate_content=translator,
        )
        translator.assert_awaited_once()
        self.assertEqual(translator.await_args.args[1], "original")
        self.assertEqual(result["result"], "formatted:enhanced:translated")
        self.assertEqual(content_data["content"], "original")

    async def test_cache_revision_mismatch_is_rejected(self):
        handler = self.make_handler()
        handler.apply_runtime_config({"custom_prompt": "changed"})
        handler.cache_manager.get = lambda url: {
            "result": {"_settings_revision": "old", "result": "stale"}
        }
        self.assertIsNone(handler.check_cache("https://example.test"))

    def test_runtime_limits_expiry_capacity_and_preload(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            manager = CacheManager(cache_dir=cache_dir, max_size=10)
            for index in range(4):
                manager.set(f"https://example.test/{index}", {"result": str(index)})
            self.assertEqual(len(manager.memory_cache), 4)

            manager.apply_runtime_config(
                {
                    "max_cache_size": 2,
                    "cache_expire_time_min": 5,
                    "cache_preload_count": 1,
                    "cache_preload_enabled": True,
                }
            )
            self.assertEqual(manager.max_size, 2)
            self.assertEqual(manager.expire_time, 300)
            self.assertEqual(len(manager.memory_cache), 2)
            self.assertTrue(manager.preload_enabled)
            self.assertEqual(manager.preload_count, 1)

            manager.apply_runtime_config({"cache_preload_enabled": False})
            self.assertFalse(manager.preload_enabled)
            self.assertEqual(len(manager.memory_cache), 2)

            manager.apply_runtime_config({"cache_expire_time_min": 1})
            url = next(iter(manager.memory_cache))
            manager.memory_cache[url]["timestamp"] -= 61
            self.assertIsNone(manager.get(url))

    def test_preload_count_zero_disables_loading_without_clearing_cache(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            seed = CacheManager(cache_dir=cache_dir)
            seed.set("https://example.test/saved", {"result": "saved"})
            reloaded = CacheManager(cache_dir=cache_dir, preload_enabled=False)
            self.assertEqual(len(reloaded.memory_cache), 1)
            reloaded.apply_runtime_config(
                {"cache_preload_enabled": True, "cache_preload_count": 0}
            )
            self.assertEqual(reloaded.preload_count, 0)
            self.assertEqual(len(reloaded.memory_cache), 1)
            self.assertEqual(
                reloaded.get("https://example.test/saved"), {"result": "saved"}
            )


if __name__ == "__main__":
    unittest.main()
