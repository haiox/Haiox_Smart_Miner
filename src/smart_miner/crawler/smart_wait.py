"""Heuristic Dynamic Wait & Hydration Settle Engine.

Replaces fixed sleep delays with intelligent heuristics for modern SPAs (React, Next.js,
Vue, Nuxt, Svelte), detecting when client-side frameworks complete DOM hydration or
when mutation activity settles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("smart_miner.crawler.smart_wait")

FRAMEWORK_DETECTION_JS = """
(() => {
    if (window.__NEXT_DATA__) return "next.js";
    if (window.__NUXT__) return "nuxt";
    if (document.querySelector('[data-reactroot], #root > *, #__next > *')) return "react";
    if (window.angular || document.querySelector('[ng-version], [ng-app]')) return "angular";
    if (document.querySelector('[data-v-app], [data-server-rendered]')) return "vue";
    return "vanilla";
})()
"""

DOM_SETTLED_PROMISE_JS = """
(settleMs) => {
    return new Promise((resolve) => {
        let timer = null;
        const observer = new MutationObserver(() => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                observer.disconnect();
                resolve(true);
            }, settleMs);
        });
        observer.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true,
            attributes: true,
            characterData: true
        });
        // Initial timer if DOM is already quiet
        timer = setTimeout(() => {
            observer.disconnect();
            resolve(true);
        }, settleMs);
    });
}
"""


@dataclass
class WaitResult:
    """Diagnostic outcome of dynamic wait execution."""

    settled: bool
    framework: str
    elapsed_ms: float
    wait_mode: str
    error: Optional[str] = None


class SmartWait:
    """Orchestrates heuristic wait conditions for dynamic rendering."""

    def __init__(
        self,
        default_timeout_ms: int = 15000,
        settle_interval_ms: int = 150,
    ):
        self.default_timeout_ms = default_timeout_ms
        self.settle_interval_ms = settle_interval_ms

    async def detect_framework(self, page: Any) -> str:
        """Identify which client-side framework is powering the DOM."""
        try:
            res = await page.evaluate(FRAMEWORK_DETECTION_JS)
            return str(res or "unknown")
        except Exception:
            return "unknown"

    async def wait_for_settled(
        self,
        page: Any,
        *,
        wait_selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        min_text_len: int = 0,
    ) -> WaitResult:
        """Wait for selector (if supplied) or DOM mutation quietness and hydration."""
        start = time.perf_counter()
        t_ms = timeout_ms or self.default_timeout_ms
        framework = "unknown"

        # Case 1: Specific wait selector requested
        if wait_selector:
            try:
                locator = page.locator(wait_selector)
                await locator.wait_for(state="visible", timeout=t_ms)
                framework = await self.detect_framework(page)
                elapsed = (time.perf_counter() - start) * 1000.0
                return WaitResult(
                    settled=True,
                    framework=framework,
                    elapsed_ms=round(elapsed, 2),
                    wait_mode=f"selector:{wait_selector}",
                )
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000.0
                return WaitResult(
                    settled=False,
                    framework=framework,
                    elapsed_ms=round(elapsed, 2),
                    wait_mode=f"selector:{wait_selector}",
                    error=str(exc),
                )

        # Case 2: Heuristic DOM mutation quietness
        try:
            framework = await self.detect_framework(page)
            # Evaluate mutation observer with deadline
            async with asyncio.timeout(max(0.2, t_ms / 1000.0)):
                await page.evaluate(DOM_SETTLED_PROMISE_JS, self.settle_interval_ms)

            elapsed = (time.perf_counter() - start) * 1000.0
            return WaitResult(
                settled=True,
                framework=framework,
                elapsed_ms=round(elapsed, 2),
                wait_mode="mutation_settle",
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            return WaitResult(
                settled=False,
                framework=framework,
                elapsed_ms=round(elapsed, 2),
                wait_mode="mutation_settle",
                error=str(exc),
            )
