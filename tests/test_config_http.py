import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load_package():
    package_name = "web_analyzer_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT / "core")]
    sys.modules[package_name] = package

    core_package_name = f"{package_name}.core"
    core_package = types.ModuleType(core_package_name)
    core_package.__path__ = [str(PLUGIN_ROOT / "core")]
    sys.modules[core_package_name] = core_package

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    star = types.ModuleType("astrbot.api.star")
    star.Context = type("Context", (), {})
    sys.modules.setdefault("astrbot", astrbot)
    sys.modules.setdefault("astrbot.api", api)
    sys.modules.setdefault("astrbot.api.star", star)

    for module_name in ("utils", "config_loader", "browser", "analyzer"):
        full_name = f"{core_package_name}.{module_name}"
        module_path = PLUGIN_ROOT / "core" / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(full_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)

    return sys.modules[f"{core_package_name}.config_loader"].ConfigLoader, sys.modules[
        f"{core_package_name}.analyzer"
    ].WebAnalyzer


ConfigLoader, WebAnalyzer = _load_package()


class ConfigFetchModeTests(unittest.TestCase):
    def _load_mode(self, mode):
        config = {"基础设置": {"网络设置": {"fetch_mode": mode}}}
        loaded = ConfigLoader._load_basic_settings(config)
        return loaded["fetch_mode"], config["基础设置"]["网络设置"]["fetch_mode"]

    def test_legacy_playwright_mode_is_normalized(self):
        self.assertEqual(self._load_mode("playwright"), ("browser", "browser"))

    def test_browser_mode_is_preserved(self):
        self.assertEqual(self._load_mode("browser"), ("browser", "browser"))

    def test_httpx_mode_is_preserved(self):
        self.assertEqual(self._load_mode("httpx"), ("httpx", "httpx"))


class SharedHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_contexts_share_client_and_close_on_last_exit(self):
        analyzer = WebAnalyzer(enable_memory_monitor=False)
        client = types.SimpleNamespace(aclose=AsyncMock())
        started = asyncio.Event()
        allow_first_exit = asyncio.Event()
        clients_created = []

        def make_client(**kwargs):
            clients_created.append(kwargs)
            return client

        async def first_context():
            async with analyzer:
                started.set()
                await allow_first_exit.wait()

        with patch.object(
            sys.modules["web_analyzer_test_package.core.analyzer"].httpx,
            "AsyncClient",
            side_effect=make_client,
        ) as client_factory:
            first = asyncio.create_task(first_context())
            await started.wait()
            second = asyncio.create_task(analyzer.__aenter__())
            await second

            self.assertEqual(client_factory.call_count, 1)
            self.assertIs(analyzer.client, client)
            await analyzer.__aexit__(None, None, None)
            client.aclose.assert_not_awaited()

            allow_first_exit.set()
            await first

        client.aclose.assert_awaited_once_with()
        self.assertIsNone(analyzer.client)
        self.assertEqual(analyzer._client_refs, 0)
        self.assertEqual(len(clients_created), 1)
