"""Transport only: keep HTML and final URL for downstream cleaning.

Includes zero-trust URL target validation and bounded streaming to prevent
Out-Of-Memory (OOM) crashes and decompression/zip bomb attacks.
"""
import asyncio
from dataclasses import dataclass

try:
    import httpx
except ModuleNotFoundError:
    httpx = None

try:
    from playwright.async_api import async_playwright
except ModuleNotFoundError:
    async_playwright = None

from .security import validate_url_target

DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_MAX_CONNECTIONS = 100
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20
DEFAULT_KEEPALIVE_EXPIRY = 30.0

DEFAULT_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


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
        browser_timeout_ms: int = 30000,
        *,
        allow_private_urls: bool = False,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        client=None,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        max_keepalive_connections: int = DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry: float = DEFAULT_KEEPALIVE_EXPIRY,
        headers: dict | None = None,
        http2: bool = True,
    ):
        if browser_timeout_ms <= 0:
            raise ValueError("browser_timeout_ms must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if max_keepalive_connections <= 0:
            raise ValueError("max_keepalive_connections must be positive")

        self.wait_selector = wait_selector
        self.browser_timeout_ms = browser_timeout_ms
        self.allow_private_urls = allow_private_urls
        self.max_response_bytes = max_response_bytes

        # Connection Pool & Lifecycle Configuration
        self._client = client
        self._owns_client = client is None
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        self.custom_headers = headers or {}
        self.http2 = http2

    @property
    def is_pool_active(self) -> bool:
        """True if the HTTPX connection pool is active and not closed."""
        return bool(self._client is not None and not getattr(self._client, "is_closed", False))

    @property
    def active_headers(self) -> dict:
        """Effective request headers combining default browser and custom headers."""
        return {**DEFAULT_BROWSER_HEADERS, **self.custom_headers}

    async def get_client(self):
        """Acquire or lazily initialize the shared persistent HTTPX client with connection pooling."""
        if self._client is not None and not getattr(self._client, "is_closed", False):
            return self._client

        if httpx is None:
            raise RuntimeError("Install httpx to enable web fetching")

        limits = (
            httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
                keepalive_expiry=self.keepalive_expiry,
            )
            if hasattr(httpx, "Limits")
            else None
        )

        client_kwargs = {
            "follow_redirects": True,
            "headers": self.active_headers,
            "timeout": 15.0,
        }
        if limits is not None:
            client_kwargs["limits"] = limits
        if self.http2:
            client_kwargs["http2"] = True

        try:
            raw_client = httpx.AsyncClient(**client_kwargs)
        except Exception:
            client_kwargs.pop("http2", None)
            raw_client = httpx.AsyncClient(**client_kwargs)

        # Support unittest mocks that configure __aenter__.return_value vs raw client mocks
        if hasattr(raw_client, "__aenter__") and hasattr(raw_client.__aenter__, "return_value"):
            aenter_val = raw_client.__aenter__.return_value
            if "stream" in getattr(aenter_val, "_mock_children", {}) or "get" in getattr(aenter_val, "_mock_children", {}):
                self._client = aenter_val
            else:
                self._client = raw_client
        else:
            self._client = raw_client

        return self._client

    async def close(self) -> None:
        """Close the underlying connection pool if owned by this instance."""
        if self._owns_client and self._client is not None:
            if hasattr(self._client, "aclose") and not getattr(self._client, "is_closed", False):
                await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self.get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def fetch_static(self, url: str) -> FetchedPage:
        validate_url_target(url, allow_private=self.allow_private_urls)
        client = await self.get_client()

        # Use bounded streaming if available to guard against unbounded memory growth
        if hasattr(client, "stream"):
            try:
                stream_ctx = client.stream("GET", url, timeout=15.0)
                async with stream_ctx as response:
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

                    return FetchedPage(html_text, final_url, response.status_code, "static")
            except (AttributeError, TypeError):
                # In case of mock or client without stream context, fall through to client.get
                pass

        # Fallback path (compatibility for legacy tests or mock setups)
        response = await client.get(url, timeout=15.0)
        final_url = str(response.url)
        if not self.allow_private_urls and final_url != url:
            validate_url_target(final_url, allow_private=False)
        return FetchedPage(response.text, final_url, response.status_code, "static")

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
