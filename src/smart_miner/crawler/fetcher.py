"""Transport only: keep HTML and final URL for downstream cleaning."""
import asyncio
from dataclasses import dataclass

import httpx
try:
    from playwright.async_api import async_playwright
except ModuleNotFoundError:
    async_playwright = None


@dataclass(frozen=True)
class FetchedPage:
    html: str
    source_url: str
    status_code: int = 200
    strategy: str = "static"


class PageFetcher:
    def __init__(self, wait_selector=None, browser_timeout_ms=30000):
        if browser_timeout_ms <= 0:
            raise ValueError("browser_timeout_ms must be positive")
        self.wait_selector = wait_selector
        self.browser_timeout_ms = browser_timeout_ms

    async def fetch_static(self, url):
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=15.0)
            # Inspect error-page bodies for access barriers before raising.
            return FetchedPage(response.text, str(response.url), response.status_code)

    async def fetch_dynamic(self, url):
        if async_playwright is None:
            raise RuntimeError("Install playwright to enable browser fallback")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, timeout=self.browser_timeout_ms)
            try:
                # One deadline includes context creation, navigation and readiness.
                async with asyncio.timeout(self.browser_timeout_ms / 1000):
                    context = await browser.new_context()
                    page = await context.new_page()
                    response = await page.goto(url, wait_until="domcontentloaded",
                                               timeout=self.browser_timeout_ms)
                    from .barriers import barrier_reason
                    initial = FetchedPage(await page.content(), page.url,
                                          response.status if response else 200, "dynamic")
                    if barrier_reason(initial):
                        return initial
                    if self.wait_selector:
                        try:
                            await page.locator(self.wait_selector).wait_for(
                                state="visible", timeout=self.browser_timeout_ms)
                        except Exception:
                            current = FetchedPage(await page.content(), page.url,
                                                  initial.status_code, "dynamic")
                            if barrier_reason(current):
                                return current
                            raise
                    else:
                        # Bounded settling period; callers should supply a selector for AJAX.
                        await page.wait_for_timeout(min(1000, self.browser_timeout_ms))
                    return FetchedPage(await page.content(), page.url,
                                       response.status if response else 200, "dynamic")
            finally:
                await browser.close()
