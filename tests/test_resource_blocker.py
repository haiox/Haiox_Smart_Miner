"""Tests for RouteBlocker (Subsystem 17: Route Hijacking & Resource Blocker)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_miner.crawler.resource_blocker import (
    BlockMetrics,
    RouteBlocker,
    RouteBlockerConfig,
)


class RouteBlockerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.blocker = RouteBlocker()

    def test_blocks_specified_resource_types(self):
        blocked, reason = self.blocker.should_block("https://example.com/photo.bin", "image")
        self.assertTrue(blocked)
        self.assertEqual(reason, "TYPE:image")

        blocked, reason = self.blocker.should_block("https://example.com/song.bin", "media")
        self.assertTrue(blocked)
        self.assertEqual(reason, "TYPE:media")

        blocked, reason = self.blocker.should_block("https://example.com/font.bin", "font")
        self.assertTrue(blocked)
        self.assertEqual(reason, "TYPE:font")

    def test_blocks_by_file_extensions(self):
        blocked, reason = self.blocker.should_block("https://example.com/asset.png", "other")
        self.assertTrue(blocked)
        self.assertEqual(reason, "EXT:.png")

        blocked, reason = self.blocker.should_block("https://example.com/hero.mp4", "other")
        self.assertTrue(blocked)
        self.assertEqual(reason, "EXT:.mp4")

        blocked, reason = self.blocker.should_block("https://example.com/fonts/inter.woff2", "other")
        self.assertTrue(blocked)
        self.assertEqual(reason, "EXT:.woff2")

    def test_blocks_telemetry_domains(self):
        blocked, reason = self.blocker.should_block("https://www.google-analytics.com/analytics.js", "script")
        self.assertTrue(blocked)
        self.assertIn("TELEMETRY", reason)

        blocked, reason = self.blocker.should_block("https://connect.facebook.net/en_US/fbevents.js", "script")
        self.assertTrue(blocked)
        self.assertIn("TELEMETRY", reason)

    def test_allows_essential_documents_and_scripts(self):
        blocked, reason = self.blocker.should_block("https://example.com/article/123", "document")
        self.assertFalse(blocked)
        self.assertEqual(reason, "ALLOWED")

        blocked, reason = self.blocker.should_block("https://example.com/bundle.js", "script")
        self.assertFalse(blocked)
        self.assertEqual(reason, "ALLOWED")

        blocked, reason = self.blocker.should_block("https://example.com/api/data.json", "xhr")
        self.assertFalse(blocked)
        self.assertEqual(reason, "ALLOWED")

    async def test_route_handler_aborts_or_continues(self):
        mock_route = MagicMock()
        mock_route.abort = AsyncMock()
        mock_route.continue_ = AsyncMock()

        # Image request -> abort
        img_req = MagicMock(url="https://example.com/cat.jpg", resource_type="image")
        await self.blocker.handle_route(mock_route, img_req)
        mock_route.abort.assert_awaited_once_with("blockedbyclient")
        mock_route.continue_.assert_not_awaited()

        # Reset mocks
        mock_route.abort.reset_mock()
        mock_route.continue_.reset_mock()

        # Document request -> continue
        doc_req = MagicMock(url="https://example.com/page", resource_type="document")
        await self.blocker.handle_route(mock_route, doc_req)
        mock_route.abort.assert_not_awaited()
        mock_route.continue_.assert_awaited_once()

        # Verify metrics
        metrics = self.blocker.metrics
        self.assertEqual(metrics.total_intercepted, 2)
        self.assertEqual(metrics.blocked_count, 1)
        self.assertEqual(metrics.allowed_count, 1)
        self.assertEqual(metrics.block_ratio, 50.0)
        self.assertGreater(metrics.estimated_bytes_saved, 0)


if __name__ == "__main__":
    unittest.main()
