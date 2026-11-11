import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from test_config_http import WebAnalyzer


class RuntimeNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_http_client_survives_config_change_and_new_context_uses_new_settings(
        self,
    ):
        analyzer = WebAnalyzer(
            enable_memory_monitor=False, timeout=11, user_agent="old"
        )
        old_client = types.SimpleNamespace(aclose=AsyncMock())
        new_client = types.SimpleNamespace(aclose=AsyncMock())
        factory = patch.object(
            sys.modules["web_analyzer_test_package.core.analyzer"].httpx,
            "AsyncClient",
            side_effect=[old_client, new_client],
        )
        with factory as client_factory:
            await analyzer.__aenter__()
            await analyzer.apply_runtime_config(
                {"request_timeout_s": 22, "proxy": "http://proxy", "user_agent": "new"}
            )
            self.assertFalse(old_client.aclose.await_count)
            await analyzer.__aenter__()
            self.assertEqual(
                client_factory.call_args_list[-1].kwargs,
                {"timeout": 22, "proxy": "http://proxy"},
            )
            self.assertEqual(analyzer._current_request_snapshot()["user_agent"], "new")
            await analyzer.__aexit__(None, None, None)
            self.assertFalse(old_client.aclose.await_count)
            await analyzer.__aexit__(None, None, None)
        old_client.aclose.assert_awaited_once()
        new_client.aclose.assert_awaited_once()

    async def test_monitor_toggles_and_threshold_updates(self):
        analyzer = WebAnalyzer(enable_memory_monitor=False)
        analyzer.memory_check_interval = 3600
        await analyzer.apply_runtime_config(
            {"enable_memory_monitor": True, "memory_threshold_percent": 61}
        )
        task = analyzer._memory_monitor_task
        self.assertIsNotNone(task)
        self.assertEqual(analyzer.memory_threshold, 61)
        await analyzer.apply_runtime_config(
            {"enable_memory_monitor": False, "memory_threshold_percent": 72}
        )
        self.assertTrue(task.cancelled() or task.cancelling())
        self.assertIsNone(analyzer._memory_monitor_task)
        self.assertEqual(analyzer.memory_threshold, 72)

    async def test_close_cancels_monitor_and_closes_every_generation(self):
        analyzer = WebAnalyzer(enable_memory_monitor=False)
        old_client = types.SimpleNamespace(aclose=AsyncMock())
        new_client = types.SimpleNamespace(aclose=AsyncMock())
        analyzer._client_generations = {
            1: {"signature": (10, None), "client": old_client, "refs": 1},
            2: {"signature": (20, "http://proxy"), "client": new_client, "refs": 1},
        }
        analyzer._client_refs = 2
        analyzer.client = new_client
        analyzer.enable_memory_monitor = True
        analyzer.memory_check_interval = 3600
        analyzer._sync_memory_monitor()
        monitor = analyzer._memory_monitor_task

        await analyzer.close()

        old_client.aclose.assert_awaited_once()
        new_client.aclose.assert_awaited_once()
        self.assertTrue(monitor.cancelled() or monitor.cancelling())
        self.assertEqual(analyzer._client_generations, {})
        self.assertEqual(analyzer._task_clients, {})
        self.assertEqual(analyzer._client_refs, 0)
        self.assertIsNone(analyzer.client)
        self.assertIsNone(analyzer._memory_monitor_task)

    async def test_runtime_browser_change_closes_idle_but_not_checked_out(self):
        analyzer = WebAnalyzer(enable_memory_monitor=False)
        WebAnalyzer._browser_lock = asyncio.Lock()
        WebAnalyzer._browser_pool = []
        WebAnalyzer._browser_instances = set()

        class Browser:
            def __init__(self):
                self.pool_key = ("auto", False, None)
                self.close = AsyncMock()

        idle = Browser()
        active = Browser()
        WebAnalyzer._browser_pool.append(idle)
        WebAnalyzer._browser_instances.update((idle, active))
        await analyzer.apply_runtime_config({"sandbox_mode": "always_enabled"})
        idle.close.assert_awaited_once()
        active.close.assert_not_awaited()
        self.assertEqual(WebAnalyzer._browser_pool, [])
        self.assertIn(active, WebAnalyzer._browser_instances)
        WebAnalyzer._browser_instances.clear()


if __name__ == "__main__":
    unittest.main()
