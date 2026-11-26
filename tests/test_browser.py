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
BrowserExecutableError = browser_module.BrowserExecutableError
BrowserLaunchError = browser_module.BrowserLaunchError
CdpNavigationError = browser_module.CdpNavigationError
CdpTimeoutError = browser_module.CdpTimeoutError
PageLimitError = browser_module.PageLimitError


def reset_browser_state():
    """Give each test empty pools and primitives bound to its own event loop."""
    WebAnalyzer._shutting_down = False
    WebAnalyzer._browser_lock = asyncio.Lock()
    WebAnalyzer._detect_lock = asyncio.Lock()
    WebAnalyzer._browser_slot_released = asyncio.Event()
    WebAnalyzer._browser_pool = []
    WebAnalyzer._browser_instances = set()
    WebAnalyzer._browser_last_used = {}
    WebAnalyzer._browser_blacklist = {}
    WebAnalyzer._detected_browser_path = ""
    WebAnalyzer._detected_browser_name = ""
    WebAnalyzer._detected_browser_version = ""


async def eventually(condition, timeout=5):
    """Wait until the condition holds instead of relying on a fixed sleep."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0.01)


class FakeBrowser:
    """Stand-in for BrowserInstance that reports closure like the real driver."""

    created = []
    launch_error = None

    def __init__(
        self,
        executable_path,
        extra_args=None,
        command_timeout=30.0,
        proxy_credentials=None,
    ):
        self.executable_path = executable_path
        self.extra_args = extra_args
        self.proxy_credentials = proxy_credentials
        self.on_closed = None
        self.pool_key = None
        self.version = "Fake/130.0"
        self.closed = False
        FakeBrowser.created.append(self)

    async def start(self):
        # Yield like a real process launch so that other requests interleave.
        await asyncio.sleep(0.01)
        if FakeBrowser.launch_error:
            await self.close()
            raise FakeBrowser.launch_error

    def is_connected(self):
        return not self.closed

    async def close(self):
        self.closed = True
        if self.on_closed:
            self.on_closed()


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

    async def test_slow_page_is_not_an_instance_failure(self):
        page = CDPPage(SimpleNamespace(is_connected=lambda: True), "tab", "session")
        page._send = AsyncMock(return_value={"frameId": "main", "loaderId": "target"})
        with self.assertRaises(CdpNavigationError) as caught:
            await page.goto("https://example.test", timeout=20)
        self.assertIn("Page navigation timed out", str(caught.exception))
        self.assertFalse(caught.exception.instance_failure)

    async def test_unanswered_navigation_command_is_an_instance_failure(self):
        page = CDPPage(SimpleNamespace(is_connected=lambda: True), "tab", "session")

        async def never_answers(*args, **kwargs):
            await asyncio.Event().wait()

        page._send = AsyncMock(side_effect=never_answers)
        with self.assertRaises(CdpTimeoutError) as caught:
            await page.goto("https://example.test", timeout=20)
        self.assertTrue(caught.exception.instance_failure)

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
        with self.assertRaises(PageLimitError) as caught:
            await page.screenshot(full_page=True, format="png")
        self.assertFalse(caught.exception.instance_failure)
        self.assertEqual(page._send.await_count, 1)

    def test_proxy_credentials_removed_and_url_decoded(self):
        analyzer = WebAnalyzer(
            hide_ip=True, proxy="http://user%40name:p%3Ass@[::1]:8080"
        )
        args = analyzer._build_browser_launch_args()
        self.assertIn("--proxy-server=http://[::1]:8080", args)
        self.assertEqual(analyzer._browser_proxy_credentials, ("user@name", "p:ss"))
        self.assertFalse(any("user%40" in arg for arg in args))


class LaunchFailureTests(unittest.IsolatedAsyncioTestCase):
    """Classify the driver's launch failures without starting a real browser."""

    async def test_missing_executable_cannot_run_here(self):
        missing = Path(tempfile.gettempdir()) / "astrbot_wa_missing" / "chrome"
        with self.assertRaises(BrowserExecutableError) as caught:
            await BrowserInstance(str(missing)).start()
        self.assertIn("Cannot execute system browser", str(caught.exception))

    async def test_early_exit_with_error_status_reports_the_browser_reason(self):
        process = Mock(pid=os.getpid(), returncode=1)
        process.poll.return_value = 1

        def spawn(args, **kwargs):
            kwargs["stderr"].write(b"gpu noise\n[FATAL:sandbox] No usable sandbox\n")
            return process

        browser = BrowserInstance("unused")
        browser.on_closed = Mock()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(browser_module.tempfile, "mkdtemp", return_value=temp),
            patch.object(browser_module.subprocess, "Popen", side_effect=spawn),
        ):
            with self.assertRaises(BrowserExecutableError) as caught:
                await browser.start()
            # The temporary profile, including the stderr log, is removed.
            self.assertEqual(browser._profile_dir, "")
            self.assertFalse(Path(temp).exists())
        self.assertEqual(
            str(caught.exception),
            "Browser exited with code 1: [FATAL:sandbox] No usable sandbox",
        )
        browser.on_closed.assert_called_once()

    async def test_closing_the_real_driver_reports_freed_capacity_once(self):
        browser = BrowserInstance("unused")
        browser.on_closed = Mock()
        await browser.close()
        await browser.close()  # repeated close must not count the slot twice
        browser.on_closed.assert_called_once()

    async def test_signal_exit_may_pass_on_a_later_request(self):
        process = Mock(pid=os.getpid(), returncode=-9)
        process.poll.return_value = -9
        browser = BrowserInstance("unused")
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(browser_module.tempfile, "mkdtemp", return_value=temp),
            patch.object(browser_module.subprocess, "Popen", return_value=process),
        ):
            with self.assertRaises(BrowserLaunchError) as caught:
                await browser.start()
        self.assertNotIsInstance(caught.exception, BrowserExecutableError)

    async def test_slow_start_may_pass_on_a_later_request(self):
        process = Mock(pid=os.getpid())
        process.poll.return_value = None
        browser = BrowserInstance("unused")
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(browser_module.tempfile, "mkdtemp", return_value=temp),
            patch.object(browser_module.subprocess, "Popen", return_value=process),
            patch.object(browser_module, "_LAUNCH_TIMEOUT", 0),
        ):
            with self.assertRaises(BrowserLaunchError) as caught:
                await browser.start()
        self.assertIn("Timed out", str(caught.exception))
        self.assertNotIsInstance(caught.exception, BrowserExecutableError)

    async def test_unexpected_disconnect_reports_the_signal_and_fails_commands(
        self,
    ):
        class DeadSocket:
            send = AsyncMock()

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise OSError("connection reset")

        browser = BrowserInstance("unused")
        browser._ws_alive = True
        browser._process = SimpleNamespace(poll=lambda: -9)
        browser._ws = DeadSocket()
        pending = asyncio.create_task(browser.send_command("Browser.getVersion"))
        await asyncio.sleep(0)
        with patch.object(browser_module, "logger") as log:
            await browser._reader_loop()
        log.warning.assert_called_once()
        self.assertIn("was killed by signal 9", log.warning.call_args.args[0])
        with self.assertRaises(BrowserError):
            await pending
        self.assertFalse(browser.is_connected())

    async def test_deliberate_close_is_not_reported_as_a_lost_connection(self):
        class ClosedSocket:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        browser = BrowserInstance("unused")
        browser._ws_alive = True
        browser._close_task = Mock()
        browser._ws = ClosedSocket()
        with patch.object(browser_module, "logger") as log:
            await browser._reader_loop()
        log.warning.assert_not_called()
        log.debug.assert_called_once()

    async def test_page_setup_failure_disposes_the_browser_context(self):
        browser = BrowserInstance("unused", command_timeout=42)
        browser.send_command = AsyncMock(
            side_effect=[
                {"browserContextId": "ctx"},
                CdpTimeoutError("CDP command timed out: Target.createTarget"),
                {},
            ]
        )
        with self.assertRaises(CdpTimeoutError):
            await browser.new_page()
        self.assertEqual(
            browser.send_command.await_args_list[2].args,
            ("Target.disposeBrowserContext", {"browserContextId": "ctx"}),
        )
        self.assertEqual(browser._pages, {})
        # A slow container gets the instance timeout instead of a fixed 15s.
        self.assertEqual(
            browser.send_command.await_args_list[0].kwargs, {"timeout": 42}
        )

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


