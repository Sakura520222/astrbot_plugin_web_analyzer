"""Regression tests for the lightweight browser driver and resource ownership."""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import psutil
from test_config_http import WebAnalyzer

analyzer_module = sys.modules[WebAnalyzer.__module__]
browser_module = sys.modules[WebAnalyzer.__module__.rsplit(".", 1)[0] + ".browser"]
BrowserInstance = browser_module.BrowserInstance
CDPPage = browser_module.CDPPage
BrowserError = browser_module.BrowserError


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_blank_lifecycle_does_not_complete_navigation(self):
        browser = SimpleNamespace(is_connected=lambda: True)
        page = CDPPage(browser, "tab", "session")
        navigating = asyncio.Event()

        async def navigate(*args, **kwargs):
            page._on_event(
                "Page.lifecycleEvent",
                {"frameId": "main", "loaderId": "blank", "name": "DOMContentLoaded"},
            )
            navigating.set()
            return {"frameId": "main", "loaderId": "target"}

        page._send = AsyncMock(side_effect=navigate)
        task = asyncio.create_task(page.goto("https://example.test", timeout=1000))
        await navigating.wait()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        page._on_event(
            "Page.lifecycleEvent",
            {"frameId": "main", "loaderId": "target", "name": "DOMContentLoaded"},
        )
        await task

    async def test_lifecycle_before_command_response_is_retained(self):
        page = CDPPage(SimpleNamespace(is_connected=lambda: True), "tab", "session")

        async def navigate(*args, **kwargs):
            page._on_event(
                "Page.lifecycleEvent",
                {"frameId": "main", "loaderId": "target", "name": "DOMContentLoaded"},
            )
            return {"frameId": "main", "loaderId": "target"}

        page._send = AsyncMock(side_effect=navigate)
        await page.goto("https://example.test", timeout=1000)

    async def test_same_document_navigation_requires_no_new_event(self):
        page = CDPPage(SimpleNamespace(is_connected=lambda: True), "tab", "session")
        page._send = AsyncMock(return_value={"frameId": "main"})
        await page.goto("https://example.test/#anchor", timeout=20)

    async def test_only_proxy_challenges_receive_proxy_credentials(self):
        page = CDPPage(
            SimpleNamespace(_proxy_credentials=("user", "secret")), "tab", "s"
        )
        page._send = AsyncMock()
        for source in ("Server", "Proxy", "Proxy"):
            await page._handle_fetch_event(
                "Fetch.authRequired",
                {"requestId": "one", "authChallenge": {"source": source}},
            )
        responses = [
            call.args[1]["authChallengeResponse"] for call in page._send.await_args_list
        ]
        self.assertEqual(responses[0], {"response": "Default"})
        self.assertEqual(responses[1]["username"], "user")
        self.assertEqual(responses[2], {"response": "CancelAuth"})

    async def test_oversized_screenshot_rejected_before_capture(self):
        page = CDPPage(None, "tab", "session")
        page._send = AsyncMock(
            return_value={"cssContentSize": {"width": 4000, "height": 30000}}
        )
        with self.assertRaises(BrowserError):
            await page.screenshot(full_page=True, format="png")
        self.assertEqual(page._send.await_count, 1)

    def test_proxy_credentials_removed_and_url_decoded(self):
        analyzer = WebAnalyzer(
            hide_ip=True, proxy="http://user%40name:p%3Ass@[::1]:8080"
        )
        args = analyzer._build_browser_launch_args()
        self.assertIn("--proxy-server=http://[::1]:8080", args)
        self.assertEqual(analyzer._browser_proxy_credentials, ("user@name", "p:ss"))
        self.assertFalse(any("user%40" in arg for arg in args))


class ResourceOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        WebAnalyzer._browser_lock = asyncio.Lock()
        WebAnalyzer._browser_pool = []
        WebAnalyzer._browser_instances = set()
        WebAnalyzer._browser_last_used = {}
        WebAnalyzer._shutting_down = False
        self.analyzer = WebAnalyzer(enable_memory_monitor=False)

    @staticmethod
    def browser():
        return Mock(close=AsyncMock(), is_connected=lambda: True)

    async def test_fresh_screenshot_failure_closes_browser(self):
        browser = self.browser()
        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(return_value=(browser, False)),
            ),
            patch.object(
                self.analyzer,
                "_perform_screenshot",
                new=AsyncMock(side_effect=BrowserError("failed")),
            ),
        ):
            with self.assertRaises(analyzer_module.ScreenshotError):
                await self.analyzer.capture_screenshot("https://example.test")
        browser.close.assert_awaited_once()
        self.assertEqual(WebAnalyzer._browser_pool, [])

    async def test_cancelled_screenshot_closes_browser(self):
        browser = self.browser()
        entered = asyncio.Event()

        async def screenshot(**kwargs):
            entered.set()
            await asyncio.Event().wait()

        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(return_value=(browser, False)),
            ),
            patch.object(self.analyzer, "_perform_screenshot", side_effect=screenshot),
        ):
            task = asyncio.create_task(
                self.analyzer.capture_screenshot("https://example.test")
            )
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        browser.close.assert_awaited_once()

    async def test_cancel_during_page_close_still_closes_browser(self):
        browser = self.browser()
        closing = asyncio.Event()

        async def page_close():
            closing.set()
            await asyncio.Event().wait()

        page = SimpleNamespace(
            goto=AsyncMock(),
            wait_for_timeout=AsyncMock(),
            content=AsyncMock(return_value="<html>ok</html>"),
            close=page_close,
        )
        browser.new_page = AsyncMock(return_value=page)
        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(return_value=(browser, False)),
            ),
        ):
            task = asyncio.create_task(
                self.analyzer._fetch_with_browser("https://example.test")
            )
            await closing.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        browser.close.assert_awaited_once()
        self.assertEqual(WebAnalyzer._browser_pool, [])

    async def test_pooled_failure_retries_and_recycles_success(self):
        first, second = self.browser(), self.browser()
        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(return_value=(first, True)),
            ),
            patch.object(
                self.analyzer, "_create_new_browser", new=AsyncMock(return_value=second)
            ),
            patch.object(
                self.analyzer,
                "_perform_screenshot",
                new=AsyncMock(side_effect=[BrowserError("dead"), b"image"]),
            ),
            patch.object(self.analyzer, "_recycle_browser", new=AsyncMock()) as recycle,
        ):
            result = await self.analyzer.capture_screenshot("https://example.test")
        self.assertEqual(result, b"image")
        first.close.assert_awaited_once()
        second.close.assert_not_awaited()
        recycle.assert_awaited_once_with(second)

    async def test_cancel_during_spawn_waits_for_popen_then_closes(self):
        browser = BrowserInstance("unused")
        started = threading.Event()
        release = threading.Event()
        process = SimpleNamespace(pid=12345)

        def spawn(*args, **kwargs):
            started.set()
            release.wait(5)
            return process

        browser._terminate_process = AsyncMock()
        browser._cleanup_profile_dir = AsyncMock()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(browser_module.tempfile, "mkdtemp", return_value=temp),
            patch.object(browser_module.subprocess, "Popen", side_effect=spawn),
        ):
            task = asyncio.create_task(browser.start())
            await asyncio.to_thread(started.wait, 5)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIs(browser._process, process)
        browser._terminate_process.assert_awaited_once()

    async def test_cancelled_protocol_command_removes_pending_future(self):
        browser = BrowserInstance("unused")
        browser._ws_alive = True
        browser._ws = SimpleNamespace(send=AsyncMock())
        task = asyncio.create_task(browser.send_command("Test.command"))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(browser._pending_commands, {})

    async def test_sweep_preserves_live_and_unmarked_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [
                Path(temp) / (browser_module.PROFILE_DIR_PREFIX + suffix)
                for suffix in ("live", "unmarked", "dead")
            ]
            for path in paths:
                path.mkdir()
            (paths[0] / "astrbot-owner.json").write_text(
                json.dumps(
                    [{"pid": os.getpid(), "created": psutil.Process().create_time()}]
                )
            )
            (paths[2] / "astrbot-owner.json").write_text(
                json.dumps([{"pid": 2147483647, "created": 0}])
            )
            for path in paths:
                os.utime(path, (time.time() - 25000,) * 2)
            with patch.object(browser_module.tempfile, "gettempdir", return_value=temp):
                await browser_module.sweep_stale_browser_artifacts()
            self.assertTrue(paths[0].exists())
            self.assertTrue(paths[1].exists())
            self.assertFalse(paths[2].exists())
