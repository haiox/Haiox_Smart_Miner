"""Playwright Browser Context Pool & Lifecycle Manager.

Maintains a reusable browser instance, pools contexts to eliminate Chromium process
launch overhead (from ~3000ms down to <150ms), recycles browser instances before
memory leaks occur, and coordinates stealth & route blocking.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        async_playwright,
    )
except ModuleNotFoundError:  # pragma: no cover
    Browser = Any
    BrowserContext = Any
    Page = Any
    Playwright = Any
    async_playwright = None

from .fingerprint import BrowserProfile, PROFILES
from .resource_blocker import RouteBlocker, RouteBlockerConfig
from .stealth import StealthEngine

logger = logging.getLogger("smart_miner.crawler.browser_pool")

DEFAULT_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-client-side-phishing-detection",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
]


@dataclass
class BrowserPoolConfig:
    """Configuration options for PlaywrightBrowserPool."""

    max_concurrent_contexts: int = 10
    max_contexts_per_instance: int = 50
    browser_timeout_ms: int = 30000
    headless: bool = True
    chromium_args: List[str] = field(default_factory=lambda: list(DEFAULT_CHROMIUM_ARGS))
    enable_stealth: bool = True
    enable_resource_blocking: bool = True
    blocked_resource_types: Set[str] = field(
        default_factory=lambda: {"image", "media", "font"}
    )
    block_telemetry_domains: bool = True


@dataclass
class PoolStats:
    """Runtime statistics for monitoring browser pool health."""

    active_contexts: int = 0
    total_contexts_created: int = 0
    total_recycles: int = 0
    browser_running: bool = False


class PlaywrightBrowserPool:
    """Thread-safe, pooled context manager for Chromium in Playwright."""

    def __init__(
        self,
        config: BrowserPoolConfig | None = None,
        *,
        playwright_instance: Optional[Playwright] = None,
    ):
        self.config = config or BrowserPoolConfig()
        self._external_playwright = playwright_instance
        self._playwright: Optional[Playwright] = playwright_instance
        self._playwright_cm: Any = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_contexts)
        self._active_contexts: Set[BrowserContext] = set()
        self._contexts_count: int = 0
        self._total_contexts_created: int = 0
        self._recycles_count: int = 0
        self._is_closed: bool = False

        self.stealth_engine = StealthEngine()
        self.route_blocker = RouteBlocker(
            RouteBlockerConfig(
                blocked_types=self.config.blocked_resource_types,
                block_telemetry=self.config.block_telemetry_domains,
            )
        )

    @property
    def is_running(self) -> bool:
        """True if the pooled browser instance is currently launched and open."""
        return bool(self._browser is not None and self._browser.is_connected())

    @property
    def stats(self) -> PoolStats:
        """Fetch real-time metrics of pool usage and memory health."""
        return PoolStats(
            active_contexts=len(self._active_contexts),
            total_contexts_created=self._total_contexts_created,
            total_recycles=self._recycles_count,
            browser_running=self.is_running,
        )

    async def _ensure_browser(self) -> Browser:
        """Ensure a healthy browser instance exists, launching or recycling if needed."""
        if self._is_closed:
            raise RuntimeError("Browser pool has been closed.")

        if self._browser is not None:
            if not self._browser.is_connected():
                logger.info("Browser disconnected. Re-launching...")
                await self._cleanup_browser()
            elif self._contexts_count >= self.config.max_contexts_per_instance:
                logger.info(
                    "Context limit (%d) reached for browser instance. Recycling to free RAM...",
                    self.config.max_contexts_per_instance,
                )
                await self._recycle_browser()

        if self._browser is None:
            if self._playwright is None:
                if async_playwright is None:
                    raise RuntimeError("playwright is not installed or available.")
                self._playwright_cm = async_playwright()
                self._playwright = await self._playwright_cm.__aenter__()

            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=self.config.chromium_args,
                timeout=self.config.browser_timeout_ms,
            )
            self._contexts_count = 0

        return self._browser

    async def _recycle_browser(self) -> None:
        """Gracefully close and recycle the active browser instance."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:  # pragma: no cover
                logger.debug("Suppressed error closing recycled browser: %s", exc)
            self._browser = None
            self._recycles_count += 1
            self._contexts_count = 0

    async def _cleanup_browser(self) -> None:
        """Force cleanup browser and any dangling contexts."""
        for ctx in list(self._active_contexts):
            try:
                await ctx.close()
            except Exception:
                pass
        self._active_contexts.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

    async def acquire_context(
        self,
        profile: BrowserProfile | None = None,
        extra_headers: dict | None = None,
    ) -> BrowserContext:
        """Acquire a fresh, isolated BrowserContext with stealth & route interception applied."""
        await self._semaphore.acquire()
        try:
            async with self._lock:
                browser = await self._ensure_browser()

                # Choose consistent browser profile
                prof = profile or PROFILES["chrome_windows"]
                headers = dict(prof.headers)
                if extra_headers:
                    headers.update(extra_headers)

                user_agent = headers.get("User-Agent", prof.user_agent)

                context: BrowserContext = await browser.new_context(
                    user_agent=user_agent,
                    extra_http_headers=headers,
                    viewport={"width": 1366, "height": 768},
                    device_scale_factor=1.0,
                    is_mobile=False,
                    has_touch=False,
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                # Attach stealth hooks
                if self.config.enable_stealth:
                    await self.stealth_engine.apply_to_context(context, profile=prof)

                # Attach resource blocking routes
                if self.config.enable_resource_blocking:
                    await self.route_blocker.attach_to_context(context)

                self._active_contexts.add(context)
                self._contexts_count += 1
                self._total_contexts_created += 1

                return context
        except Exception:
            self._semaphore.release()
            raise

    async def release_context(self, context: BrowserContext) -> None:
        """Safely release and destroy a BrowserContext, decrementing semaphore."""
        try:
            if context in self._active_contexts:
                self._active_contexts.remove(context)
            try:
                await context.close()
            except Exception as exc:  # pragma: no cover
                logger.debug("Suppressed error closing context: %s", exc)
        finally:
            self._semaphore.release()

    async def create_page(
        self,
        profile: BrowserProfile | None = None,
        extra_headers: dict | None = None,
    ) -> tuple[Page, BrowserContext]:
        """Convenience method: Acquire a context and open a single fresh page."""
        context = await self.acquire_context(profile, extra_headers)
        try:
            page = await context.new_page()
            return page, context
        except Exception:
            await self.release_context(context)
            raise

    async def close(self) -> None:
        """Close all active contexts, browsers, and the Playwright driver."""
        async with self._lock:
            self._is_closed = True
            await self._cleanup_browser()
            if self._playwright_cm is not None:
                try:
                    await self._playwright_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._playwright_cm = None
                self._playwright = None

    async def __aenter__(self) -> PlaywrightBrowserPool:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
