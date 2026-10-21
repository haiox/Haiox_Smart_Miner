"""Tests for PlaywrightBrowserPool (Subsystem 16: Browser Context Pool & Lifecycle Manager)."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner.crawler.browser_pool import (
    BrowserPoolConfig,
    PlaywrightBrowserPool,
    PoolStats,
)
from smart_miner.crawler.fingerprint import PROFILES


class BrowserPoolLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_playwright = MagicMock()
        self.mock_browser = MagicMock()
        self.mock_browser.is_connected.return_value = True
        self.mock_browser.close = AsyncMock()

        def make_context(**kwargs):
            ctx = MagicMock()
            ctx.close = AsyncMock()
            ctx.add_init_script = AsyncMock()
            ctx.route = AsyncMock()
            ctx.new_page = AsyncMock(return_value=MagicMock())
            return ctx

        self.mock_browser.new_context = AsyncMock(side_effect=make_context)
        self.mock_playwright.chromium.launch = AsyncMock(return_value=self.mock_browser)

    async def test_pool_lazy_initialization(self):
        config = BrowserPoolConfig(max_concurrent_contexts=3, max_contexts_per_instance=5)
        pool = PlaywrightBrowserPool(config, playwright_instance=self.mock_playwright)

        self.assertFalse(pool.is_running)
        self.assertEqual(pool.stats.active_contexts, 0)
        self.assertEqual(pool.stats.total_contexts_created, 0)
        self.assertEqual(pool.stats.total_recycles, 0)

        # Trigger initialization by acquiring context
        ctx = await pool.acquire_context(profile=PROFILES["chrome_windows"])
        self.assertTrue(pool.is_running)
        self.assertEqual(pool.stats.active_contexts, 1)
        self.assertEqual(pool.stats.total_contexts_created, 1)

        # Release context
        await pool.release_context(ctx)
        self.assertEqual(pool.stats.active_contexts, 0)
        self.assertEqual(pool.stats.total_contexts_created, 1)
        ctx.close.assert_awaited_once()

        await pool.close()

    async def test_pool_concurrency_semaphore_limits(self):
        config = BrowserPoolConfig(max_concurrent_contexts=2)
        pool = PlaywrightBrowserPool(config, playwright_instance=self.mock_playwright)

        ctx1 = await pool.acquire_context()
        ctx2 = await pool.acquire_context()
        self.assertEqual(pool.stats.active_contexts, 2)

        # Releasing one allows another
        await pool.release_context(ctx1)
        self.assertEqual(pool.stats.active_contexts, 1)

        ctx3 = await pool.acquire_context()
        self.assertEqual(pool.stats.active_contexts, 2)

        await pool.release_context(ctx2)
        await pool.release_context(ctx3)
        self.assertEqual(pool.stats.active_contexts, 0)
        await pool.close()

    async def test_browser_instance_recycling_at_limit(self):
        config = BrowserPoolConfig(max_contexts_per_instance=2)
        pool = PlaywrightBrowserPool(config, playwright_instance=self.mock_playwright)

        ctx1 = await pool.acquire_context()
        await pool.release_context(ctx1)

        ctx2 = await pool.acquire_context()
        await pool.release_context(ctx2)
        self.assertEqual(pool.stats.total_recycles, 0)

        # Third context triggers recycling
        ctx3 = await pool.acquire_context()
        await pool.release_context(ctx3)
        self.assertEqual(pool.stats.total_recycles, 1)
        self.assertEqual(self.mock_browser.close.await_count, 1)

        await pool.close()

    async def test_create_page_convenience(self):
        pool = PlaywrightBrowserPool(playwright_instance=self.mock_playwright)
        page, context = await pool.create_page()

        self.assertIsNotNone(page)
        self.assertIsNotNone(context)
        self.assertEqual(pool.stats.active_contexts, 1)

        await pool.release_context(context)
        self.assertEqual(pool.stats.active_contexts, 0)
        await pool.close()

    async def test_pool_close_shuts_down_cleanly(self):
        pool = PlaywrightBrowserPool(playwright_instance=self.mock_playwright)
        ctx = await pool.acquire_context()
        self.assertEqual(pool.stats.active_contexts, 1)

        await pool.close()
        self.assertEqual(pool.stats.active_contexts, 0)
        self.assertFalse(pool.is_running)

        with self.assertRaises(RuntimeError):
            await pool.acquire_context()


if __name__ == "__main__":
    unittest.main()
