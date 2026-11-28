"""Capture pipeline tests: URL filtering, concurrency, caching and results."""

import asyncio
import tempfile
import unittest

from test_support import (
    CapturePipeline,
    CaptureSettings,
    ScreenshotCache,
    ScreenshotService,
)

PARAMS = {
    "width": 800,
    "height": 600,
    "full_page": False,
    "format": "jpeg",
    "quality": 80,
    "wait_strategy": "fixed",
    "wait_time": 100,
}


class FakeScreenshotService(ScreenshotService):
    """Records captures without launching any browser."""

    def __init__(self):
        # Skip the real constructor: no locks or monitors are needed here.
        self.timeout = 30
        self.screenshot_retry_count = 0
        self.capture_log = []
        self.inflight = 0
        self.max_observed_inflight = 0
        self._png = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # magic header + filler

    async def capture(self, url, **kwargs):
        self.capture_log.append((url, kwargs))
        self.inflight += 1
        self.max_observed_inflight = max(self.max_observed_inflight, self.inflight)
        try:
            await asyncio.sleep(0.02)
            return self._png, f"title-{url}", url
        finally:
            self.inflight -= 1


def make_pipeline(max_concurrency=2, cache=True):
    service = FakeScreenshotService()
    cache_dir = tempfile.mkdtemp(prefix="wa_pipeline_test_")
    screenshot_cache = ScreenshotCache(cache_dir=cache_dir, enabled=cache)
    pipeline = CapturePipeline(
        service, screenshot_cache, max_concurrency=max_concurrency
    )
    return pipeline, service, screenshot_cache


class FilterUrlsTests(unittest.TestCase):
    def test_invalid_and_blocked_urls_are_filtered(self):
        pipeline, _, _ = make_pipeline()
        urls = pipeline.filter_urls(
            [
                "https://ok.example/",
                "http://127.0.0.1/secret",
                "https://blocked.example/",
                "not a url",
            ],
            [],
            ["blocked.example"],
        )
        self.assertEqual(urls, ["https://ok.example"])

    def test_allow_local_keeps_loopback(self):
        pipeline, _, _ = make_pipeline()
        urls = pipeline.filter_urls(
            ["http://127.0.0.1:6185/", "http://localhost:8000/app"],
            [],
            [],
            allow_local=True,
        )
        self.assertEqual(urls, ["http://127.0.0.1:6185", "http://localhost:8000/app"])

    def test_duplicates_and_www_variants_collapse(self):
        pipeline, _, _ = make_pipeline()
        urls = pipeline.filter_urls(
            [
                "https://example.com/a",
                "https://example.com/a/",
                "https://www.example.com/a",
            ],
            [],
            [],
            unify_www=True,
        )
        self.assertEqual(len(urls), 1)

    def test_allow_list_restricts(self):
        pipeline, _, _ = make_pipeline()
        urls = pipeline.filter_urls(["https://a.com/", "https://b.com/"], ["a.com"], [])
        self.assertEqual(urls, ["https://a.com"])


class CaptureBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_returns_results_in_input_order(self):
        pipeline, service, _ = make_pipeline()
        settings = CaptureSettings(**PARAMS)
        outcomes = await pipeline.capture_batch(
            ["https://a.example/", "https://b.example/"], settings
        )
        self.assertEqual(
            [outcome.url for outcome in outcomes],
            ["https://a.example/", "https://b.example/"],
        )
        self.assertTrue(all(outcome.ok for outcome in outcomes))
        self.assertTrue(all(outcome.screenshot for outcome in outcomes))
        self.assertEqual(service.capture_log[0][1]["width"], 800)

    async def test_concurrency_limit_is_respected(self):
        pipeline, service, _ = make_pipeline(max_concurrency=2)
        settings = CaptureSettings(**PARAMS)
        await pipeline.capture_batch(
            [f"https://{i}.example/" for i in range(6)], settings
        )
        self.assertLessEqual(service.max_observed_inflight, 2)

    async def test_second_batch_hits_cache_and_skips_capture(self):
        pipeline, service, _ = make_pipeline()
        settings = CaptureSettings(**PARAMS)
        url = "https://cached.example/"
        first = await pipeline.capture_batch([url], settings)
        count_after_first = len(service.capture_log)
        second = await pipeline.capture_batch([url], settings)
        self.assertEqual(len(service.capture_log), count_after_first)
        self.assertTrue(second[0].cached)
        self.assertFalse(first[0].cached)
        self.assertEqual(first[0].screenshot, second[0].screenshot)

    async def test_param_change_misses_cache(self):
        pipeline, service, _ = make_pipeline()
        url = "https://param.example/"
        await pipeline.capture_batch([url], CaptureSettings(**PARAMS))
        await pipeline.capture_batch(
            [url], CaptureSettings(**{**PARAMS, "full_page": True})
        )
        self.assertEqual(len(service.capture_log), 2)

    async def test_capture_failure_is_reported_not_raised(self):
        pipeline, _, _ = make_pipeline()

        async def boom(url, **kwargs):
            raise RuntimeError("browser exploded")

        pipeline.screenshot_service.capture = boom
        settings = CaptureSettings(**PARAMS)
        outcome = await pipeline.capture_one("https://fail.example/", settings)
        self.assertFalse(outcome.ok)
        self.assertIn("失败", outcome.error)


class CropTests(unittest.IsolatedAsyncioTestCase):
    async def test_crop_is_applied_when_enabled(self):
        import io

        from PIL import Image

        pipeline, _, _ = make_pipeline()
        service = pipeline.screenshot_service

        # 生成一张真实图片供裁剪
        image = Image.new("RGB", (100, 100), (255, 0, 0))
        import io as _io

        buf = _io.BytesIO()
        image.save(buf, format="PNG")
        png = buf.getvalue()
        service._png = png

        settings = CaptureSettings(
            **{
                **PARAMS,
                "format": "png",
                "enable_crop": True,
                "crop_area": (0, 0, 50, 50),
            }
        )
        outcome = await pipeline.capture_one("https://crop.example/", settings)
        self.assertTrue(outcome.ok)
        size = Image.open(io.BytesIO(outcome.screenshot)).size
        self.assertEqual(size, (50, 50))

    async def test_cache_stores_cropped_result(self):
        import io

        from PIL import Image

        pipeline, _, cache = make_pipeline()
        service = pipeline.screenshot_service
        image = Image.new("RGB", (80, 80), (0, 255, 0))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        service._png = buf.getvalue()

        settings = CaptureSettings(
            **{
                **PARAMS,
                "format": "png",
                "enable_crop": True,
                "crop_area": (0, 0, 40, 40),
            }
        )
        await pipeline.capture_one("https://crop2.example/", settings)
        cached_entries = cache.list_entries()
        self.assertEqual(len(cached_entries), 1)
        screenshot = cache.get_screenshot(cached_entries[0]["id"])
        self.assertEqual(Image.open(io.BytesIO(screenshot)).size, (40, 40))


if __name__ == "__main__":
    unittest.main()
