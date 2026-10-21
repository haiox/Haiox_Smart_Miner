"""Tests for VisualEvidenceCapture & VisualEvidence (Subsystem 22: Cryptographic Visual Evidence)."""

import hashlib
import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_miner.crawler.visual_evidence import (
    VisualEvidence,
    VisualEvidenceCapture,
)


class VisualEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_visual_evidence_and_sha256(self):
        sample_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00mockdata"
        expected_hash = hashlib.sha256(sample_png_bytes).hexdigest()

        mock_page = MagicMock()
        mock_page.screenshot = AsyncMock(return_value=sample_png_bytes)
        mock_page.viewport_size = {"width": 1280, "height": 720}

        evidence = await VisualEvidenceCapture.capture(mock_page, full_page=True, image_format="png")

        self.assertIsInstance(evidence, VisualEvidence)
        self.assertEqual(evidence.screenshot_sha256, expected_hash)
        self.assertEqual(evidence.format, "png")
        self.assertEqual(evidence.width, 1280)
        self.assertEqual(evidence.height, 720)
        self.assertEqual(evidence.byte_size, len(sample_png_bytes))
        self.assertTrue(evidence.base64_data_uri.startswith("data:image/png;base64,"))

        # Verify mathematical integrity
        self.assertTrue(evidence.verify_hash(sample_png_bytes))
        self.assertFalse(evidence.verify_hash(b"tampered_bytes"))

        # Serialization
        d = evidence.to_dict()
        self.assertEqual(d["screenshot_sha256"], expected_hash)
        self.assertEqual(d["format"], "png")


if __name__ == "__main__":
    unittest.main()
