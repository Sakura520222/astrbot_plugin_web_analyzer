"""URL extraction, validation, normalization and domain rule tests."""

import unittest

from test_support import (
    extract_urls,
    is_domain_allowed,
    is_valid_url,
    normalize_url,
)


class ExtractUrlsTests(unittest.TestCase):
    def test_protocol_urls_are_found(self):
        text = "看这个 https://example.com/a?b=1 和 http://foo.cn/bar。"
        urls = extract_urls(text)
        self.assertIn("https://example.com/a?b=1", urls)
        self.assertTrue(any(u.startswith("http://foo.cn/bar") for u in urls))

    def test_no_protocol_urls_require_opt_in(self):
        text = "访问 www.example.com/page 试试"
        self.assertEqual(extract_urls(text), [])
        urls = extract_urls(text, enable_no_protocol=True, default_protocol="https")
        self.assertEqual(urls, ["https://www.example.com/page"])

    def test_no_protocol_honors_default_protocol(self):
        urls = extract_urls(
            "去 foo.cn", enable_no_protocol=True, default_protocol="http"
        )
        self.assertEqual(urls, ["http://foo.cn"])

    def test_cjk_text_does_not_extend_urls(self):
        urls = extract_urls("https://example.com/路径abc")
        self.assertEqual(urls, ["https://example.com/"])


class ValidUrlTests(unittest.TestCase):
    def test_rejects_non_http_schemes(self):
        for url in ("ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"):
            self.assertFalse(is_valid_url(url), url)

    def test_rejects_private_and_loopback_ips(self):
        for url in (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://169.254.1.1/",
            "http://[::1]/",
        ):
            self.assertFalse(is_valid_url(url), url)

    def test_rejects_localhost_hostname(self):
        self.assertFalse(is_valid_url("http://localhost:6185/"))
        self.assertFalse(is_valid_url("http://app.localhost/"))

    def test_allow_local_permits_loopback_and_private(self):
        for url in (
            "http://127.0.0.1:6185/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://localhost:6185/",
            "http://[::1]/",
        ):
            self.assertTrue(is_valid_url(url, allow_local=True), url)

    def test_allow_local_still_rejects_bad_schemes(self):
        self.assertFalse(is_valid_url("ftp://127.0.0.1/", allow_local=True))
        self.assertFalse(is_valid_url("not a url", allow_local=True))

    def test_accepts_public_urls(self):
        self.assertTrue(is_valid_url("https://example.com/x"))
        self.assertTrue(is_valid_url("http://8.8.8.8/"))


class NormalizeUrlTests(unittest.TestCase):
    def test_lowercases_scheme_and_host_and_strips_trailing_slash(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.COM/Path/"), "https://example.com/Path"
        )

    def test_unify_www_merges_apex_domains(self):
        self.assertEqual(
            normalize_url("https://example.com/a", unify_www=True),
            normalize_url("https://www.example.com/a", unify_www=True),
        )

    def test_unify_www_leaves_ips_and_www_hosts_alone(self):
        self.assertEqual(
            normalize_url("http://8.8.8.8/", unify_www=True), "http://8.8.8.8"
        )
        self.assertEqual(
            normalize_url("http://www.example.com/", unify_www=True),
            "http://www.example.com",
        )


class DomainRuleTests(unittest.TestCase):
    def test_blocked_list_wins(self):
        self.assertFalse(
            is_domain_allowed("https://ads.example.com/", [], ["example.com"])
        )

    def test_subdomain_suffix_match_for_blocked(self):
        self.assertFalse(is_domain_allowed("https://x.evil.com/", [], ["evil.com"]))
        self.assertTrue(is_domain_allowed("https://notevil.com/", [], ["evil.com"]))

    def test_allow_list_filters_others(self):
        self.assertTrue(is_domain_allowed("https://example.com/", ["example.com"], []))
        self.assertFalse(is_domain_allowed("https://other.com/", ["example.com"], []))

    def test_subdomain_matches_allow_list(self):
        self.assertTrue(
            is_domain_allowed("https://sub.example.com/", ["example.com"], [])
        )

    def test_empty_allow_list_allows_everything_unblocked(self):
        self.assertTrue(is_domain_allowed("https://anything.com/", [], []))


if __name__ == "__main__":
    unittest.main()
