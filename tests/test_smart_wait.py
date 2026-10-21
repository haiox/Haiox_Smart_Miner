"""Tests for SmartWait (Subsystem 19: Heuristic Dynamic Wait & Hydration Settle)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_miner.crawler.smart_wait import SmartWait, WaitResult


class SmartWaitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.waiter = SmartWait(default_timeout_ms=1000, settle_interval_ms=50)

    async def test_detect_framework(self):
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value="next.js")

        framework = await self.waiter.detect_framework(mock_page)
        self.assertEqual(framework, "next.js")

    async def test_wait_for_settled_with_selector_success(self):
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.wait_for = AsyncMock()
        mock_page.locator.return_value = mock_locator
        mock_page.evaluate = AsyncMock(return_value="react")

        res = await self.waiter.wait_for_settled(mock_page, wait_selector="#content")
        self.assertTrue(res.settled)
        self.assertEqual(res.framework, "react")
        self.assertEqual(res.wait_mode, "selector:#content")
        self.assertIsNone(res.error)

    async def test_wait_for_settled_with_selector_failure(self):
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.wait_for = AsyncMock(side_effect=TimeoutError("Selector not found"))
        mock_page.locator.return_value = mock_locator
        mock_page.evaluate = AsyncMock(return_value="unknown")

        res = await self.waiter.wait_for_settled(mock_page, wait_selector="#missing")
        self.assertFalse(res.settled)
        self.assertEqual(res.wait_mode, "selector:#missing")
        self.assertIn("Selector not found", str(res.error))

    async def test_wait_for_settled_mutation_observer_flow(self):
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        res = await self.waiter.wait_for_settled(mock_page)
        self.assertTrue(res.settled)
        self.assertEqual(res.wait_mode, "mutation_settle")


if __name__ == "__main__":
    unittest.main()
