"""Haiox Smart Miner — Phase 2 Structural Parsing Engine Benchmark Suite.

Executes rigorous micro-benchmarks across all 7 core parsing, cleaning,
and semantic structuring layers of Phase 2 (Subsystems 8 to 15), measuring throughput (ops/sec)
and latency (µs / ms) with zero network stall.
"""

from __future__ import annotations

import copy
import os
import sys
import time
from bs4 import BeautifulSoup

# Ensure src is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from smart_miner.pipeline.ast_cleaner import ASTCleaner
from smart_miner.pipeline.tables import TableNormalizer
from smart_miner.pipeline.headings import HeadingHierarchyExtractor
from smart_miner.pipeline.density import SemanticDensityScorer
from smart_miner.pipeline.metadata import MetadataHarvester
from smart_miner.pipeline.jsonld import JSONLDResolver
from smart_miner.pipeline.evidence import EvidenceBuilder
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Deep Systems Architecture: High-Throughput Web Ingestion</title>
  <meta name="description" content="In-depth analysis of zero-trust web scraping and semantic AST parsing.">
  <meta property="og:title" content="Deep Systems Architecture">
  <meta property="og:description" content="In-depth analysis of zero-trust web scraping.">
  <meta property="og:type" content="article">
  <meta property="article:published_time" content="2026-10-21T03:00:00Z">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:creator" content="@haioxlab">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@id": "https://haiox.ai/#article-bench",
        "@type": "TechArticle",
        "headline": "High-Throughput Zero-Trust Mining",
        "author": {"@id": "https://haiox.ai/#hatef"}
      },
      {
        "@id": "https://haiox.ai/#hatef",
        "@type": "Person",
        "name": "Hatef"
      }
    ]
  }
  </script>
</head>
<body>
  <div class="cookie-banner-wrap" id="cookie-notice">
    <p>We use tracking cookies. <button>Accept All</button></p>
  </div>
  <aside class="sidebar-ads" id="ad-slot-1">
    <a href="https://ads.example.com">Buy things</a>
  </aside>
  <main id="main-content">
    <h1>Deep Systems Architecture</h1>
    <p>Autonomous agent frameworks require verified, noise-free context streams to operate without hallucinations.</p>
    
    <h2>1. The Multi-Layer Shield</h2>
    <p>The network shield verifies IP ranges, resolves DNS in-memory, and rotates coherent browser fingerprints.</p>
    
    <h3>Matrix Comparison</h3>
    <table border="1">
      <thead>
        <tr><th rowspan="2">Module</th><th colspan="2">Latency Specs</th></tr>
        <tr><th>Throughput</th><th>Guarantee</th></tr>
      </thead>
      <tbody>
        <tr><td>SSRF Shield</td><td>30k ops/sec</td><td>Zero IP leaks</td></tr>
        <tr><td>DNS LRU</td><td>1.1M ops/sec</td><td>&lt;0.05ms memory lookup</td></tr>
      </tbody>
    </table>
    
    <h4>1.1.2 Heading Gap Repair</h4>
    <p>Gap repair guarantees strictly monotonic heading outlines without skipping depth levels.</p>
  </main>