class BrowserDetectionTests(unittest.TestCase):
    """detect_system_browser explains a failed detection from the log alone."""

    # Commands of the Linux candidate list and the paths they resolve to.
    COMMANDS = {
        "chromium": "/usr/bin/chromium",
        "chromium-browser": "/usr/bin/chromium-browser",
    }
    # Both names are links to one binary, as shipped by several distributions.
    # Keys are compared as Path strings: Windows prints "/usr/bin/x" differently.
    BINARY = {
        str(Path("/usr/bin/chromium")): "/opt/chromium",
        str(Path("/usr/bin/chromium-browser")): "/opt/chromium",
    }
    CHROMIUM = "/usr/bin/chromium"

    def detect(self, existing=(), executable=True, **kwargs):
        """Run a Linux detection on which only ``existing`` paths are present."""
        present = {Path(path) for path in existing}
        with (
            patch.object(browser_module.platform, "system", return_value="Linux"),
            patch.object(
                browser_module.Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: path in present,
            ),
            patch.object(browser_module.os, "access", return_value=executable),
            patch.object(
                browser_module.os.path,
                "realpath",
                side_effect=lambda path: self.BINARY.get(str(Path(path)), path),
            ),
            patch.object(
                browser_module.shutil,
                "which",
                side_effect=lambda command: (
                    self.COMMANDS.get(command)
                    if self.COMMANDS.get(command) in existing
                    else None
                ),
            ),
            patch.object(browser_module, "logger") as log,
        ):
            found = browser_module.detect_system_browser(**kwargs)
        return found, log

    def test_failure_lists_rejected_candidates_and_the_search_path(self):
        found, log = self.detect()
        self.assertEqual(found, (False, "", "", ""))
        log.warning.assert_called_once()
        message = log.warning.call_args.args[0]
        self.assertIn(f"{Path(self.CHROMIUM)} (not found)", message)
        self.assertIn("PATH=", message)

    def test_unexecutable_candidate_is_skipped_and_reported(self):
        found, log = self.detect({self.CHROMIUM}, executable=False)
        self.assertFalse(found[0])
        self.assertIn(
            f"{Path(self.CHROMIUM)} (not executable)", log.warning.call_args.args[0]
        )

    def test_rejected_executable_and_its_aliases_are_skipped(self):
        existing = {self.CHROMIUM, "/usr/bin/chromium-browser"}
        version = SimpleNamespace(stdout="Chromium 130")
        with patch.object(
            browser_module.subprocess, "run", return_value=version
        ) as run:
            found, _ = self.detect(existing)
            self.assertEqual(found, (True, self.CHROMIUM, "Chromium", "Chromium 130"))
            run.reset_mock()
            found, log = self.detect(existing, exclude_paths={self.CHROMIUM})
        self.assertFalse(found[0])
        # The alias leads to the rejected binary, so it is never launched.
        run.assert_not_called()
        self.assertIn("(launch failed earlier)", log.warning.call_args.args[0])


class ScreenshotRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_browser_state()
        self.analyzer = WebAnalyzer(enable_memory_monitor=False)

    @staticmethod
    def browser():
        return Mock(close=AsyncMock(), is_connected=lambda: True)

    async def test_fresh_instance_failure_retries_and_closes_every_instance(self):
        first, second = self.browser(), self.browser()
        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(side_effect=[(first, False), (second, False)]),
            ),
            patch.object(
                self.analyzer,
                "_perform_screenshot",
                new=AsyncMock(side_effect=BrowserError("failed")),
            ),
        ):
            with self.assertRaises(analyzer_module.ScreenshotError):
                await self.analyzer.capture_screenshot("https://example.test")
        first.close.assert_awaited_once()
        second.close.assert_awaited_once()
        self.assertEqual(WebAnalyzer._browser_pool, [])

    async def test_page_failures_are_not_retried_on_another_instance(self):
        errors = (
            CdpNavigationError("Navigation failed: net::ERR_NAME_NOT_RESOLVED"),
            PageLimitError("Screenshot exceeds 10,000,000 pixel limit"),
            KeyError("targetId"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                browser = self.browser()
                acquire = AsyncMock(return_value=(browser, False))
                with (
                    patch.object(
                        self.analyzer, "_ensure_browser_detected", new=AsyncMock()
                    ),
                    patch.object(
                        self.analyzer, "_cleanup_browser_pool", new=AsyncMock()
                    ),
                    patch.object(self.analyzer, "_get_or_create_browser", acquire),
                    patch.object(
                        self.analyzer,
                        "_perform_screenshot",
                        new=AsyncMock(side_effect=error),
                    ),
                ):
                    with self.assertRaises(analyzer_module.ScreenshotError):
                        await self.analyzer.capture_screenshot("https://example.test")
                acquire.assert_awaited_once()
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
                new=AsyncMock(side_effect=[(first, True), (second, False)]),
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

    async def test_retry_count_is_configurable(self):
        for retries, expected in ((0, 1), (2, 3)):
            with self.subTest(retries=retries):
                analyzer = WebAnalyzer(
                    enable_memory_monitor=False, screenshot_retry_count=retries
                )
                browser = self.browser()
                acquire = AsyncMock(return_value=(browser, False))
                with (
                    patch.object(analyzer, "_ensure_browser_detected", new=AsyncMock()),
                    patch.object(analyzer, "_cleanup_browser_pool", new=AsyncMock()),
                    patch.object(analyzer, "_get_or_create_browser", acquire),
                    patch.object(
                        analyzer,
                        "_perform_screenshot",
                        new=AsyncMock(side_effect=BrowserError("failed")),
                    ),
                ):
                    with self.assertRaises(analyzer_module.ScreenshotError):
                        await analyzer.capture_screenshot("https://example.test")
                self.assertEqual(acquire.await_count, expected)
                self.assertEqual(browser.close.await_count, expected)
        await self.analyzer.apply_runtime_config({"screenshot_retry_count": 0})
        self.assertEqual(self.analyzer.screenshot_retry_count, 0)

    async def test_screenshot_survives_a_cleanup_failure(self):
        browser = self.browser()
        with (
            patch.object(self.analyzer, "_ensure_browser_detected", new=AsyncMock()),
            patch.object(self.analyzer, "_cleanup_browser_pool", new=AsyncMock()),
            patch.object(
                self.analyzer,
                "_get_or_create_browser",
                new=AsyncMock(return_value=(browser, True)),
            ),
            patch.object(
                self.analyzer,
                "_perform_screenshot",
                new=AsyncMock(return_value=b"image"),
            ),
            patch.object(
                self.analyzer,
                "_recycle_browser",
                new=AsyncMock(side_effect=RuntimeError("close exploded")),
            ),
        ):
            result = await self.analyzer.capture_screenshot("https://example.test")
        self.assertEqual(result, b"image")

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


class FakeBrowserTests(unittest.IsolatedAsyncioTestCase):
    """Drive the browser pool with a stand-in instead of a system browser."""

    # A real file, so that the cached detection result stays valid.
    executable = str(Path(__file__).resolve())

    def setUp(self):
        reset_browser_state()
        FakeBrowser.created.clear()
        FakeBrowser.launch_error = None

        def detect(exclude_paths=None):
            # Like the real detector, a rejected executable is no longer found.
            if exclude_paths:
                return False, "", "", ""
            return True, self.executable, "Fake", "1"

        self.detect = self.enterContext(
            patch.object(analyzer_module, "detect_system_browser", side_effect=detect)
        )
        self.enterContext(
            patch.object(analyzer_module, "BrowserInstance", new=FakeBrowser)
        )
        self.enterContext(
            patch.object(
                analyzer_module, "sweep_stale_browser_artifacts", new=AsyncMock()
            )
        )
        self.analyzer = WebAnalyzer(enable_memory_monitor=False)

    async def acquire(self):
        return await self.analyzer._get_or_create_browser()

    async def test_concurrent_first_requests_share_one_detection(self):
        gate = threading.Event()

        def detect(exclude_paths=None):
            gate.wait(5)
            return True, self.executable, "Fake", "1"

        self.detect.side_effect = detect
        requests = [asyncio.create_task(self.acquire()) for _ in range(3)]
        await asyncio.sleep(0.02)
        gate.set()
        acquired = await asyncio.wait_for(asyncio.gather(*requests), 5)
        self.assertEqual(self.detect.call_count, 1)
        self.assertEqual(len({id(instance) for instance, _ in acquired}), 3)

    async def test_missing_browser_keeps_the_install_hint(self):
        self.detect.side_effect = None
        self.detect.return_value = (False, "", "", "")
        with self.assertRaises(analyzer_module.ScreenshotError) as caught:
            await self.acquire()
        self.assertTrue(str(caught.exception).startswith("未检测到系统已安装的浏览器"))

    async def test_status_reuses_the_shared_detection(self):
        status = await self.analyzer.get_browser_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["install_path"], self.executable)
        self.assertEqual(self.detect.call_count, 1)

    async def test_transient_launch_failure_is_reported_without_blacklisting(self):
        FakeBrowser.launch_error = BrowserLaunchError(
            "Timed out waiting for the browser debugging endpoint"
        )
        with self.assertRaises(BrowserLaunchError):
            await self.acquire()
        self.assertEqual(WebAnalyzer._browser_blacklist, {})
        self.assertEqual(WebAnalyzer._browser_instances, set())
        self.assertEqual(WebAnalyzer._detected_browser_path, self.executable)

        # The next request simply tries the same executable again.
        FakeBrowser.launch_error = None
        instance, pooled = await self.acquire()
        self.assertFalse(instance.closed)
        self.assertFalse(pooled)

    async def test_unrunnable_browser_is_skipped_together_with_its_reason(self):
        FakeBrowser.launch_error = BrowserExecutableError(
            "Browser exited with code 1: No usable sandbox"
        )
        with self.assertRaises(analyzer_module.ScreenshotError) as caught:
            await self.acquire()
        message = str(caught.exception)
        self.assertIn(
            f"{self.executable}: Browser exited with code 1: No usable sandbox",
            message,
        )
        self.assertIn("自动重试", message)
        self.assertEqual(self.detect.call_count, 2)
        self.assertEqual(WebAnalyzer._browser_instances, set())
        self.assertEqual(FakeBrowser.created[0].closed, True)

    async def test_skipped_browser_is_tried_again_after_the_cooldown(self):
        FakeBrowser.launch_error = BrowserExecutableError(
            "Browser exited with code 127"
        )
        with self.assertRaises(analyzer_module.ScreenshotError) as caught:
            await self.acquire()
        self.assertIn(
            f"{self.executable}: Browser exited with code 127", str(caught.exception)
        )

        # During the cooldown it is neither detected nor launched again.
        with self.assertRaises(analyzer_module.ScreenshotError):
            await self.acquire()
        self.assertEqual(self.detect.call_count, 3)
        self.detect.assert_called_with(exclude_paths={self.executable})
        self.assertEqual(len(FakeBrowser.created), 1)

        # An expired entry is dropped, so the next request tries it again.
        reason = WebAnalyzer._browser_blacklist[self.executable][1]
        WebAnalyzer._browser_blacklist[self.executable] = (
            time.monotonic() - 1,
            reason,
        )
        FakeBrowser.launch_error = None
        instance, _ = await self.acquire()
        self.assertFalse(instance.closed)
        self.detect.assert_called_with(exclude_paths=set())
        self.assertEqual(WebAnalyzer._browser_blacklist, {})

    async def test_changing_launch_settings_forgets_launch_failures(self):
        FakeBrowser.launch_error = BrowserExecutableError("Browser exited with code 1")
        with self.assertRaises(analyzer_module.ScreenshotError):
            await self.acquire()
        await self.analyzer.apply_runtime_config({"max_content_length": 5000})
        self.assertIn(self.executable, WebAnalyzer._browser_blacklist)

        await self.analyzer.apply_runtime_config({"sandbox_mode": "always_disabled"})
        self.assertEqual(WebAnalyzer._browser_blacklist, {})
        self.assertEqual(WebAnalyzer._detected_browser_path, "")

    async def test_reload_resets_the_browser_session(self):
        FakeBrowser.launch_error = BrowserExecutableError("Browser exited with code 1")
        with self.assertRaises(analyzer_module.ScreenshotError):
            await self.acquire()
        WebAnalyzer._shutting_down = True
        WebAnalyzer.reset_browser_session()
        self.assertFalse(WebAnalyzer._shutting_down)
        self.assertEqual(WebAnalyzer._browser_blacklist, {})

    async def test_cancel_before_registration_leaves_no_slot_leak(self):
        sweep_started = asyncio.Event()
        release_sweep = asyncio.Event()

        async def slow_sweep():
            sweep_started.set()
            await release_sweep.wait()

        # 每小时一次的残留清理是登记名额前的最后一个可取消点
        WebAnalyzer._last_profile_sweep = 0
        with patch.object(
            analyzer_module, "sweep_stale_browser_artifacts", new=slow_sweep
        ):
            task = asyncio.create_task(self.acquire())
            await sweep_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(FakeBrowser.created, [])
        self.assertEqual(WebAnalyzer._browser_instances, set())

        # 名额未被占用，后续请求正常启动实例
        release_sweep.set()
        WebAnalyzer._last_profile_sweep = time.time()
        instance, pooled = await asyncio.wait_for(self.acquire(), 5)
        self.assertFalse(pooled)
        self.assertEqual(len(FakeBrowser.created), 1)

    async def test_cancel_while_closing_dead_instances_registers_nothing(self):
        dead = FakeBrowser(self.executable)
        dead.closed = True  # 断开连接，被视为失效实例
        closing = asyncio.Event()

        async def hang_close():
            closing.set()
            await asyncio.Event().wait()

        dead.close = hang_close
        WebAnalyzer._browser_pool.append(dead)
        WebAnalyzer._browser_last_used[id(dead)] = time.time()
        task = asyncio.create_task(self.acquire())
        await closing.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(FakeBrowser.created), 1)
        self.assertEqual(WebAnalyzer._browser_instances, set())

        # 关闭被中断的失效实例不阻塞后续请求
        dead.close = AsyncMock()
        instance, _ = await asyncio.wait_for(self.acquire(), 5)
        self.assertEqual(len(FakeBrowser.created), 2)
        self.assertIsNot(instance, dead)

    async def test_requests_at_the_cap_wait_and_reuse_returned_instances(self):
        self.analyzer = WebAnalyzer(
            enable_memory_monitor=False, max_browser_instances=2
        )
        requests = [asyncio.create_task(self.acquire()) for _ in range(4)]
        await eventually(lambda: sum(task.done() for task in requests) >= 2)
        finished = [task for task in requests if task.done()]
        self.assertEqual(len(finished), 2)
        self.assertEqual(len(FakeBrowser.created), 2)
        first, _ = finished[0].result()
        second, _ = finished[1].result()
        self.assertLessEqual(len(WebAnalyzer._browser_instances), 2)

        # Returning an instance serves exactly one of the two waiting requests.
        await self.analyzer._recycle_browser(first)
        waiting = [task for task in requests if task not in finished]
        await eventually(lambda: any(task.done() for task in waiting))
        done = [task for task in waiting if task.done()]
        self.assertEqual(len(done), 1)
        reused, pooled = done[0].result()
        self.assertIs(reused, first)
        self.assertTrue(pooled)
        self.assertEqual(len(FakeBrowser.created), 2)

        # Closing the other instance frees a slot for the last request.
        await self.analyzer._close_browsers([second])
        last, pooled = await asyncio.wait_for(
            next(task for task in waiting if task not in done), 5
        )
        self.assertFalse(pooled)
        self.assertIsNot(last, first)
        self.assertEqual(len(FakeBrowser.created), 3)
        self.assertLessEqual(len(WebAnalyzer._browser_instances), 2)

    async def test_waiting_request_fails_with_a_busy_error_at_the_deadline(self):
        self.analyzer = WebAnalyzer(
            enable_memory_monitor=False, max_browser_instances=1
        )
        self.analyzer.timeout = 0.05
        acquired, _ = await self.acquire()
        with self.assertRaises(analyzer_module.ScreenshotError) as caught:
            await self.acquire()
        self.assertIn("上限", str(caught.exception))
        # The request holding the instance is not affected.
        self.assertIn(acquired, WebAnalyzer._browser_instances)
        self.assertFalse(acquired.closed)

    async def test_shutdown_releases_waiting_requests(self):
        self.analyzer = WebAnalyzer(
            enable_memory_monitor=False, max_browser_instances=1
        )
        acquired, _ = await self.acquire()
        waiting = asyncio.create_task(self.acquire())
        await asyncio.sleep(0.02)
        WebAnalyzer._shutting_down = True
        await acquired.close()  # what terminate() does with every instance
        with self.assertRaises(RuntimeError):
            await waiting

    async def test_lowering_the_cap_closes_surplus_idle_instances(self):
        held = await asyncio.gather(*(self.acquire() for _ in range(3)))
        for instance, _ in held:
            await self.analyzer._recycle_browser(instance)
        self.assertEqual(len(WebAnalyzer._browser_pool), 3)
        await self.analyzer.apply_runtime_config({"max_browser_instances": 1})
        self.assertEqual(WebAnalyzer._max_browser_instances, 1)
        self.assertEqual(len(WebAnalyzer._browser_pool), 1)
        self.assertEqual(sum(instance.closed for instance in FakeBrowser.created), 2)
        self.assertEqual(len(WebAnalyzer._browser_instances), 1)

    async def test_raising_the_cap_lets_a_waiting_request_start_an_instance(self):
        self.analyzer = WebAnalyzer(
            enable_memory_monitor=False, max_browser_instances=1
        )
        acquired, _ = await self.acquire()
        waiting = asyncio.create_task(self.acquire())
        await asyncio.sleep(0.02)
        self.assertFalse(waiting.done())
        await self.analyzer.apply_runtime_config({"max_browser_instances": 2})
        instance, pooled = await asyncio.wait_for(waiting, 5)
        self.assertFalse(pooled)
        self.assertIsNot(instance, acquired)

    async def test_instance_limit_values_are_normalized(self):
        # The loader bounds the setting; the analyzer still never trusts it.
        cases = ((0, 1), (-3, 1), ("many", 3), (None, 3), ("2", 2), (8, 8))
        for value, expected in cases:
            with self.subTest(value=value):
                WebAnalyzer._set_browser_instance_limit(value)
                self.assertEqual(WebAnalyzer._max_browser_instances, expected)


if __name__ == "__main__":
    unittest.main()
