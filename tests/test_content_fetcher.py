"""Content fetcher tests: readable extraction, redirect checks and limits."""

import unittest
from unittest.mock import patch

import httpx
from test_support import ContentFetcher, FetchError, content_fetcher_module

HTML_FULL = """
<html><head><title>页面标题</title>
<meta property="og:title" content="OG 标题"></head>
<body>
<nav>菜单</nav>
<script>alert(1)</script>
<article><p>第一段正文。</p><p>第二段正文。</p></article>
<footer>页脚</footer>
</body></html>
"""


class ReadableExtractionTests(unittest.TestCase):
    def test_extracts_title_and_article_text(self):
        fetcher = ContentFetcher()
        title, content, truncated = fetcher._extract_readable(HTML_FULL)
        self.assertFalse(truncated)
        self.assertEqual(title, "页面标题")
        self.assertIn("第一段正文。", content)
        self.assertIn("第二段正文。", content)
        self.assertNotIn("菜单", content)
        self.assertNotIn("页脚", content)
        self.assertNotIn("alert", content)

    def test_falls_back_to_body_when_no_article(self):
        fetcher = ContentFetcher()
        title, content, _truncated = fetcher._extract_readable(
            "<html><head><title>T</title></head><body><p>正文内容</p></body></html>"
        )
        self.assertEqual(title, "T")
        self.assertIn("正文内容", content)

    def test_truncates_to_max_content_length(self):
        fetcher = ContentFetcher(max_content_length=10)
        _, content, truncated = fetcher._extract_readable(
            "<body><article>" + "字" * 100 + "</article></body>"
        )
        self.assertEqual(len(content), 10)
        self.assertTrue(truncated)

    def test_bad_html_raises_fetch_error(self):
        fetcher = ContentFetcher()
        with self.assertRaises(FetchError):
            fetcher._extract_readable(12345)

    def test_tool_result_formatting(self):
        result = content_fetcher_module.ContentResult(
            url="https://a.com/",
            final_url="https://b.com/final",
            title="标题",
            content="正文内容",
            truncated=True,
        )
        text = ContentFetcher.format_tool_result(result, max_chars=1000)
        self.assertIn("最终URL: https://b.com/final", text)
        self.assertIn("标题: 标题", text)
        self.assertIn("截断", text)
        self.assertIn("正文内容", text)


class FetchValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_url_is_rejected_before_any_request(self):
        fetcher = ContentFetcher()
        with self.assertRaises(FetchError):
            await fetcher.fetch("http://127.0.0.1/secret")
        with self.assertRaises(FetchError):
            await fetcher.fetch("http://localhost:6185/")

    async def test_allow_local_permits_loopback(self):
        fetcher = ContentFetcher(allow_local=True)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text="<html><head><title>本机</title></head><body><p>dashboard</p></body></html>",
            )

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            result = await fetcher._fetch_with_httpx("http://127.0.0.1:6185/")
        self.assertEqual(result.title, "本机")
        self.assertIn("dashboard", result.content)

    async def test_redirects_are_validated_each_hop(self):
        fetcher = ContentFetcher()
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if str(request.url).startswith("https://start.example/"):
                return httpx.Response(
                    302, headers={"Location": "http://127.0.0.1/evil"}
                )
            return httpx.Response(200, text="<html><body><p>x</p></body></html>")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            with self.assertRaises(FetchError) as caught:
                await fetcher._fetch_with_httpx("https://start.example/page")
        self.assertIn("不允许访问", str(caught.exception))

    async def test_successful_fetch_returns_final_url_title_and_content(self):
        fetcher = ContentFetcher()

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith("https://start.example/"):
                return httpx.Response(
                    301, headers={"Location": "https://final.example/done"}
                )
            return httpx.Response(200, text=HTML_FULL)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            result = await fetcher._fetch_with_httpx("https://start.example/page")
        self.assertEqual(result.url, "https://start.example/page")
        self.assertEqual(result.final_url, "https://final.example/done")
        self.assertEqual(result.title, "页面标题")
        self.assertIn("第一段正文。", result.content)

    async def test_error_status_raises(self):
        fetcher = ContentFetcher()
        transport = httpx.MockTransport(lambda request: httpx.Response(403, text="no"))
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            with self.assertRaises(FetchError) as caught:
                await fetcher._fetch_with_httpx("https://deny.example/")
        self.assertIn("403", str(caught.exception))

    async def test_redirect_cap_is_enforced(self):
        fetcher = ContentFetcher()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302, headers={"Location": "https://loop.example/next"}
            )

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            with self.assertRaises(FetchError) as caught:
                await fetcher._fetch_with_httpx("https://loop.example/start")
        self.assertIn("跳转次数", str(caught.exception))

    async def test_empty_content_raises(self):
        fetcher = ContentFetcher()
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html><body></body></html>")
        )
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        with (
            patch.object(ContentFetcher, "_shared_client", client),
            patch.object(ContentFetcher, "_shared_client_params", ("",)),
        ):
            with self.assertRaises(FetchError):
                await fetcher._fetch_with_httpx("https://empty.example/")


class SharedClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_recreated_when_proxy_changes(self):
        fetcher = ContentFetcher(proxy="")
        client_a = fetcher._get_client()
        fetcher.proxy = "http://127.0.0.1:7890"
        client_b = fetcher._get_client()
        self.assertIsNot(client_a, client_b)
        await fetcher.close()
        self.assertIsNone(ContentFetcher._shared_client)

    async def test_close_shuts_down_shared_client(self):
        fetcher = ContentFetcher()
        fetcher._get_client()
        await fetcher.close()
        self.assertIsNone(ContentFetcher._shared_client)


if __name__ == "__main__":
    unittest.main()
