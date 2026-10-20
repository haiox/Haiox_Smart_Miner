"""Phase 1 Network Shield - Benchmark & Stress Verification Suite.

Validates that performance guarantees, memory limits, and latency budgets
are strictly met across all Subsystems of Phase 1: The Network Shield.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock

from smart_miner.crawler.security import is_public_ip, validate_url_target, SecurityError
from smart_miner.crawler.dns import DNSResolver
from smart_miner.crawler.fingerprint import FingerprintEngine
from smart_miner.crawler.retry import RetryEngine, RetryConfig
from smart_miner.crawler.fetcher import PageFetcher, FetchedPage

# Import benchmark functions
scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
from benchmark_phase1 import (
    benchmark_ssrf_filter,
    benchmark_dns_cache_lookup,
    benchmark_fingerprint_matrix,
    benchmark_retry_jitter_engine,
    run_all_benchmarks,
)


class BenchmarkAndStressTests(unittest.TestCase):
    def test_ssrf_benchmark_metrics_and_guarantees(self):
        res = benchmark_ssrf_filter(iterations=100)
        self.assertEqual(res["name"], "Zero-Trust SSRF Filter")
        self.assertGreater(res["operations"], 0)
        self.assertGreater(res["ops_per_second"], 1000)
        # Verify latency is well below 1ms (1000 µs)
        self.assertLess(res["avg_latency_us"], 1000.0)

    def test_dns_cache_benchmark_metrics_and_latency(self):
        res = benchmark_dns_cache_lookup(iterations=100)
        self.assertEqual(res["name"], "In-Memory DNS Cache Lookup")
        self.assertGreater(res["operations"], 0)
        self.assertGreater(res["ops_per_second"], 50000)
        # In-memory lookup must be sub-millisecond (< 50,000 ns = 0.05ms)
        self.assertLess(res["avg_latency_ns"], 50_000.0)

    def test_fingerprint_matrix_benchmark_consistency(self):
        res = benchmark_fingerprint_matrix(iterations=100)
        self.assertEqual(res["name"], "Browser Fingerprint & Trap Audit")
        self.assertGreater(res["operations"], 0)
        self.assertGreater(res["ops_per_second"], 5000)
        self.assertLess(res["avg_latency_us"], 200.0)

    def test_retry_jitter_benchmark_distribution(self):
        res = benchmark_retry_jitter_engine(iterations=100)
        self.assertEqual(res["name"], "Exponential Backoff & Full Jitter")
        self.assertGreater(res["operations"], 0)
        self.assertGreater(res["ops_per_second"], 10000)
        self.assertLess(res["avg_latency_us"], 100.0)

    def test_run_all_benchmarks_runner(self):
        results = run_all_benchmarks()
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertIn("ops_per_second", r)
            self.assertIn("guarantee", r)

    def test_multi_ip_failover_stress_rotation(self):
        resolver = DNSResolver(ttl=300, max_entries=100)
        cdn_ips = ["104.21.45.1", "104.21.45.2", "104.21.45.3", "104.21.45.4"]
        resolver.set("cdn.haiox.ai", cdn_ips)

        # Simulate sequential CDN node failures with accumulated failed_ips
        failed_ips = []
        for expected_ip in cdn_ips:
            fallback = resolver.get_fallback_ip("cdn.haiox.ai", failed_ips=failed_ips)
            self.assertEqual(fallback, expected_ip)
            failed_ips.append(fallback)

        # Once all CDN node candidate IPs have failed, returns None to signal total outage
        self.assertIsNone(resolver.get_fallback_ip("cdn.haiox.ai", failed_ips=failed_ips))


class BoundedStreamStressTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_stream_anti_dos_immediate_halt(self):
        """Verify that a 10MB chunked stream is immediately halted at 5MB limit."""
        client = MagicMock()
        mock_stream = MagicMock()
        mock_stream.url = "https://example.test/huge"
        mock_stream.status_code = 200
        mock_stream.headers = {"content-type": "text/html"}

        # Stream 100 chunks of 100KB = 10MB total
        chunks_delivered = 0
        async def aiter_chunks():
            nonlocal chunks_delivered
            for _ in range(100):
                chunks_delivered += 1
                yield b"X" * (100 * 1024)

        mock_stream.aiter_bytes = aiter_chunks
        mock_stream.__aenter__.return_value = mock_stream
        client.stream.return_value = mock_stream

        fetcher = PageFetcher(client=client, max_response_bytes=5 * 1024 * 1024)  # 5MB limit

        with self.assertRaises(ValueError) as ctx:
            await fetcher.fetch_static("https://example.test/huge")

        self.assertEqual(str(ctx.exception), "PAGE_TOO_LARGE")
        # Ensure the stream was halted around chunk 51-52, not continuing to 100 chunks
        self.assertLessEqual(chunks_delivered, 52)
        self.assertGreaterEqual(chunks_delivered, 50)
