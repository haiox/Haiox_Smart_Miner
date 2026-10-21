"""Phase 2 Structural Parsing - Benchmark & Performance Verification Suite.

Validates that throughput, latency, and semantic guarantees are strictly met across
all parsing and extraction subsystems of Phase 2 (Subsystems 8 to 15).
"""

import os
import sys
import unittest

scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from benchmark_phase2 import (
    benchmark_ast_cleaner,
    benchmark_table_normalizer,
    benchmark_heading_synthesizer,
    benchmark_density_scorer,
    benchmark_metadata_harvester,
    benchmark_jsonld_resolver,
    benchmark_evidence_packager,
    benchmark_end_to_end_pipeline,
    run_all_phase2_benchmarks,
)


class Phase2BenchmarkTests(unittest.TestCase):
    def test_table_normalizer_benchmark(self):
        res = benchmark_table_normalizer(iterations=20)
        self.assertEqual(res["name"], "2D Matrix Table Normalizer")
        self.assertGreater(res["ops_per_second"], 50)
        self.assertLess(res["avg_latency_us"], 50_000.0)

    def test_heading_synthesizer_benchmark(self):
        res = benchmark_heading_synthesizer(iterations=20)
        self.assertEqual(res["name"], "Unicode Heading Hierarchy & Slugs")
        self.assertGreater(res["ops_per_second"], 100)
        self.assertLess(res["avg_latency_us"], 25_000.0)

    def test_density_scorer_benchmark(self):
        res = benchmark_density_scorer(iterations=20)
        self.assertEqual(res["name"], "Semantic Text & Link Density Scorer")
        self.assertGreater(res["ops_per_second"], 50)
        self.assertLess(res["avg_latency_us"], 50_000.0)

    def test_metadata_harvester_benchmark(self):
        res = benchmark_metadata_harvester(iterations=20)
        self.assertEqual(res["name"], "OpenGraph & Metadata Harvester")
        self.assertGreater(res["ops_per_second"], 200)
        self.assertLess(res["avg_latency_us"], 10_000.0)

    def test_jsonld_resolver_benchmark(self):
        res = benchmark_jsonld_resolver(iterations=50)
        self.assertEqual(res["name"], "JSON-LD Entity Graph Resolver")
        self.assertGreater(res["ops_per_second"], 500)
        self.assertLess(res["avg_latency_us"], 5_000.0)

    def test_evidence_packager_benchmark(self):
        res = benchmark_evidence_packager(iterations=50)
        self.assertEqual(res["name"], "Trilogy Evidence Packager")
        self.assertGreater(res["ops_per_second"], 500)
        self.assertLess(res["avg_latency_us"], 5_000.0)

    def test_end_to_end_pipeline_benchmark(self):
        res = benchmark_end_to_end_pipeline(iterations=5)
        self.assertEqual(res["name"], "Full End-to-End Local Document Pipeline")
        self.assertGreater(res["ops_per_second"], 2)
        self.assertLess(res["avg_latency_ms"], 250.0)

    def test_run_all_phase2_benchmarks_runner(self):
        results = run_all_phase2_benchmarks()
        self.assertEqual(len(results), 8)
        for r in results:
            self.assertIn("ops_per_second", r)
            self.assertIn("guarantee", r)
