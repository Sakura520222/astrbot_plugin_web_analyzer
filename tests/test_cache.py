"""Screenshot cache tests: key derivation, TTL, LRU and legacy visibility."""

import os
import tempfile
import time
import unittest

from test_support import ScreenshotCache, cache_module

build_cache_key = cache_module.build_cache_key


def make_cache(**kwargs):
    cache_dir = tempfile.mkdtemp(prefix="wa_cache_test_")
    defaults = {"cache_dir": cache_dir, "max_size": 3, "expire_minutes": 60}
    defaults.update(kwargs)
    return ScreenshotCache(**defaults)


PARAMS = {
    "width": 1280,
    "height": 720,
    "full_page": False,
    "format": "jpeg",
    "quality": 80,
    "wait_strategy": "fixed",
    "wait_time": 2000,
}


class CacheKeyTests(unittest.TestCase):
    def test_different_params_produce_different_keys(self):
        base = build_cache_key("https://example.com/", PARAMS)
        changed = dict(PARAMS, full_page=True)
        self.assertNotEqual(base, build_cache_key("https://example.com/", changed))

    def test_same_url_and_params_share_key(self):
        self.assertEqual(
            build_cache_key("https://example.com/", PARAMS),
            build_cache_key("https://example.com/", dict(PARAMS)),
        )

    def test_different_urls_differ(self):
        self.assertNotEqual(
            build_cache_key("https://a.com/", PARAMS),
            build_cache_key("https://b.com/", PARAMS),
        )


class CacheBehaviourTests(unittest.TestCase):
    def test_put_and_get_roundtrip_with_screenshot(self):
        cache = make_cache()
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {"title": "T"}, b"png-bytes")
        entry = cache.get(key)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["result"]["title"], "T")
        self.assertEqual(cache.get_screenshot(key), b"png-bytes")

    def test_disabled_cache_reads_and_writes_nothing(self):
        cache = make_cache(enabled=False)
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {"title": "T"}, b"x")
        self.assertIsNone(cache.get(key))

    def test_expiry_uses_minutes_to_seconds_once(self):
        cache = make_cache(expire_minutes=5)
        self.assertEqual(cache.expire_seconds, 300)
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {})
        entry = cache._entries[key]
        entry["timestamp"] = time.time() - 301
        self.assertIsNone(cache.get(key))
        # 过期条目已被删除
        self.assertNotIn(key, cache._entries)

    def test_lru_eviction_respects_max_size(self):
        cache = make_cache(max_size=2)
        for i in range(3):
            url = f"https://example.com/{i}"
            key = build_cache_key(url, PARAMS)
            cache.put(key, url, PARAMS, {})
            time.sleep(0.01)
        remaining = set(cache._entries)
        oldest = build_cache_key("https://example.com/0", PARAMS)
        self.assertNotIn(oldest, remaining)
        self.assertEqual(len(cache._entries), 2)

    def test_delete_removes_files(self):
        cache = make_cache()
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {}, b"bytes")
        self.assertTrue(os.path.exists(os.path.join(cache.cache_dir, f"{key}.json")))
        cache.delete(key)
        self.assertFalse(os.path.exists(os.path.join(cache.cache_dir, f"{key}.json")))
        self.assertFalse(
            os.path.exists(os.path.join(cache.cache_dir, f"{key}_screenshot.bin"))
        )

    def test_clear_removes_everything(self):
        cache = make_cache()
        for i in range(2):
            key = build_cache_key(f"https://e.com/{i}", PARAMS)
            cache.put(key, f"https://e.com/{i}", PARAMS, {}, b"b")
        cache.clear()
        self.assertEqual(os.listdir(cache.cache_dir), [])


class LegacyVisibilityTests(unittest.TestCase):
    def test_legacy_files_appear_in_listing(self):
        import hashlib
        import json

        cache = make_cache()
        # 旧版格式：sha256(url)[:32].json + 同名 _screenshot.bin
        legacy_url = "https://legacy.example/page"
        legacy_key = hashlib.sha256(legacy_url.encode()).hexdigest()[:32]
        entry = json.dumps(
            {
                "url": legacy_url,
                "timestamp": int(time.time()),
                "result": {"has_screenshot": True},
            }
        )
        with open(os.path.join(cache.cache_dir, f"{legacy_key}.json"), "w") as f:
            f.write(entry)
        with open(
            os.path.join(cache.cache_dir, f"{legacy_key}_screenshot.bin"), "wb"
        ) as f:
            f.write(b"legacy-image")

        items = cache.list_entries()
        legacy_items = [item for item in items if item["legacy"]]
        self.assertEqual(len(legacy_items), 1)
        self.assertEqual(legacy_items[0]["url"], legacy_url)
        self.assertTrue(legacy_items[0]["has_screenshot"])

        # 新旧条目可同屏搜索
        cache.put(
            build_cache_key("https://new.example/", PARAMS),
            "https://new.example/",
            PARAMS,
            {"title": "new"},
            b"img",
        )
        self.assertEqual(len(cache.list_entries("new.example")), 1)
        self.assertEqual(len(cache.list_entries("legacy.example")), 1)

    def test_preview_file_path(self):
        cache = make_cache()
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {}, b"img")
        self.assertEqual(
            cache.get_file_path(key),
            os.path.join(cache.cache_dir, f"{key}_screenshot.bin"),
        )
        self.assertIsNone(cache.get_file_path("nonexistent00"))


class StatsTests(unittest.TestCase):
    def test_stats_counts_valid_and_expired(self):
        cache = make_cache(expire_minutes=5)
        key = build_cache_key("https://example.com/", PARAMS)
        cache.put(key, "https://example.com/", PARAMS, {})
        cache._entries[key]["timestamp"] = time.time() - 1000
        stats = cache.get_stats()
        self.assertEqual(stats, {"total": 1, "valid": 0, "expired": 1})


if __name__ == "__main__":
    unittest.main()
