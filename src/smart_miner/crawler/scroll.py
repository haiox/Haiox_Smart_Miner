"""Infinite Scroll & Virtual List Emulation Engine.

Emulates human-like stepped scrolling in Playwright to trigger IntersectionObserver
callbacks, lazy-loaded media placeholders, and virtualized feed items (e.g. social feeds,
infinite catalog listings).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("smart_miner.crawler.scroll")


@dataclass
class ScrollConfig:
    """Options controlling stepped infinite scrolling."""

    max_scrolls: int = 5
    step_pixels: int = 800
    delay_ms: int = 250
    settle_ms: int = 350
    stop_on_stagnant_height: bool = True
    stagnant_threshold: int = 2


@dataclass
class ScrollReport:
    """Metrics recorded during stepped scroll emulation."""

    total_scrolls: int
    initial_height: int
    final_height: int
    bytes_added_estimate: int
    duration_ms: float
    reached_bottom: bool

    def to_dict(self) -> dict:
        return {
            "total_scrolls": self.total_scrolls,
            "initial_height": self.initial_height,
            "final_height": self.final_height,
            "bytes_added_estimate": self.bytes_added_estimate,
            "duration_ms": self.duration_ms,
            "reached_bottom": self.reached_bottom,
        }


class ScrollEmulator:
    """Orchestrates stepped downward scrolling on a Playwright Page."""

    def __init__(self, config: ScrollConfig | None = None):
        self.config = config or ScrollConfig()

    async def get_scroll_height(self, page: Any) -> int:
        """Measure current scroll height of the document body."""
        try:
            val = await page.evaluate("() => document.body.scrollHeight || document.documentElement.scrollHeight || 0")
            return int(val or 0)
        except Exception:
            return 0

    async def get_dom_size(self, page: Any) -> int:
        """Measure current HTML string length to detect newly injected content."""
        try:
            val = await page.evaluate("() => document.documentElement.outerHTML.length")
            return int(val or 0)
        except Exception:
            return 0

    async def scroll(self, page: Any, config: Optional[ScrollConfig] = None) -> ScrollReport:
        """Execute stepped scroll down with adaptive stagnation termination."""
        cfg = config or self.config
        start_time = time.perf_counter()

        initial_h = await self.get_scroll_height(page)
        initial_bytes = await self.get_dom_size(page)

        current_h = initial_h
        scrolls_executed = 0
        stagnant_count = 0
        reached_bottom = False

        for i in range(cfg.max_scrolls):
            scrolls_executed += 1

            # Step 1: Scroll by step_pixels
            try:
                await page.evaluate(f"window.scrollBy({{ top: {cfg.step_pixels}, behavior: 'smooth' }});")
            except Exception as exc:
                logger.debug("Scroll execution error: %s", exc)
                break

            await asyncio.sleep(cfg.delay_ms / 1000.0)

            # Step 2: Measure new height
            new_h = await self.get_scroll_height(page)
            if new_h <= current_h:
                stagnant_count += 1
                if cfg.stop_on_stagnant_height and stagnant_count >= cfg.stagnant_threshold:
                    reached_bottom = True
                    break
            else:
                stagnant_count = 0
                current_h = new_h

            if cfg.settle_ms > 0:
                await asyncio.sleep(cfg.settle_ms / 1000.0)

        final_bytes = await self.get_dom_size(page)
        elapsed = (time.perf_counter() - start_time) * 1000.0

        return ScrollReport(
            total_scrolls=scrolls_executed,
            initial_height=initial_h,
            final_height=current_h,
            bytes_added_estimate=max(0, final_bytes - initial_bytes),
            duration_ms=round(elapsed, 2),
            reached_bottom=reached_bottom,
        )
