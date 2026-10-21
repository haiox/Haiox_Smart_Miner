"""Tests for ScrollEmulator (Subsystem 21: Infinite Scroll & Virtual List Emulation)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_miner.crawler.scroll import ScrollConfig, ScrollEmulator, ScrollReport


class ScrollEmulatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.emulator = ScrollEmulator(
            ScrollConfig(max_scrolls=3, step_pixels=500, delay_ms=10, settle_ms=10)
        )

    async def test_scroll_execution_with_expanding_content(self):
        mock_page = MagicMock()
        # Simulate growing scroll height: 1000 -> 1500 -> 2000 -> 2500
        heights = [1000, 1500, 2000, 2500]
        bytes_lens = [5000, 7000, 9000, 11000]

        async def mock_evaluate(script, *args):
            if "scrollHeight" in script:
                return heights.pop(0) if heights else 2500
            if "outerHTML.length" in script:
                return bytes_lens.pop(0) if bytes_lens else 11000
            return None

        mock_page.evaluate = AsyncMock(side_effect=mock_evaluate)

        report = await self.emulator.scroll(mock_page)
        self.assertIsInstance(report, ScrollReport)
        self.assertEqual(report.total_scrolls, 3)
        self.assertEqual(report.initial_height, 1000)
        self.assertEqual(report.final_height, 2500)
        self.assertGreater(report.bytes_added_estimate, 0)
        self.assertFalse(report.reached_bottom)

    async def test_stagnant_height_early_stop(self):
        mock_page = MagicMock()
        # Height stops expanding immediately: 1000 -> 1000 -> 1000
        async def mock_evaluate(script, *args):
            if "scrollHeight" in script:
                return 1000
            if "outerHTML.length" in script:
                return 5000
            return None

        mock_page.evaluate = AsyncMock(side_effect=mock_evaluate)

        config = ScrollConfig(max_scrolls=10, stagnant_threshold=2, delay_ms=5, settle_ms=5)
        report = await self.emulator.scroll(mock_page, config=config)

        # Should stop after reaching stagnant_threshold (2 scrolls)
        self.assertEqual(report.total_scrolls, 2)
        self.assertTrue(report.reached_bottom)
        self.assertEqual(report.initial_height, 1000)
        self.assertEqual(report.final_height, 1000)
        self.assertEqual(report.bytes_added_estimate, 0)

        # Serialization
        data = report.to_dict()
        self.assertEqual(data["total_scrolls"], 2)
        self.assertTrue(data["reached_bottom"])


if __name__ == "__main__":
    unittest.main()
