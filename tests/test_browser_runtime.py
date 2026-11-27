"""Opt-in local browser integration tests; no public sites are contacted."""

import asyncio
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from test_browser import (
    BrowserInstance,
    WebAnalyzer,
    browser_module,
    reset_browser_state,
)


@unittest.skipUnless(
    os.environ.get("WEB_ANALYZER_BROWSER_TESTS") == "1",
    "Set WEB_ANALYZER_BROWSER_TESTS=1 to launch a system browser",
)
class BrowserRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        found, self.path, _, _ = await asyncio.to_thread(
            browser_module.detect_system_browser
        )
        if not found:
            self.skipTest("No system browser installed")
        reset_browser_state()

    async def asyncTearDown(self):
        instances = set(WebAnalyzer._browser_instances) | set(WebAnalyzer._browser_pool)
        for instance in instances:
            await instance.close()
        WebAnalyzer._browser_instances.clear()
        WebAnalyzer._browser_pool.clear()
        WebAnalyzer._browser_last_used.clear()

    @staticmethod
    def local_page(temp, body="<body>page"):
        page_file = Path(temp) / "page.html"
        page_file.write_text(
            f"<!doctype html><meta charset='utf-8'>{body}", encoding="utf-8"
        )
        return page_file.as_uri()

    async def test_screenshot_follows_redirect_before_dom_is_ready(self):
        arrived = asyncio.Event()
        user_agents = []

        async def serve(reader, writer):
            try:
                headers = await reader.readuntil(b"\r\n\r\n")
                path = headers.split(b" ", 2)[1]
                if path == b"/start":
                    user_agents.extend(
                        line.split(b":", 1)[1].strip()
                        for line in headers.split(b"\r\n")
                        if line.lower().startswith(b"user-agent:")
                    )
                    body = b"<html><script>location.replace('/final')</script>"
                    # Leave the original document incomplete while JS redirects.
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        b"Content-Length: 50000\r\n\r\n" + body
                    )
                    await writer.drain()
                    await asyncio.wait_for(arrived.wait(), 5)
                elif path == b"/final":
                    arrived.set()
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        b"Connection: close\r\n\r\n<body style='background:#00ff00'>"
                    )
                    await writer.drain()
            except (OSError, TimeoutError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            analyzer = WebAnalyzer(enable_memory_monitor=False, timeout=3)
            overrides = (
                "",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "WebAnalyzer-Test/1.0",
            )
            for override in overrides:
                arrived.clear()
                await analyzer.apply_runtime_config({"user_agent": override})
                data = await analyzer.capture_screenshot(
                    f"http://127.0.0.1:{port}/start", format="png", wait_time=0
                )
                with Image.open(io.BytesIO(data)) as image:
                    self.assertEqual(
                        image.convert("RGB").getpixel((80, 80)), (0, 255, 0)
                    )
        self.assertIn(b"Chrome/", user_agents[0])
        self.assertEqual(user_agents[1:], [ua.encode() for ua in overrides[1:]])

    async def test_interrupted_document_reports_network_error(self):
        async def serve(reader, writer):
            try:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                    b"Content-Length: 50000\r\n\r\n<html><body>partial"
                )
                await writer.drain()
            except (OSError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        browser = BrowserInstance(self.path)
        async with server:
            port = server.sockets[0].getsockname()[1]
            try:
                await browser.start()
                page = await browser.new_page()
                with self.assertRaisesRegex(
                    browser_module.CdpNavigationError,
                    "net::ERR_CONTENT_LENGTH_MISMATCH",
                ):
                    await page.goto(f"http://127.0.0.1:{port}/truncated", timeout=3000)
            finally:
                await browser.close()

    async def test_render_capture_reuse_concurrency_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            page_file = Path(temp) / "动态 页面.html"
            page_file.write_text(
                """<!doctype html><meta charset='utf-8'>
            <style>body {height:2500px}</style><div id='result'>pending</div>
            <script>setTimeout(() => document.getElementById('result').textContent = 'rendered-1023', 100)</script>""",
                encoding="utf-8",
            )
            url = page_file.as_uri()
            analyzer = WebAnalyzer(fetch_mode="playwright", enable_memory_monitor=False)
            async with analyzer:
                html = await analyzer.fetch_webpage(url)
                self.assertIn("rendered-1023", html)
                first = list(WebAnalyzer._browser_pool)
                self.assertEqual(len(first), 1)
                screenshot = await analyzer.capture_screenshot(
                    url, width=1024, height=768, wait_time=200
                )
                self.assertEqual(Image.open(io.BytesIO(screenshot)).size, (1024, 768))
                self.assertIs(WebAnalyzer._browser_pool[0], first[0])
                full = await analyzer.capture_screenshot(
                    url,
                    width=1024,
                    height=768,
                    format="png",
                    full_page=True,
                    wait_time=200,
                )
                image = Image.open(io.BytesIO(full))
                self.assertEqual(image.width, 1024)
                self.assertGreaterEqual(image.height, 2500)

                async def concurrent_capture(width):
                    async with analyzer:
                        data = await analyzer.capture_screenshot(
                            url, width=width, height=600, wait_time=100
                        )
                        return Image.open(io.BytesIO(data)).size

                sizes = await asyncio.gather(
                    *(concurrent_capture(w) for w in (800, 900, 1000))
                )
                self.assertEqual(sizes, [(800, 600), (900, 600), (1000, 600)])
                pool = WebAnalyzer._browser_pool
                self.assertEqual(len(pool), len(set(pool)))
                self.assertLessEqual(len(pool), WebAnalyzer._max_idle_browsers)
                self.assertLessEqual(
                    len(WebAnalyzer._browser_instances),
                    WebAnalyzer._max_browser_instances,
                )
                self.assertTrue(all(instance.page_count == 0 for instance in pool))
            self.assertIsNone(analyzer.client)
            instances = list(WebAnalyzer._browser_instances)
            profiles = [instance.profile_dir for instance in instances]
            for instance in instances:
                await instance.close()
                self.assertFalse(instance.is_connected())
                self.assertIsNotNone(instance._process.poll())
            self.assertTrue(all(not Path(profile).exists() for profile in profiles))

    async def test_concurrent_captures_never_exceed_the_instance_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            url = self.local_page(temp)
            analyzer = WebAnalyzer(enable_memory_monitor=False, max_browser_instances=2)
            started = []
            start = analyzer._start_browser

            async def tracked(instance):
                started.append(await start(instance))
                return started[-1]

            analyzer._start_browser = tracked
            sizes = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        analyzer.capture_screenshot(
                            url, width=width, height=600, wait_time=300
                        )
                        for width in (800, 900, 1000, 1100)
                    )
                ),
                90,
            )
            self.assertEqual(
                [Image.open(io.BytesIO(data)).size for data in sizes],
                [(800, 600), (900, 600), (1000, 600), (1100, 600)],
            )
            # Two browser processes were started; the other requests reused them.
            self.assertEqual(len(started), 2)
            self.assertLessEqual(len(WebAnalyzer._browser_instances), 2)

    async def test_instance_failure_is_retried_on_another_browser(self):
        with tempfile.TemporaryDirectory() as temp:
            url = self.local_page(temp)
            analyzer = WebAnalyzer(enable_memory_monitor=False)
            perform = analyzer._perform_screenshot
            used = []

            async def flaky(browser, **kwargs):
                used.append(browser)
                if len(used) == 1:
                    # What a lost DevTools connection looks like to the caller.
                    await browser.close()
                    raise browser_module.BrowserError(
                        "Browser DevTools connection disconnected"
                    )
                return await perform(browser=browser, **kwargs)

            analyzer._perform_screenshot = flaky
            screenshot = await asyncio.wait_for(
                analyzer.capture_screenshot(url, width=800, height=600, wait_time=100),
                90,
            )
            self.assertEqual(Image.open(io.BytesIO(screenshot)).size, (800, 600))
            self.assertEqual(len(used), 2)
            self.assertIsNot(used[0], used[1])
            # The failed instance is gone and only the healthy one stays pooled.
            self.assertFalse(used[0].is_connected())
            self.assertEqual(WebAnalyzer._browser_pool, [used[1]])

    async def test_tabs_have_isolated_cookies(self):
        browser = BrowserInstance(self.path)
        try:
            await browser.start()
            first = await browser.new_page()
            await first._send(
                "Network.setCookie",
                {
                    "name": "private-test",
                    "value": "one",
                    "url": "https://cookie-test.invalid/",
                },
            )
            second = await browser.new_page()
            cookies = await second._send(
                "Network.getCookies", {"urls": ["https://cookie-test.invalid/"]}
            )
            self.assertEqual(cookies["cookies"], [])
            await first.close()
            await second.close()
        finally:
            await browser.close()

    async def test_authenticated_http_proxy(self):
        expected = "Basic " + base64.b64encode(b"test-user:test-password").decode()
        authorized = asyncio.Event()

        async def proxy(reader, writer):
            try:
                request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
                headers = request.decode("latin1").split("\r\n")
                auth = next(
                    (
                        line.split(":", 1)[1].strip()
                        for line in headers
                        if line.lower().startswith("proxy-authorization:")
                    ),
                    "",
                )
                if auth != expected:
                    writer.write(
                        b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="local-test"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                    )
                else:
                    body = b"<html><title>Proxy OK</title><body>proxy-auth-ok</body></html>"
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
                        + str(len(body)).encode()
                        + b"\r\nConnection: close\r\n\r\n"
                        + body
                    )
                    authorized.set()
                await writer.drain()
            except (OSError, TimeoutError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(proxy, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        analyzer = WebAnalyzer(
            hide_ip=True, proxy=f"http://test-user:test-password@127.0.0.1:{port}"
        )
        args = analyzer._build_browser_launch_args()
        browser = BrowserInstance(
            self.path,
            extra_args=args,
            proxy_credentials=analyzer._browser_proxy_credentials,
        )
        try:
            await browser.start()
            page = await browser.new_page()
            await page.goto("http://proxy-test.invalid/", timeout=15000)
            self.assertIn("proxy-auth-ok", await page.content())
            self.assertTrue(authorized.is_set())
            await page.close()
        finally:
            await browser.close()
            server.close()
            await server.wait_closed()
