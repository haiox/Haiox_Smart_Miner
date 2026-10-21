"""
Haiox Smart Miner - Subsystem 23: Production CLI Engine
Provides unified command-line interface for web crawling, local microservice hosting,
and architectural micro-benchmarking.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional

from smart_miner import __version__
from smart_miner.crawler.router import route


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-miner",
        description="Haiox Smart Miner ⚡ Zero-Trust Ingestion & Structural Parsing Engine (v2.0.0)",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"Haiox Smart Miner v{__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: crawl
    crawl_p = subparsers.add_parser("crawl", help="Ingest and parse a target webpage")
    crawl_p.add_argument("url", help="Target URL to crawl")
    crawl_p.add_argument("--dynamic", "-d", action="store_true", help="Enable Playwright headless browser execution")
    crawl_p.add_argument("--fingerprint", "-f", default="chrome_windows", help="Browser fingerprint profile")
    crawl_p.add_argument(
        "--format",
        choices=["markdown", "json", "summary"],
        default="markdown",
        help="Output display format (default: markdown)",
    )
    crawl_p.add_argument("--output", "-o", help="Save output to a destination file")
    crawl_p.add_argument("--verbose", "-v", action="store_true", help="Print routing diagnostics")

    # Command: serve
    serve_p = subparsers.add_parser("serve", help="Launch the FastAPI microservice")
    serve_p.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    serve_p.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_p.add_argument("--workers", type=int, default=1, help="Number of worker processes")

    # Command: benchmark
    bench_p = subparsers.add_parser("benchmark", help="Run local architectural micro-benchmarks")
    bench_p.add_argument(
        "--phase",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Select benchmark phase to run",
    )

    return parser


async def run_crawl_command(args: argparse.Namespace) -> int:
    try:
        res = await route(
            args.url,
            fingerprint=args.fingerprint,
        )
    except Exception as exc:
        sys.stderr.write(f"[ERROR] Crawl failed: {exc}\n")
        return 1

    if res.get("status") != "success":
        sys.stderr.write(f"[FAILURE] Crawl unsuccessful: {res.get('error')}\n")
        return 2

    doc = res.get("document", {})
    ev = res.get("evidence", {})

    output_content = ""
    if args.format == "markdown":
        output_content = doc.get("markdown", "")
    elif args.format == "json":
        output_content = json.dumps(res, indent=2, ensure_ascii=False)
    elif args.format == "summary":
        output_content = (
            f"Title: {doc.get('title')}\n"
            f"Author: {doc.get('author')}\n"
            f"Reading Time: {doc.get('reading_time_minutes')} min\n"
            f"SHA256: {ev.get('document_sha256')}\n"
            f"Chunks: {len(ev.get('chunks', []))}\n"
        )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_content)
        sys.stdout.write(f"[OK] Output saved to {args.output}\n")
    else:
        sys.stdout.write(output_content + "\n")

    if args.verbose:
        sys.stderr.write(f"\n[DIAGNOSTICS] Routing: {json.dumps(res.get('routing', {}))}\n")

    return 0


def run_serve_command(args: argparse.Namespace) -> int:
    try:
        import uvicorn
        from smart_miner.api.app import app
        sys.stdout.write(f"[*] Starting Haiox Smart Miner Microservice on http://{args.host}:{args.port}...\n")
        uvicorn.run(app, host=args.host, port=args.port, workers=args.workers)
        return 0
    except ImportError:
        sys.stderr.write("[ERROR] uvicorn is required to run the server. Install via pip install uvicorn.\n")
        return 1


def run_benchmark_command(args: argparse.Namespace) -> int:
    import subprocess
    cmd = [sys.executable, "-m", "unittest"]
    if args.phase == "1":
        cmd.append("tests/test_benchmark_phase1.py")
    elif args.phase == "2":
        cmd.append("tests/test_benchmark_phase2.py")
    elif args.phase == "3":
        cmd.append("tests/test_benchmark_phase3.py")
    else:
        cmd.extend(["discover", "-s", "tests", "-p", "test_benchmark*.py"])

    sys.stdout.write(f"[*] Executing benchmarks for Phase {args.phase}...\n")
    return subprocess.call(cmd)


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "crawl":
        return asyncio.run(run_crawl_command(args))
    elif args.command == "serve":
        return run_serve_command(args)
    elif args.command == "benchmark":
        return run_benchmark_command(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
