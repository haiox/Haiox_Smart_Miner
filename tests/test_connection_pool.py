"""Tests for HTTPX connection pooling, session lifecycle, and stealth headers."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner import route
from smart_miner.crawler.fetcher import (
    DEFAULT_BROWSER_HEADERS,
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
    FetchedPage,
    PageFetcher,
)


class MockResponse:
    def __init__(self, text="<html><body>Pooled Content</body></html>", status_code=200, url="https://example.test"):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"

    async def aiter_bytes(self):
        yield self.text.encode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class ConnectionPoolTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_pool_limits_raise_value_error(self):
        with self.assertRaises(ValueError):
            PageFetcher(max_connections=0)
        with self.assertRaises(ValueError):
            PageFetcher(max_connections=-5)
        with self.assertRaises(ValueError):
            PageFetcher(max_keepalive_connections=0)
        with self.assertRaises(ValueError):
            PageFetcher(max_keepalive_connections=-1)

    def test_stealth_headers_configured_by_default(self):
        fetcher = PageFetcher()
        headers = fetcher.active_headers
        self.assertIn("User-Agent", headers)
        self.assertIn("Chrome", headers["User-Agent"])
        self.assertIn("Sec-Ch-Ua", headers)
        self.assertIn("Accept-Language", headers)
        self.assertEqual(headers["Upgrade-Insecure-Requests"], "1")

    def test_custom_headers_merged_with_defaults(self):
        custom = {"Authorization": "Bearer test-token", "X-Custom": "val"}
        fetcher = PageFetcher(headers=custom)
        headers = fetcher.active_headers
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(headers["X-Custom"], "val")
        self.assertIn("User-Agent", headers)

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_client_lazy_initialization_and_reuse(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_httpx.AsyncClient.return_value = mock_client

        fetcher = PageFetcher(allow_private_urls=True)
        self.assertFalse(fetcher.is_pool_active)

        # First acquisition initializes client
        client1 = await fetcher.get_client()
        self.assertEqual(client1, mock_client)
        self.assertTrue(fetcher.is_pool_active)
        self.assertEqual(mock_httpx.AsyncClient.call_count, 1)

        # Second acquisition reuses existing client without re-instantiation
        client2 = await fetcher.get_client()
        self.assertEqual(client2, mock_client)
        self.assertEqual(mock_httpx.AsyncClient.call_count, 1)

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_close_terminates_owned_client(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        mock_httpx.AsyncClient.return_value = mock_client

        fetcher = PageFetcher()
        await fetcher.get_client()
        self.assertTrue(fetcher.is_pool_active)

        await fetcher.close()
        mock_client.aclose.assert_awaited_once()
        self.assertFalse(fetcher.is_pool_active)

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_async_context_manager_lifecycle(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        mock_httpx.AsyncClient.return_value = mock_client

        async with PageFetcher() as fetcher:
            self.assertTrue(fetcher.is_pool_active)

        mock_client.aclose.assert_awaited_once()
        self.assertFalse(fetcher.is_pool_active)

    async def test_external_injected_client_is_not_closed_by_fetcher(self):
        mock_external = MagicMock()
        mock_external.is_closed = False
        mock_external.aclose = AsyncMock()

        fetcher = PageFetcher(client=mock_external)
        self.assertEqual(await fetcher.get_client(), mock_external)

        await fetcher.close()
        mock_external.aclose.assert_not_awaited()

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_fetch_static_uses_pooled_client(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.stream.return_value = MockResponse("<html>Hello World</html>")
        mock_httpx.AsyncClient.return_value = mock_client

        fetcher = PageFetcher(allow_private_urls=True)
        res = await fetcher.fetch_static("https://example.test/page1")
        self.assertEqual(res.html, "<html>Hello World</html>")
        self.assertEqual(res.strategy, "static")
        mock_client.stream.assert_called_once()

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_route_accepts_injected_fetcher(self, mock_httpx):
        mock_client = MagicMock()
        mock_client.is_closed = False
        unique_words = " ".join(f"signal_{i}" for i in range(100))
        mock_client.stream.return_value = MockResponse(
            f"<html><body><p>{unique_words}</p></body></html>"
        )
        mock_httpx.AsyncClient.return_value = mock_client

        fetcher = PageFetcher(allow_private_urls=True)
        result = await route("https://example.test/good", min_text_length=100, fetcher=fetcher)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
