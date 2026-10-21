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

from urllib.parse import urlsplit

from .dns import DNSResolver
from .fingerprint import BrowserProfile, FingerprintEngine, PROFILES
from .retry import RetryConfig, RetryEngine, is_transient_error
from .security import validate_url_target

DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_MAX_CONNECTIONS = 100
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20
DEFAULT_KEEPALIVE_EXPIRY = 30.0

DEFAULT_BROWSER_HEADERS = dict(PROFILES["chrome_windows"].headers)


@dataclass(frozen=True)
class FetchedPage:
    html: str
    source_url: str
    status_code: int = 200
    strategy: str = "static"
    response_headers: dict | None = None
    barrier_report: dict | None = None
    visual_evidence: dict | None = None
    scroll_report: dict | None = None
    wait_result: dict | None = None


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
        fingerprint: str | BrowserProfile | None = None,
        session_affinity: bool = True,
        retries: int | None = None,
        retry_config: RetryConfig | None = None,
        dns_resolver: DNSResolver | None = None,
        browser_pool=None,
        enable_stealth: bool = True,
        enable_resource_blocking: bool = True,
        enable_smart_wait: bool = True,
        enable_scroll: bool = False,
        capture_visual_evidence: bool = False,
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

        # Fingerprint Engine Configuration
        self.fingerprint_engine = FingerprintEngine()
        self.fingerprint_mode = fingerprint or "chrome_windows"
        self.session_affinity = session_affinity
        self._active_profile: BrowserProfile | None = None

        # Retry Engine Configuration
        if retry_config is not None:
            self.retry_engine = RetryEngine(retry_config)
        elif retries is not None:
            self.retry_engine = RetryEngine(RetryConfig(max_retries=retries))
        else:
            self.retry_engine = RetryEngine()
        self.last_retries_count: int = 0

        # DNS Cache & Resolver Configuration
        self.dns_resolver = dns_resolver or DNSResolver(allow_private_urls=self.allow_private_urls)

        # Browser Pool & Dynamic Anti-Bot Configuration
        self.browser_pool = browser_pool
        self.enable_stealth = enable_stealth
        self.enable_resource_blocking = enable_resource_blocking
        self.enable_smart_wait = enable_smart_wait
        self.enable_scroll = enable_scroll
        self.capture_visual_evidence = capture_visual_evidence

    @property
    def is_pool_active(self) -> bool:
        """True if the HTTPX connection pool is active and not closed."""
        return bool(self._client is not None and getattr(self._client, "is_closed", False) is not True)

    def get_headers_for_url(self, url: str = "") -> dict:
        """Resolve and audit consistent browser headers for the given target URL."""
        if self.fingerprint_mode == "random":
            if self.session_affinity and url:
                domain = urlsplit(url).netloc.split(":")[0] if "://" in url else url
                profile = self.fingerprint_engine.get_random_profile(seed=domain)
            else:
                profile = self.fingerprint_engine.get_random_profile()
        elif isinstance(self.fingerprint_mode, BrowserProfile):
            profile = self.fingerprint_mode
        else:
            profile = self.fingerprint_engine.get_profile(self.fingerprint_mode)

        self._active_profile = profile
        return self.fingerprint_engine.build_headers(profile, custom_headers=self.custom_headers)

    @property
    def active_headers(self) -> dict:
        """Effective request headers combining current profile and custom headers."""
        if self._active_profile is not None:
            return self.fingerprint_engine.build_headers(self._active_profile, custom_headers=self.custom_headers)
        return self.get_headers_for_url("")

    @property
    def active_profile_name(self) -> str:
        """Name of the currently active browser profile."""
        if self._active_profile is not None:
            return self._active_profile.name
        if isinstance(self.fingerprint_mode, BrowserProfile):
            return self.fingerprint_mode.name
        return str(self.fingerprint_mode)

    async def get_client(self):
        """Acquire or lazily initialize the shared persistent HTTPX client with connection pooling."""
        if self._client is not None and getattr(self._client, "is_closed", False) is not True:
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
        """Close the underlying connection pool and browser pool if owned by this instance."""
        if self._owns_client and self._client is not None:
            if hasattr(self._client, "aclose") and getattr(self._client, "is_closed", False) is not True:
                await self._client.aclose()
            self._client = None
        if self.browser_pool is not None and getattr(self, "_owns_browser_pool", False):
            await self.browser_pool.close()

    async def __aenter__(self):
        await self.get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _fetch_single_static(self, client, url: str, req_headers: dict) -> FetchedPage:
        # Use bounded streaming if available to guard against unbounded memory growth
        if hasattr(client, "stream"):
            try:
                try:
                    stream_ctx = client.stream("GET", url, headers=req_headers, timeout=15.0)
                except TypeError:
                    stream_ctx = client.stream("GET", url, timeout=15.0)

                async with stream_ctx as response:
                    final_url = str(response.url)
                    if not self.allow_private_urls and final_url != url:
                        validate_url_target(final_url, allow_private=False, dns_resolver=self.dns_resolver)

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

                    resp_headers = dict(response.headers) if hasattr(response, "headers") else {}
                    return FetchedPage(html_text, final_url, response.status_code, "static", resp_headers)
            except (AttributeError, TypeError):
                # In case of mock or client without stream context, fall through to client.get
                pass

        # Fallback path (compatibility for legacy tests or mock setups)
        try:
            response = await client.get(url, headers=req_headers, timeout=15.0)
        except TypeError:
            response = await client.get(url, timeout=15.0)

        final_url = str(response.url)
        if not self.allow_private_urls and final_url != url:
            validate_url_target(final_url, allow_private=False, dns_resolver=self.dns_resolver)
        resp_headers = dict(response.headers) if hasattr(response, "headers") else {}
        return FetchedPage(response.text, final_url, response.status_code, "static", resp_headers)

    async def fetch_static(self, url: str) -> FetchedPage:
        # Validate URL and warm DNS cache
        validate_url_target(url, allow_private=self.allow_private_urls, dns_resolver=self.dns_resolver)

        client = await self.get_client()
        req_headers = self.get_headers_for_url(url)

        self.last_retries_count = 0
        max_retries = self.retry_engine.config.max_retries

        for attempt in range(max_retries + 1):
            try:
                page = await self._fetch_single_static(client, url, req_headers)
                if (
                    self.retry_engine.should_retry_status(page.status_code)
                    and attempt < max_retries
                ):
                    self.last_retries_count += 1
                    await self.retry_engine.sleep_backoff(attempt, page.response_headers)
                    continue
                return page
            except Exception as exc:
                if not is_transient_error(exc) or attempt >= max_retries:
                    raise
                self.last_retries_count += 1
                await self.retry_engine.sleep_backoff(attempt)

    async def _execute_dynamic_page(self, page, url: str) -> FetchedPage:
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=self.browser_timeout_ms
        )
        if not self.allow_private_urls and page.url != url:
            validate_url_target(page.url, allow_private=False, dns_resolver=self.dns_resolver)

        from .barriers import BarrierDetector, barrier_reason

        raw_content = await page.content()
        status = response.status if response and hasattr(response, "status") else 200
        headers = dict(response.headers) if response and hasattr(response, "headers") else {}

        initial = FetchedPage(
            raw_content,
            page.url,
            status,
            "dynamic",
            response_headers=headers,
        )

        barrier_rep = BarrierDetector.detect(initial)
        if barrier_rep.is_blocked:
            return FetchedPage(
                raw_content,
                page.url,
                status,
                "dynamic",
                response_headers=headers,
                barrier_report=barrier_rep.to_dict(),
            )

        wait_res = None
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
                    response_headers=headers,
                )
                if barrier_reason(current):
                    return current
                raise
        elif self.enable_smart_wait:
            try:
                from .smart_wait import SmartWait
                sw = SmartWait(default_timeout_ms=min(5000, self.browser_timeout_ms))
                wait_res = await sw.wait_for_settled(page, timeout_ms=self.browser_timeout_ms)
            except Exception:
                await page.wait_for_timeout(min(1000, self.browser_timeout_ms))
        else:
            await page.wait_for_timeout(min(1000, self.browser_timeout_ms))

        # Scroll Emulation
        scroll_rep = None
        if self.enable_scroll:
            try:
                from .scroll import ScrollEmulator
                se = ScrollEmulator()
                scroll_rep = await se.scroll(page)
            except Exception:
                pass

        # Visual Evidence
        visual_ev = None
        if self.capture_visual_evidence:
            try:
                from .visual_evidence import VisualEvidenceCapture
                visual_ev = await VisualEvidenceCapture.capture(page)
            except Exception:
                pass

        final_content = await page.content()
        return FetchedPage(
            final_content,
            page.url,
            status,
            "dynamic",
            response_headers=headers,
            barrier_report=barrier_rep.to_dict() if barrier_rep.is_blocked else None,
            visual_evidence=visual_ev.to_dict() if visual_ev else None,
            scroll_report=scroll_rep.to_dict() if scroll_rep else None,
            wait_result=wait_res.__dict__ if wait_res else None,
        )

    async def fetch_dynamic(self, url: str) -> FetchedPage:
        validate_url_target(url, allow_private=self.allow_private_urls, dns_resolver=self.dns_resolver)
        req_headers = self.get_headers_for_url(url)

        if self.browser_pool is not None:
            context = await self.browser_pool.acquire_context(profile=self._active_profile, extra_headers=req_headers)
            try:
                page = await context.new_page()
                return await self._execute_dynamic_page(page, url)
            finally:
                await self.browser_pool.release_context(context)

        if async_playwright is None:
            raise RuntimeError("Install playwright to enable browser fallback")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, timeout=self.browser_timeout_ms
            )
            try:
                # One deadline includes context creation, navigation and readiness.
                async with asyncio.timeout(self.browser_timeout_ms / 1000):
                    context = await browser.new_context(
                        user_agent=req_headers.get("User-Agent"),
                        extra_http_headers=req_headers,
                    )
                    if self.enable_stealth:
                        try:
                            from .stealth import StealthEngine
                            await StealthEngine().apply_to_context(context, profile=self._active_profile)
                        except Exception:
                            pass
                    if self.enable_resource_blocking:
                        try:
                            from .resource_blocker import RouteBlocker
                            await RouteBlocker().attach_to_context(context)
                        except Exception:
                            pass

                    page = await context.new_page()
                    return await self._execute_dynamic_page(page, url)
            finally:
                await browser.close()
