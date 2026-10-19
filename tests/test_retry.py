"""Unit tests for exponential backoff, full jitter, Retry-After header parsing,
and fault-tolerant retry engine in PageFetcher and CrawlOrchestrator.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner import route
from smart_miner.crawler.fetcher import FetchedPage, PageFetcher
from smart_miner.crawler.retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_DELAY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_STATUSES,
    RetryConfig,
    RetryEngine,
    calculate_backoff,
    is_transient_error,
    parse_retry_after,
)
from smart_miner.crawler.security import SecurityError


class MockStreamResponse:
    def __init__(self, text="<html><body>Success</body></html>", status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.url = "https://example.test/page"
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"

    async def aiter_bytes(self):
        yield self.text.encode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class RetryEngineUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_retry_config_validations(self):
        # Valid configs
        cfg = RetryConfig(max_retries=5, base_delay=0.1, max_delay=2.0)
        self.assertEqual(cfg.max_retries, 5)
        self.assertEqual(cfg.base_delay, 0.1)
        self.assertEqual(cfg.max_delay, 2.0)

        # Invalid max_retries
        with self.assertRaises(ValueError):
            RetryConfig(max_retries=-1)

        # Invalid base_delay
        with self.assertRaises(ValueError):
            RetryConfig(base_delay=-0.5)

        # Invalid max_delay < base_delay
        with self.assertRaises(ValueError):
            RetryConfig(base_delay=2.0, max_delay=1.0)

    def test_calculate_backoff_deterministic(self):
        # Without jitter: strictly base * 2^attempt clamped to max_delay
        self.assertEqual(calculate_backoff(0, base_delay=1.0, max_delay=10.0, jitter=False), 1.0)
        self.assertEqual(calculate_backoff(1, base_delay=1.0, max_delay=10.0, jitter=False), 2.0)
        self.assertEqual(calculate_backoff(2, base_delay=1.0, max_delay=10.0, jitter=False), 4.0)
        self.assertEqual(calculate_backoff(3, base_delay=1.0, max_delay=10.0, jitter=False), 8.0)
        self.assertEqual(calculate_backoff(4, base_delay=1.0, max_delay=10.0, jitter=False), 10.0)

    def test_calculate_backoff_full_jitter_bounds(self):
        # With Full Jitter, output must be bounded: 0.0 <= delay <= ceiling
        for attempt in range(5):
            ceiling = min(10.0, 1.0 * (2 ** attempt))
            for _ in range(25):
                delay = calculate_backoff(attempt, base_delay=1.0, max_delay=10.0, jitter=True)
                self.assertGreaterEqual(delay, 0.0)
                self.assertLessEqual(delay, ceiling)

    def test_parse_retry_after_seconds(self):
        self.assertEqual(parse_retry_after("3"), 3.0)
        self.assertEqual(parse_retry_after("0"), 0.0)
        self.assertEqual(parse_retry_after("-5"), 0.0)
        self.assertEqual(parse_retry_after("120", max_delay=30.0), 30.0)
        self.assertIsNone(parse_retry_after(None))
        self.assertIsNone(parse_retry_after(""))
        self.assertIsNone(parse_retry_after("not-a-number-or-date"))

    def test_parse_retry_after_http_date(self):
        # Future date (+10 seconds)
        future = datetime.now(timezone.utc) + timedelta(seconds=10)
        date_str = format_datetime(future, usegmt=True)
        delay = parse_retry_after(date_str, max_delay=60.0)
        self.assertIsNotNone(delay)
        self.assertGreater(delay, 7.0)
        self.assertLessEqual(delay, 11.0)

        # Past date (-10 seconds)
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        past_str = format_datetime(past, usegmt=True)
        self.assertEqual(parse_retry_after(past_str), 0.0)

    def test_is_transient_error_classification(self):
        self.assertTrue(is_transient_error(TimeoutError("timed out")))
        self.assertTrue(is_transient_error(ConnectionResetError("peer reset")))
        self.assertTrue(is_transient_error(ConnectionRefusedError("connection refused")))

        # Dynamic duck-typed exception names from httpx
        class TimeoutException(Exception):
            pass
        class ConnectError(Exception):
            pass

        self.assertTrue(is_transient_error(TimeoutException()))
        self.assertTrue(is_transient_error(ConnectError()))

        # Non-transient errors must return False
        self.assertFalse(is_transient_error(ValueError("PAGE_TOO_LARGE")))
        self.assertFalse(is_transient_error(ValueError("UNSUPPORTED_CONTENT_TYPE")))
        self.assertFalse(is_transient_error(SecurityError("NON_PUBLIC_ADDRESS")))
        self.assertFalse(is_transient_error(KeyError("missing")))


class PageFetcherRetryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetcher_retries_on_429_and_succeeds(self):
        # Attempt 0: 429 Too Many Requests with Retry-After: 0.01
        resp_429 = MockStreamResponse(
            text="Too Many Requests",
            status_code=429,
            headers={"content-type": "text/html", "retry-after": "0.01"},
        )
        # Attempt 1: 200 OK
        resp_200 = MockStreamResponse(text="<html><body>Recovered Content</body></html>", status_code=200)

        client = MagicMock()
        client.stream.side_effect = [resp_429, resp_200]

        cfg = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1, jitter=False)
        fetcher = PageFetcher(client=client, retry_config=cfg)

        page = await fetcher.fetch_static("https://example.test/rate-limited")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Recovered Content", page.html)
        self.assertEqual(fetcher.last_retries_count, 1)
        self.assertEqual(client.stream.call_count, 2)

    async def test_fetcher_retries_exhausted_on_503(self):
        # Server always returns 503 Service Unavailable
        resp_503 = MockStreamResponse(text="Service Unavailable", status_code=503)

        client = MagicMock()
        client.stream.side_effect = [resp_503, resp_503, resp_503]

        cfg = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=False)
        fetcher = PageFetcher(client=client, retry_config=cfg)

        page = await fetcher.fetch_static("https://example.test/overloaded")
        self.assertEqual(page.status_code, 503)
        self.assertEqual(fetcher.last_retries_count, 2)
        self.assertEqual(client.stream.call_count, 3)

    async def test_fetcher_does_not_retry_on_404(self):
        # 404 Not Found is not transient; must not be retried
        resp_404 = MockStreamResponse(text="Not Found", status_code=404)

        client = MagicMock()
        client.stream.return_value = resp_404

        cfg = RetryConfig(max_retries=3, base_delay=0.01)
        fetcher = PageFetcher(client=client, retry_config=cfg)

        page = await fetcher.fetch_static("https://example.test/missing")
        self.assertEqual(page.status_code, 404)
        self.assertEqual(fetcher.last_retries_count, 0)
        self.assertEqual(client.stream.call_count, 1)

    async def test_fetcher_retries_on_network_connection_reset(self):
        # Attempt 0: ConnectionResetError
        # Attempt 1: 200 OK
        resp_200 = MockStreamResponse(text="<html><body>Connected</body></html>", status_code=200)

        client = MagicMock()
        client.stream.side_effect = [ConnectionResetError("Socket dropped"), resp_200]

        cfg = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05, jitter=False)
        fetcher = PageFetcher(client=client, retry_config=cfg)

        page = await fetcher.fetch_static("https://example.test/flaky-socket")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Connected", page.html)
        self.assertEqual(fetcher.last_retries_count, 1)

    async def test_fetcher_does_not_retry_on_page_too_large(self):
        # Anti-DoS size violation must NOT be retried
        oversized = MockStreamResponse(
            text="Big Data",
            headers={"content-type": "text/html", "content-length": "10000000"},
        )
        client = MagicMock()
        client.stream.return_value = oversized

        cfg = RetryConfig(max_retries=3, base_delay=0.01)
        fetcher = PageFetcher(client=client, max_response_bytes=1024, retry_config=cfg)

        with self.assertRaises(ValueError) as ctx:
            await fetcher.fetch_static("https://example.test/too-large")
        self.assertEqual(str(ctx.exception), "PAGE_TOO_LARGE")
        self.assertEqual(fetcher.last_retries_count, 0)
        self.assertEqual(client.stream.call_count, 1)

    async def test_route_integration_records_retries_count(self):
        # Injected fetcher with retries performed and high-diversity content
        unique_text = " ".join(f"informative_signal_{i}" for i in range(100))
        fetcher = MagicMock()
        fetcher.fetch_static = AsyncMock(
            return_value=FetchedPage(
                f"<html><body><h1>Title</h1><p>{unique_text}</p></body></html>",
                "https://example.test/article",
                200,
            )
        )
        fetcher.active_profile_name = "edge_windows"
        fetcher.last_retries_count = 2

        result = await route("https://example.test/article", fetcher=fetcher)
        self.assertTrue(result["success"])
        self.assertEqual(result["routing"]["retries"], 2)
        self.assertEqual(result["routing"]["fingerprint"], "edge_windows")


if __name__ == "__main__":
    unittest.main()
