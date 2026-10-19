"""Tests for bounded streaming, response size limits and Content-Type inspection."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner import route
from smart_miner.crawler.fetcher import FetchedPage, PageFetcher


class MockStreamResponse:
    def __init__(self, chunks, headers=None, status_code=200, url="https://example.test"):
        self.chunks = chunks
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.status_code = status_code
        self.url = url
        self.encoding = "utf-8"

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class StreamLimitsTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_max_response_bytes_raises(self):
        with self.assertRaises(ValueError):
            PageFetcher(max_response_bytes=0)
        with self.assertRaises(ValueError):
            PageFetcher(max_response_bytes=-1024)

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_unsupported_binary_mime_types_rejected(self, mock_httpx):
        unsupported_types = [
            "image/png",
            "image/jpeg",
            "application/octet-stream",
            "video/mp4",
            "audio/mpeg",
            "application/pdf",
            "application/zip",
        ]
        for mime in unsupported_types:
            with self.subTest(mime=mime):
                client = MagicMock()
                client.is_closed = False
                mock_resp = MockStreamResponse(
                    [b"binary data"], headers={"content-type": mime}
                )
                client.stream.return_value = mock_resp
                mock_httpx.AsyncClient.return_value = client

                fetcher = PageFetcher(allow_private_urls=True)
                with self.assertRaises(ValueError) as ctx:
                    await fetcher.fetch_static("https://example.test/file")
                self.assertEqual(str(ctx.exception), "UNSUPPORTED_CONTENT_TYPE")

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_oversized_content_length_aborts_immediately(self, mock_httpx):
        client = MagicMock()
        client.is_closed = False
        # Header declares 10 MB, fetcher limit is 1 MB
        mock_resp = MockStreamResponse(
            [], headers={"content-type": "text/html", "content-length": str(10 * 1024 * 1024)}
        )
        client.stream.return_value = mock_resp
        mock_httpx.AsyncClient.return_value = client

        fetcher = PageFetcher(allow_private_urls=True, max_response_bytes=1024 * 1024)
        with self.assertRaises(ValueError) as ctx:
            await fetcher.fetch_static("https://example.test/huge")
        self.assertEqual(str(ctx.exception), "PAGE_TOO_LARGE")

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_chunked_stream_cutoff_when_threshold_exceeded(self, mock_httpx):
        # 3 chunks of 500 KB (total 1.5 MB), without Content-Length header
        chunk = b"A" * (500 * 1024)
        mock_resp = MockStreamResponse(
            [chunk, chunk, chunk], headers={"content-type": "text/html"}
        )
        client = MagicMock()
        client.is_closed = False
        client.stream.return_value = mock_resp
        mock_httpx.AsyncClient.return_value = client

        # Limit is 1 MB, chunk 3 will exceed and abort
        fetcher = PageFetcher(allow_private_urls=True, max_response_bytes=1024 * 1024)
        with self.assertRaises(ValueError) as ctx:
            await fetcher.fetch_static("https://example.test/stream")
        self.assertEqual(str(ctx.exception), "PAGE_TOO_LARGE")

    @patch("smart_miner.crawler.fetcher.httpx")
    async def test_safe_content_within_limits_succeeds(self, mock_httpx):
        html_bytes = b"<html><body><h1>Valid Page</h1><p>Useful content</p></body></html>"
        mock_resp = MockStreamResponse(
            [html_bytes],
            headers={"content-type": "text/html; charset=utf-8", "content-length": str(len(html_bytes))},
        )
        client = MagicMock()
        client.is_closed = False
        client.stream.return_value = mock_resp
        mock_httpx.AsyncClient.return_value = client

        fetcher = PageFetcher(allow_private_urls=True, max_response_bytes=1024 * 1024)
        page = await fetcher.fetch_static("https://example.test/page")
        self.assertEqual(page.html, html_bytes.decode("utf-8"))
        self.assertEqual(page.status_code, 200)

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_orchestrator_maps_page_too_large_code(self, mock_fetch_static):
        mock_fetch_static.side_effect = ValueError("PAGE_TOO_LARGE")

        result = await route("https://example.test")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["PAGE_TOO_LARGE"])

    @patch("smart_miner.crawler.fetcher.PageFetcher.fetch_static", new_callable=AsyncMock)
    async def test_orchestrator_maps_unsupported_content_type_code(self, mock_fetch_static):
        mock_fetch_static.side_effect = ValueError("UNSUPPORTED_CONTENT_TYPE")

        result = await route("https://example.test")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["routing"]["reason_codes"], ["UNSUPPORTED_CONTENT_TYPE"])


if __name__ == "__main__":
    unittest.main()
