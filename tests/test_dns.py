"""Comprehensive unit and integration tests for in-memory DNS caching,
multi-IP fast fallback, and zero-trust SSRF resolution defense.
"""

import socket
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from smart_miner import route
from smart_miner.crawler.dns import (
    DEFAULT_DNS_TTL,
    DEFAULT_MAX_DNS_ENTRIES,
    DNSCacheEntry,
    DNSResolver,
)
from smart_miner.crawler.fetcher import FetchedPage, PageFetcher
from smart_miner.crawler.security import SecurityError


def _make_addrinfo(ip_list):
    """Helper to mock socket.getaddrinfo return format."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
        for ip in ip_list
    ]


class DNSResolverUnitTests(unittest.TestCase):
    def test_dns_resolver_initialization_and_validation(self):
        resolver = DNSResolver(ttl=60.0, max_entries=500)
        self.assertEqual(resolver.ttl, 60.0)
        self.assertEqual(resolver.max_entries, 500)
        self.assertEqual(resolver.size, 0)

        with self.assertRaises(ValueError):
            DNSResolver(ttl=-1)
        with self.assertRaises(ValueError):
            DNSResolver(max_entries=0)

    def test_ip_literal_bypasses_dns_and_validates_ssrf(self):
        resolver = DNSResolver()

        # Public IP literal
        res = resolver.resolve("8.8.8.8")
        self.assertEqual(res, ["8.8.8.8"])
        self.assertEqual(resolver.size, 0)  # Literals are not cached

        # Private IP literals blocked under zero-trust
        with self.assertRaises(SecurityError) as ctx:
            resolver.resolve("127.0.0.1")
        self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

        with self.assertRaises(SecurityError) as ctx:
            resolver.resolve("192.168.1.1")
        self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

        # Private IP literals allowed explicitly
        res_dev = resolver.resolve("127.0.0.1", allow_private=True)
        self.assertEqual(res_dev, ["127.0.0.1"])

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_caching_and_hit_miss_counters(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _make_addrinfo(["93.184.216.34"])
        resolver = DNSResolver(ttl=300.0)

        # 1. First resolution: Cache Miss
        ips_first = resolver.resolve("example.com")
        self.assertEqual(ips_first, ["93.184.216.34"])
        self.assertEqual(resolver.misses_count, 1)
        self.assertEqual(resolver.hits_count, 0)
        self.assertEqual(mock_getaddrinfo.call_count, 1)

        # 2. Second resolution: Cache Hit (instant in-memory)
        ips_second = resolver.resolve("example.com")
        self.assertEqual(ips_second, ["93.184.216.34"])
        self.assertEqual(resolver.misses_count, 1)
        self.assertEqual(resolver.hits_count, 1)
        self.assertEqual(mock_getaddrinfo.call_count, 1)  # No additional socket call!

        # 3. Force refresh: Cache Bypassed
        resolver.resolve("example.com", force_refresh=True)
        self.assertEqual(mock_getaddrinfo.call_count, 2)

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_ttl_expiration(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _make_addrinfo(["93.184.216.34"])
        # Micro-TTL for testing: 0.05 seconds
        resolver = DNSResolver(ttl=0.05)

        resolver.resolve("quick-expire.test")
        self.assertEqual(mock_getaddrinfo.call_count, 1)

        # Sleep past TTL
        time.sleep(0.06)

        # Should be expired and re-resolved
        resolver.resolve("quick-expire.test")
        self.assertEqual(mock_getaddrinfo.call_count, 2)

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_multi_ip_resolution_and_fallback(self, mock_getaddrinfo):
        # Domain with multiple A records (e.g. Cloudflare / CDN endpoints)
        mock_getaddrinfo.return_value = _make_addrinfo([
            "104.16.132.229",
            "104.16.133.229",
            "172.67.150.100",
        ])
        resolver = DNSResolver()

        ips = resolver.resolve("cdn.example.org")
        self.assertEqual(len(ips), 3)

        # Fallback with no failures selects the first IP
        fb1 = resolver.get_fallback_ip("cdn.example.org")
        self.assertEqual(fb1, "104.16.132.229")

        # Fallback when first IP failed selects the second IP
        fb2 = resolver.get_fallback_ip("cdn.example.org", failed_ips=["104.16.132.229"])
        self.assertEqual(fb2, "104.16.133.229")

        # Fallback when all IPs exhausted returns None
        fb_none = resolver.get_fallback_ip("cdn.example.org", failed_ips=ips)
        self.assertIsNone(fb_none)

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_ssrf_filtering_blocks_rebinding_to_private_ips(self, mock_getaddrinfo):
        # 1. DNS Rebinding: domain resolves entirely to loopback
        mock_getaddrinfo.return_value = _make_addrinfo(["127.0.0.1"])
        resolver = DNSResolver()

        with self.assertRaises(SecurityError) as ctx:
            resolver.resolve("rebinding-attack.local")
        self.assertEqual(str(ctx.exception), "NON_PUBLIC_ADDRESS")

        # 2. Mixed DNS response: one private IP, one public IP
        # The private IP must be stripped; only public IP is safely returned
        mock_getaddrinfo.return_value = _make_addrinfo(["10.0.0.1", "142.250.180.206"])
        safe_ips = resolver.resolve("mixed-records.test")
        self.assertEqual(safe_ips, ["142.250.180.206"])
        self.assertNotIn("10.0.0.1", safe_ips)

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_lookup_failure_maps_to_clean_value_error(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        resolver = DNSResolver()

        with self.assertRaises(ValueError) as ctx:
            resolver.resolve("nonexistent.invalid")
        self.assertEqual(str(ctx.exception), "DNS_LOOKUP_FAILED")

    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    def test_dns_cache_invalidation_and_lru_bounds(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _make_addrinfo(["93.184.216.34"])
        resolver = DNSResolver(max_entries=2)

        resolver.resolve("host1.test")
        resolver.resolve("host2.test")
        self.assertEqual(resolver.size, 2)

        # Invalidate host1
        resolver.invalidate("host1.test")
        self.assertEqual(resolver.size, 1)
        self.assertIsNone(resolver.get("host1.test"))

        # Re-add host1 and host3: must evict oldest
        resolver.resolve("host1.test")
        resolver.resolve("host3.test")
        self.assertEqual(resolver.size, 2)
        self.assertIsNone(resolver.get("host2.test"))  # host2 evicted

        # Clear
        resolver.clear()
        self.assertEqual(resolver.size, 0)
        self.assertEqual(resolver.hits_count, 0)


class DNSIntegrationWithFetcherTests(unittest.IsolatedAsyncioTestCase):
    @patch("smart_miner.crawler.dns.socket.getaddrinfo")
    async def test_page_fetcher_warms_and_hits_dns_cache(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _make_addrinfo(["93.184.216.34"])

        client = MagicMock()
        mock_stream = MagicMock()
        mock_stream.url = "https://example.com/article"
        mock_stream.status_code = 200
        mock_stream.headers = {"content-type": "text/html"}
        mock_stream.encoding = "utf-8"
        async def aiter():
            yield b"<html><body><p>DNS Cached Content</p></body></html>"
        mock_stream.aiter_bytes = aiter
        mock_stream.__aenter__.return_value = mock_stream

        def fake_stream(method, url, **kwargs):
            mock_stream.url = url
            return mock_stream
        client.stream.side_effect = fake_stream

        fetcher = PageFetcher(client=client)

        # 1. First fetch: warms cache (1 miss)
        await fetcher.fetch_static("https://example.com/article")
        self.assertEqual(fetcher.dns_resolver.misses_count, 1)
        self.assertEqual(fetcher.dns_resolver.hits_count, 0)

        # 2. Second fetch to same host: hits cache! (1 hit)
        await fetcher.fetch_static("https://example.com/article-2")
        self.assertEqual(fetcher.dns_resolver.misses_count, 1)
        self.assertEqual(fetcher.dns_resolver.hits_count, 1)
        self.assertEqual(mock_getaddrinfo.call_count, 1)  # Zero additional DNS lookups!

    async def test_route_integration_records_dns_hits(self):
        unique_text = " ".join(f"dns_signal_{i}" for i in range(100))
        fetcher = MagicMock()
        fetcher.fetch_static = AsyncMock(
            return_value=FetchedPage(
                f"<html><body><h1>DNS Record</h1><p>{unique_text}</p></body></html>",
                "https://example.test/article",
                200,
            )
        )
        fetcher.active_profile_name = "chrome_windows"
        fetcher.last_retries_count = 0
        fetcher.dns_resolver = MagicMock(hits_count=4)

        result = await route("https://example.test/article", fetcher=fetcher)
        self.assertTrue(result["success"])
        self.assertEqual(result["routing"]["dns_cache_hits"], 4)


if __name__ == "__main__":
    unittest.main()
