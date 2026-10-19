"""Comprehensive unit tests for dynamic browser fingerprints, stealth headers, and anti-trap consistency."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner import route
from smart_miner.crawler.fetcher import PageFetcher
from smart_miner.crawler.fingerprint import BrowserProfile, FingerprintEngine, PROFILES


class MockStreamResponse:
    def __init__(self, text="<html><body>Fingerprint test</body></html>"):
        self.text = text
        self.status_code = 200
        self.url = "https://example.test"
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"

    async def aiter_bytes(self):
        yield self.text.encode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class FingerprintEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = FingerprintEngine()

    def test_all_canonical_profiles_loaded(self):
        expected_profiles = {"chrome_windows", "chrome_macos", "edge_windows", "firefox_windows", "safari_macos"}
        self.assertTrue(expected_profiles.issubset(set(PROFILES.keys())))

    def test_all_builtin_profiles_pass_consistency_audit(self):
        for name, profile in PROFILES.items():
            with self.subTest(profile=name):
                issues = self.engine.validate_consistency(profile.headers)
                self.assertEqual(issues, [], f"Profile {name} failed consistency audit: {issues}")

    def test_firefox_profile_strictly_omits_client_hints(self):
        firefox = self.engine.get_profile("firefox_windows")
        self.assertIn("Firefox", firefox.user_agent)
        self.assertNotIn("Sec-Ch-Ua", firefox.headers)
        self.assertNotIn("Sec-Ch-Ua-Platform", firefox.headers)
        self.assertNotIn("Sec-Ch-Ua-Mobile", firefox.headers)

    def test_safari_profile_strictly_omits_client_hints(self):
        safari = self.engine.get_profile("safari_macos")
        self.assertIn("Safari", safari.user_agent)
        self.assertNotIn("Chrome", safari.user_agent)
        self.assertNotIn("Sec-Ch-Ua", safari.headers)

    def test_edge_profile_has_matching_brands(self):
        edge = self.engine.get_profile("edge_windows")
        self.assertIn("Edg/", edge.user_agent)
        self.assertIn("Microsoft Edge", edge.headers.get("Sec-Ch-Ua", ""))

    def test_consistency_validator_detects_anti_bot_traps(self):
        # Trap 1: Firefox with Client Hints
        bad_firefox = dict(PROFILES["firefox_windows"].headers)
        bad_firefox["Sec-Ch-Ua"] = '"Chromium";v="131"'
        self.assertIn("FIREFOX_WITH_CLIENT_HINTS", self.engine.validate_consistency(bad_firefox))

        # Trap 2: Safari with Client Hints
        bad_safari = dict(PROFILES["safari_macos"].headers)
        bad_safari["Sec-Ch-Ua"] = '"Chromium";v="131"'
        self.assertIn("SAFARI_WITH_CLIENT_HINTS", self.engine.validate_consistency(bad_safari))

        # Trap 3: Platform mismatch (Macintosh UA with Windows platform hint)
        bad_platform = dict(PROFILES["chrome_macos"].headers)
        bad_platform["Sec-Ch-Ua-Platform"] = '"Windows"'
        self.assertIn("PLATFORM_MISMATCH_EXPECTED_WINDOWS", self.engine.validate_consistency(bad_platform))

        # Trap 4: Edge brand in Client Hints without Edg in UA
        bad_edge = dict(PROFILES["chrome_windows"].headers)
        bad_edge["Sec-Ch-Ua"] = '"Microsoft Edge";v="131"'
        self.assertIn("BRAND_MISMATCH_EDGE", self.engine.validate_consistency(bad_edge))

    def test_session_affinity_is_deterministic_by_domain(self):
        domain_a = "https://alpha.depin.network/docs"
        domain_b = "https://beta.depin.network/stats"

        # Repeated calls with same domain produce exact same profile
        p1 = self.engine.get_random_profile(seed="alpha.depin.network")
        p2 = self.engine.get_random_profile(seed="alpha.depin.network")
        self.assertEqual(p1.name, p2.name)

    def test_fetcher_applies_specified_firefox_fingerprint(self):
        fetcher = PageFetcher(fingerprint="firefox_windows")
        headers = fetcher.active_headers
        self.assertIn("Firefox", headers["User-Agent"])
        self.assertNotIn("Sec-Ch-Ua", headers)
        self.assertEqual(fetcher.active_profile_name, "firefox_windows")

    def test_fetcher_applies_specified_edge_fingerprint(self):
        fetcher = PageFetcher(fingerprint="edge_windows")
        headers = fetcher.active_headers
        self.assertIn("Edg/", headers["User-Agent"])
        self.assertIn("Microsoft Edge", headers["Sec-Ch-Ua"])
        self.assertEqual(fetcher.active_profile_name, "edge_windows")

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_fetch_static_passes_profile_headers(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.stream.return_value = MockStreamResponse()
        mock_httpx.AsyncClient.return_value = mock_client

        fetcher = PageFetcher(fingerprint="firefox_windows", allow_private_urls=True)
        res = await fetcher.fetch_static("https://example.test")
        self.assertEqual(res.status_code, 200)

        # Verify stream was called with Firefox User-Agent in headers
        call_kwargs = mock_client.stream.call_args.kwargs
        self.assertIn("headers", call_kwargs)
        self.assertIn("Firefox", call_kwargs["headers"]["User-Agent"])
        self.assertNotIn("Sec-Ch-Ua", call_kwargs["headers"])

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_route_records_active_fingerprint(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        unique_text = " ".join(f"evidence_{i}" for i in range(100))
        mock_client.stream.return_value = MockStreamResponse(f"<html><body><p>{unique_text}</p></body></html>")
        mock_httpx.AsyncClient.return_value = mock_client

        result = await route("https://example.test/audit", min_text_length=100, fingerprint="edge_windows", allow_private_urls=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["routing"]["fingerprint"], "edge_windows")


if __name__ == "__main__":
    unittest.main()
