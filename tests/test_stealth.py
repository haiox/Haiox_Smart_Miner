"""Tests for StealthEngine (Subsystem 18: Stealth Driver Injection & Anti-Bot Armor)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_miner.crawler.fingerprint import PROFILES
from smart_miner.crawler.stealth import StealthConfig, StealthEngine


class StealthEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = StealthEngine()

    def test_stealth_script_contains_critical_shims(self):
        script = self.engine.build_init_script()

        # 1. Webdriver mask
        self.assertIn("webdriver", script)
        self.assertIn("delete navigator.__proto__.webdriver", script)

        # 2. window.chrome mock
        self.assertIn("window.chrome", script)
        self.assertIn("runtime", script)

        # 3. Plugins mock
        self.assertIn("PDF Viewer", script)
        self.assertIn("navigator.plugins", script)

        # 4. Permissions mock
        self.assertIn("permissions.query", script)
        self.assertIn("notifications", script)

        # 5. WebGL vendor mock
        self.assertIn("UNMASKED_VENDOR_WEBGL", script)
        self.assertIn("Intel Inc.", script)

    def test_stealth_script_synchronizes_profile_languages(self):
        profile = PROFILES["chrome_windows"]
        script = self.engine.build_init_script(profile=profile)
        self.assertIn('"en-US"', script)

        # Custom languages config
        custom_engine = StealthEngine(StealthConfig(languages=["fa-IR", "fa", "en"]))
        custom_script = custom_engine.build_init_script()
        self.assertIn('"fa-IR"', custom_script)

    async def test_apply_to_context_and_page(self):
        mock_context = MagicMock()
        mock_context.add_init_script = AsyncMock()

        await self.engine.apply_to_context(mock_context)
        mock_context.add_init_script.assert_awaited_once()

        mock_page = MagicMock()
        mock_page.add_init_script = AsyncMock()

        await self.engine.apply_to_page(mock_page)
        mock_page.add_init_script.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
