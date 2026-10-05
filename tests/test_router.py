import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner.crawler.fetcher import FetchedPage

from smart_miner.crawler.router import (
    evaluate_content_quality,
    fetch_dynamic,
    fetch_static,
    route,
)


class ContentQualityTests(unittest.TestCase):
    def test_long_repetitive_content_is_rejected(self):
        quality = evaluate_content_quality("token " * 120, min_text_length=600)

        self.assertFalse(quality["accepted"])
        self.assertEqual(quality["reason_codes"], ["LOW_TEXT_DIVERSITY"])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_dynamic", new_callable=AsyncMock)
    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_accepts_high_quality_static_content(
        self, fetch_static_mock, fetch_dynamic_mock
    ):
        static_text = " ".join(f"useful-word-{index}" for index in range(80))
        fetch_static_mock.return_value = FetchedPage(static_text, "https://example.test")

        result = await route("https://example.test", min_text_length=600)

        self.assertTrue(result["success"])
        self.assertEqual(result["text"], static_text)
        self.assertIsNone(result["error"])
        self.assertEqual(result["routing"]["strategy"], "static")
        self.assertFalse(result["routing"]["fallback_used"])
        self.assertEqual(
            result["routing"]["reason_codes"], ["STATIC_QUALITY_ACCEPTED"]
        )
        self.assertEqual(
            result["routing"]["visible_character_count"], len(static_text)
        )
        self.assertGreaterEqual(result["routing"]["timing_ms"]["total"], 0)
        fetch_dynamic_mock.assert_not_awaited()

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_dynamic", new_callable=AsyncMock)
    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_short_static_content_falls_back_to_dynamic(
        self, fetch_static_mock, fetch_dynamic_mock
    ):
        fetch_static_mock.return_value = FetchedPage("Too short", "https://example.test")
        fetch_dynamic_mock.return_value = FetchedPage("Rendered page content", "https://example.test")

        result = await route("https://example.test", min_text_length=600)

        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "Rendered page content")
        self.assertEqual(result["routing"]["strategy"], "dynamic")
        self.assertTrue(result["routing"]["fallback_used"])
        self.assertEqual(
            result["routing"]["reason_codes"],
            ["INSUFFICIENT_VISIBLE_TEXT", "INSUFFICIENT_WORD_COUNT"],
        )
        self.assertEqual(result["routing"]["visible_character_count"], 21)

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_dynamic", new_callable=AsyncMock)
    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_long_low_diversity_content_falls_back(
        self, fetch_static_mock, fetch_dynamic_mock
    ):
        fetch_static_mock.return_value = FetchedPage("token " * 120, "https://example.test")
        fetch_dynamic_mock.return_value = FetchedPage("Rendered", "https://example.test")

        result = await route("https://example.test", min_text_length=600)

        self.assertEqual(result["routing"]["strategy"], "dynamic")
        self.assertEqual(
            result["routing"]["reason_codes"], ["LOW_TEXT_DIVERSITY"]
        )
        fetch_dynamic_mock.assert_awaited_once_with("https://example.test")

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_error_preserves_compatibility_keys_and_failure_metadata(
        self, fetch_static_mock
    ):
        fetch_static_mock.side_effect = RuntimeError("network unavailable")

        result = await route("https://example.test")

        self.assertFalse(result["success"])
        self.assertEqual(result["text"], "")
        self.assertEqual(result["error"], "RuntimeError")
        self.assertEqual(result["routing"]["strategy"], "failed")
        self.assertFalse(result["routing"]["fallback_used"])
        self.assertEqual(result["routing"]["reason_codes"], ["ROUTING_ERROR"])

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_dynamic", new_callable=AsyncMock)
    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_dynamic_error_reports_attempted_fallback(
        self, fetch_static_mock, fetch_dynamic_mock
    ):
        fetch_static_mock.return_value = FetchedPage("Too short", "https://example.test")
        fetch_dynamic_mock.side_effect = RuntimeError("browser unavailable")

        result = await route("https://example.test", min_text_length=600)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "RuntimeError")
        self.assertTrue(result["routing"]["fallback_used"])
        self.assertGreaterEqual(result["routing"]["timing_ms"]["dynamic"], 0)


if __name__ == "__main__":
    unittest.main()