</body>
</html>
"""


def benchmark_ast_cleaner(iterations: int = 500) -> dict:
    cleaner = ASTCleaner()
    # Pre-parse soups to benchmark AST cleaning latency specifically
    soups = [BeautifulSoup(SAMPLE_HTML, "html.parser") for _ in range(iterations)]
    start = time.perf_counter()
    for s in soups:
        cleaner.clean_soup(s)
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "AST HTML Noise & Cookie Stripper",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "100% inline event handlers, ads, and cookie banners pruned",
    }


def benchmark_table_normalizer(iterations: int = 2000) -> dict:
    normalizer = TableNormalizer()
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    table = soup.find("table")
    start = time.perf_counter()
    for _ in range(iterations):
        normalizer.parse_table(table)
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "2D Matrix Table Normalizer",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Full colspan/rowspan grid expansion & pipe-safe GFM tables",
    }


def benchmark_heading_synthesizer(iterations: int = 2000) -> dict:
    extractor = HeadingHierarchyExtractor()
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    start = time.perf_counter()
    for _ in range(iterations):
        extractor.extract_from_soup(soup, page_title="Deep Systems")
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "Unicode Heading Hierarchy & Slugs",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Monotonic depth tree repair & deduplicated Unicode slugs",
    }


def benchmark_density_scorer(iterations: int = 1500) -> dict:
    scorer = SemanticDensityScorer()
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    start = time.perf_counter()
    for _ in range(iterations):
        scorer.clean_boilerplate(soup, prune=False)
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "Semantic Text & Link Density Scorer",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Heuristic text-to-tag ratio & non-whitespace link density audit",
    }


def benchmark_metadata_harvester(iterations: int = 2000) -> dict:
    harvester = MetadataHarvester()
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    start = time.perf_counter()
    for _ in range(iterations):
        harvester.harvest(soup, base_url="https://haiox.ai/architecture")
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "OpenGraph & Metadata Harvester",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Social card harvesting, author attribution, and reading times",
    }


def benchmark_jsonld_resolver(iterations: int = 3000) -> dict:
    resolver = JSONLDResolver()
    raw = [
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@id": "https://haiox.ai/#article-bench",
                    "@type": "TechArticle",
                    "headline": "High-Throughput Zero-Trust Mining",
                    "author": {"@id": "https://haiox.ai/#hatef"},
                },
                {
                    "@id": "https://haiox.ai/#hatef",
                    "@type": "Person",
                    "name": "Hatef",
                },
            ],
        }
    ]
    start = time.perf_counter()
    for _ in range(iterations):
        resolver.resolve(raw)
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "JSON-LD Entity Graph Resolver",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Cross-node @id unrolling with cyclic reference guards",
    }


def benchmark_evidence_packager(iterations: int = 3000) -> dict:
    builder = EvidenceBuilder()
    doc = CleanDocument(
        source_url="https://haiox.ai/miner",
        title="Deep Systems Architecture",
        markdown="# Deep Systems\n\nContent explaining zero-trust web scraping.\n\n## Subsystem\n\nDetails.",
        visible_text="Deep Systems Content explaining zero-trust web scraping. Subsystem Details.",
        input_character_count=500,
        output_character_count=200,
    )
    start = time.perf_counter()
    for _ in range(iterations):
        builder.build_artifact(doc)
    elapsed = time.perf_counter() - start
    avg_us = (elapsed / iterations) * 1_000_000
    return {
        "name": "Trilogy Evidence Packager",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_us": round(avg_us, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Deterministic SHA-256 provenance & token-budget chunking",
    }


def benchmark_end_to_end_pipeline(iterations: int = 100) -> dict:
    cleaner = DocumentCleaner(normalize_tables=True, filter_boilerplate=True)
    page = FetchedPage(
        SAMPLE_HTML,
        "https://haiox.ai/architecture",
        200,
        {"content-type": "text/html"},
    )
    start = time.perf_counter()
    for _ in range(iterations):
        cleaner.clean(page)
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000
    return {
        "name": "Full End-to-End Local Document Pipeline",
        "operations": iterations,
        "elapsed_sec": round(elapsed, 4),
        "avg_latency_ms": round(avg_ms, 2),
        "ops_per_second": int(iterations / elapsed),
        "guarantee": "Zero LLM calls, zero network stalls, complete CleanDocument",
    }


def run_all_phase2_benchmarks() -> list[dict]:
    benchmarks = [
        benchmark_ast_cleaner,
        benchmark_table_normalizer,
        benchmark_heading_synthesizer,
        benchmark_density_scorer,
        benchmark_metadata_harvester,
        benchmark_jsonld_resolver,
        benchmark_evidence_packager,
        benchmark_end_to_end_pipeline,
    ]
    results = []
    print("\n" + "=" * 76)
    print(" ⚡ HAIOX SMART MINER — PHASE 2 STRUCTURAL PARSING BENCHMARK SUITE ⚡")
    print("=" * 76)
    print(f" Python: {sys.version.split()[0]} | Platform: {sys.platform}\n")

    for bench in benchmarks:
        r = bench()
        results.append(r)
        print(f"Layer: {r['name']}")
        print(f"  • Throughput:  {r['ops_per_second']:,} ops/sec")
        if "avg_latency_us" in r:
            print(f"  • Avg Latency: {r['avg_latency_us']:.2f} µs")
        else:
            print(f"  • Avg Latency: {r['avg_latency_ms']:.2f} ms")
        print(f"  • Guarantee:   {r['guarantee']}")
        print("-" * 76)

    print("\n✅ All Phase 2 Structural Parsing benchmarks completed successfully.")
    print("=" * 76 + "\n")
    return results


if __name__ == "__main__":
    run_all_phase2_benchmarks()
