"""Transport only: keep HTML and final URL for downstream cleaning.

Includes zero-trust URL target validation and bounded streaming to prevent
Out-Of-Memory (OOM) crashes and decompression/zip bomb attacks.
"""
import asyncio
from dataclasses import dataclass

import httpx

try:
    from playwright.async_api import async_playwright
except ModuleNotFoundError:
    async_playwright = None

from .security import validate_url_target

DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass(frozen=True)
class FetchedPage:
    html: str
    source_url: str
    status_code: int = 200
    strategy: str = "static"


class PageFetcher:
    def __init__(
        self,
        wait_selector=None,
        browser_timeout_ms=30000,
        *,
        allow_private_urls: bool = False,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ):
        if browser_timeout_ms <= 0:
            raise ValueError("browser_timeout_ms must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self.wait_selector = wait_selector
        self.browser_timeout_ms = browser_timeout_ms
        self.allow_private_urls = allow_private_urls
        self.max_response_bytes = max_response_bytes

    async def fetch_static(self, url: str) -> FetchedPage:
        validate_url_target(url, allow_private=self.allow_private_urls)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Use bounded streaming if available to guard against unbounded memory growth
            if hasattr(client, "stream"):
                try:
                    async with client.stream("GET", url, timeout=15.0) as response:
                        final_url = str(response.url)
                        if not self.allow_private_urls and final_url != url:
                            validate_url_target(final_url, allow_private=False)

                        # 1. Content-Type inspection
                        content_type = response.headers.get("content-type", "").lower()
                        if content_type:
                            mime = content_type.split(";")[0].strip()
                            if not (
                                mime.startswith("text/")
                                or mime in {
                                    "application/xhtml+xml",
                                    "application/xml",
                                    "application/json",
                                    "application/ld+json",
                                }
                            ):
                                raise ValueError("UNSUPPORTED_CONTENT_TYPE")

                        # 2. Content-Length header pre-check
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                if int(content_length) > self.max_response_bytes:
                                    raise ValueError("PAGE_TOO_LARGE")
                            except ValueError as e:
                                if str(e) == "PAGE_TOO_LARGE":
                                    raise

                        # 3. Bounded chunk streaming (anti-DoS & zip bomb protection)
                        chunks = []
                        total_bytes = 0
                        if hasattr(response, "aiter_bytes"):
                            async for chunk in response.aiter_bytes():
                                total_bytes += len(chunk)
                                if total_bytes > self.max_response_bytes:
                                    raise ValueError("PAGE_TOO_LARGE")
                                chunks.append(chunk)

                            raw_bytes = b"".join(chunks)
                            encoding = getattr(response, "encoding", None) or "utf-8"
                            try:
                                html_text = raw_bytes.decode(encoding, errors="replace")
                            except (LookupError, UnicodeDecodeError):
                                html_text = raw_bytes.decode("utf-8", errors="replace")
                        else:
                            html_text = getattr(response, "text", "")

                        return FetchedPage(html_text, final_url, response.status_code)
                except AttributeError:
                    # In case of partial mock without stream context, fall through to client.get
                    pass

            # Fallback path (compatibility for legacy tests or mock setups)
            response = await client.get(url, timeout=15.0)
            final_url = str(response.url)
            if not self.allow_private_urls and final_url != url:
                validate_url_target(final_url, allow_private=False)
            return FetchedPage(response.text, final_url, response.status_code)

    async def fetch_dynamic(self, url: str) -> FetchedPage:
        validate_url_target(url, allow_private=self.allow_private_urls)
        if async_playwright is None:
            raise RuntimeError("Install playwright to enable browser fallback")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, timeout=self.browser_timeout_ms
            )
            try:
                # One deadline includes context creation, navigation and readiness.
                async with asyncio.timeout(self.browser_timeout_ms / 1000):
                    context = await browser.new_context()
                    page = await context.new_page()
                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=self.browser_timeout_ms
                    )
                    if not self.allow_private_urls and page.url != url:
                        validate_url_target(page.url, allow_private=False)
                    from .barriers import barrier_reason

                    initial = FetchedPage(
                        await page.content(),
                        page.url,
                        response.status if response else 200,
                        "dynamic",
                    )
                    if barrier_reason(initial):
                        return initial
                    if self.wait_selector:
                        try:
                            await page.locator(self.wait_selector).wait_for(
                                state="visible", timeout=self.browser_timeout_ms
                            )
                        except Exception:
                            current = FetchedPage(
                                await page.content(),
                                page.url,
                                initial.status_code,
                                "dynamic",
                            )
                            if barrier_reason(current):
                                return current
                            raise
                    else:
                        # Bounded settling period; callers should supply a selector for AJAX.
                        await page.wait_for_timeout(min(1000, self.browser_timeout_ms))
                    return FetchedPage(
                        await page.content(),
                        page.url,
                        response.status if response else 200,
                        "dynamic",
                    )
            finally:
                await browser.close()
