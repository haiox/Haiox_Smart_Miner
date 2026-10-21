"""Automated unit test assertions for Phase 3 benchmarks."""

import sys
import unittest
from pathlib import Path

scripts_dir = str(Path(__file__).parent.parent / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from benchmark_phase3 import (
    benchmark_barrier_detector,
    benchmark_resource_blocker,
    benchmark_stealth_generation,
    benchmark_visual_evidence_packaging,
    run_all_phase3_benchmarks,
)


class Phase3BenchmarkTests(unittest.TestCase):
    def test_stealth_generation_benchmark(self):
        res = benchmark_stealth_generation(iterations=50)
        self.assertEqual(res["name"], "Stealth Driver Script Synthesizer")
        self.assertGreater(res["ops_per_second"], 500)
        self.assertLess(res["avg_latency_us"], 2000.0)

    def test_resource_blocker_benchmark(self):
        res = benchmark_resource_blocker(iterations=200)
        self.assertEqual(res["name"], "Route Interception & Resource Blocker")
        self.assertGreater(res["ops_per_second"], 5000)
        self.assertLess(res["avg_latency_us"], 200.0)

    def test_barrier_detector_benchmark(self):
        res = benchmark_barrier_detector(iterations=100)
        self.assertEqual(res["name"], "Modern Bot Barrier Diagnostics")
        self.assertGreater(res["ops_per_second"], 1000)
        self.assertLess(res["avg_latency_us"], 1000.0)

    def test_visual_evidence_packaging_benchmark(self):
        res = benchmark_visual_evidence_packaging(iterations=100)
        self.assertEqual(res["name"], "Cryptographic Visual Evidence Verification")
        self.assertGreater(res["ops_per_second"], 5000)
        self.assertLess(res["avg_latency_us"], 200.0)

    def test_run_all_phase3_benchmarks_runner(self):
        results = run_all_phase3_benchmarks()
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertIn("ops_per_second", r)
            self.assertIn("avg_latency_us", r)


if __name__ == "__main__":
    unittest.main()
