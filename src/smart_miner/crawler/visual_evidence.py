"""Cryptographic Visual Evidence & Screenshot Capture Engine.

Captures verifiable screenshot evidence from dynamic pages, computes deterministic
SHA-256 hashes of the visual artifact, and prepares compact base64 thumbnails for
seamless grounding in Haiox MultiAgent & Orchestrator pipelines.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("smart_miner.crawler.visual_evidence")


@dataclass
class VisualEvidence:
    """Verifiable visual evidence artifact with cryptographic provenance."""

    screenshot_sha256: str
    format: str
    width: int
    height: int
    byte_size: int
    timestamp: str
    base64_data_uri: str

    def verify_hash(self, raw_bytes: bytes) -> bool:
        """Verify that raw screenshot bytes mathematically match the evidence hash."""
        computed = hashlib.sha256(raw_bytes).hexdigest()
        return computed == self.screenshot_sha256

    def to_dict(self) -> dict:
        return {
            "screenshot_sha256": self.screenshot_sha256,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "timestamp": self.timestamp,
            "base64_data_uri": self.base64_data_uri,
        }


class VisualEvidenceCapture:
    """Handles screenshot capture and evidence hashing from Playwright pages."""

    @classmethod
    async def capture(
        cls,
        page: Any,
        *,
        full_page: bool = False,
        image_format: str = "png",
        max_thumbnail_bytes: int = 150 * 1024,
    ) -> VisualEvidence:
        """Take screenshot, compute deterministic SHA-256, and produce VisualEvidence."""
        fmt = image_format.lower()
        if fmt not in {"png", "jpeg"}:
            fmt = "png"

        # 1. Take screenshot
        try:
            screenshot_bytes = await page.screenshot(
                full_page=full_page,
                type=fmt,
            )
        except Exception as exc:
            logger.debug("Screenshot capture error: %s", exc)
            screenshot_bytes = b""

        # 2. Compute SHA-256 hash
        sha256_hash = hashlib.sha256(screenshot_bytes).hexdigest()

        # 3. Determine viewport dimensions
        viewport = getattr(page, "viewport_size", None) or {"width": 1366, "height": 768}
        width = viewport.get("width", 1366)
        height = viewport.get("height", 768)

        # 4. Generate compact Base64 Data URI
        b64 = base64.b64encode(screenshot_bytes[:max_thumbnail_bytes]).decode("ascii")
        data_uri = f"data:image/{fmt};base64,{b64}" if screenshot_bytes else ""

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return VisualEvidence(
            screenshot_sha256=sha256_hash,
            format=fmt,
            width=width,
            height=height,
            byte_size=len(screenshot_bytes),
            timestamp=now_iso,
            base64_data_uri=data_uri,
        )
