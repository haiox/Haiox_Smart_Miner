import unittest
from smart_miner.telemetry.metrics import MinerMetrics


class TelemetryMetricsTests(unittest.TestCase):
    def setUp(self):
        self.metrics = MinerMetrics()

    def test_initial_state(self):
        self.assertEqual(self.metrics.total_requests, 0)
        self.assertEqual(self.metrics.success_rate, 100.0)
        self.assertEqual(self.metrics.avg_latency_ms, 0.0)

    def test_record_successful_static_fetch(self):
        self.metrics.record_fetch(
            success=True,
            latency_sec=0.05,
            is_dynamic=False,
            bytes_count=1024,
            dns_cached=True,
        )
        self.assertEqual(self.metrics.total_requests, 1)
        self.assertEqual(self.metrics.successful_requests, 1)
        self.assertEqual(self.metrics.failed_requests, 0)
        self.assertEqual(self.metrics.static_fetches, 1)
        self.assertEqual(self.metrics.dynamic_fetches, 0)
        self.assertEqual(self.metrics.dns_cache_hits, 1)
        self.assertEqual(self.metrics.total_bytes_fetched, 1024)
        self.assertAlmostEqual(self.metrics.avg_latency_ms, 50.0, places=1)
        self.assertEqual(self.metrics.success_rate, 100.0)

    def test_record_blocked_dynamic_fetch(self):
        self.metrics.record_fetch(
            success=False,
            latency_sec=0.2,
            is_dynamic=True,
            barrier_type="cloudflare_turnstile",
            dns_cached=False,
        )
        self.assertEqual(self.metrics.total_requests, 1)
        self.assertEqual(self.metrics.failed_requests, 1)
        self.assertEqual(self.metrics.blocked_requests, 1)
        self.assertEqual(self.metrics.dynamic_fetches, 1)
        self.assertEqual(self.metrics.dns_cache_misses, 1)
        self.assertEqual(self.metrics.barrier_detections["cloudflare_turnstile"], 1)
        self.assertEqual(self.metrics.success_rate, 0.0)

    def test_to_prometheus_format(self):
        self.metrics.record_fetch(success=True, latency_sec=0.01, is_dynamic=False)
        prom_text = self.metrics.to_prometheus_format()
        self.assertIn("haiox_smart_miner_requests_total 1", prom_text)
        self.assertIn("haiox_smart_miner_requests_success_total 1", prom_text)
        self.assertIn("haiox_smart_miner_latency_ms_avg", prom_text)

    def test_to_dict(self):
        d = self.metrics.to_dict()
        self.assertIn("total_requests", d)
        self.assertIn("success_rate_pct", d)
        self.assertIn("barrier_detections", d)


if __name__ == "__main__":
    unittest.main()
