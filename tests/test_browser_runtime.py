"""Opt-in local browser integration tests; no public sites are contacted."""

import asyncio
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from test_browser import BrowserInstance, WebAnalyzer, browser_module


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
        WebAnalyzer._shutting_down = False
        WebAnalyzer._browser_lock = asyncio.Lock()
        WebAnalyzer._browser_pool = []
        WebAnalyzer._browser_instances = set()
        WebAnalyzer._browser_last_used = {}
        WebAnalyzer._browser_blacklist = set()

    async def asyncTearDown(self):
        instances = set(WebAnalyzer._browser_instances) | set(WebAnalyzer._browser_pool)
        for instance in instances:
            await instance.close()
        WebAnalyzer._browser_instances.clear()
        WebAnalyzer._browser_pool.clear()
        WebAnalyzer._browser_last_used.clear()

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
                self.assertLessEqual(len(pool), WebAnalyzer._max_browser_instances)
                self.assertTrue(all(instance.page_count == 0 for instance in pool))
            self.assertIsNone(analyzer.client)
            instances = list(WebAnalyzer._browser_instances)
            profiles = [instance.profile_dir for instance in instances]
            for instance in instances:
                await instance.close()
                self.assertFalse(instance.is_connected())
                self.assertIsNotNone(instance._process.poll())
            self.assertTrue(all(not Path(profile).exists() for profile in profiles))

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
