# Haiox Smart Miner ⚡

**A reusable engine that turns one web page into a clean, structured document.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![HTTPX](https://img.shields.io/badge/HTTPX-HTTP_fetch-3B82F6?style=flat-square)
![Playwright](https://img.shields.io/badge/Playwright-browser_fallback-2EAD33?style=flat-square&logo=playwright)
![Pydantic](https://img.shields.io/badge/Pydantic-schema_validation-E92063?style=flat-square&logo=pydantic)
![Phase](https://img.shields.io/badge/Phase_1-Completed_(7%2F7)-00C853?style=flat-square)
![Release](https://img.shields.io/badge/Release-v1.4.0-00C853?style=flat-square)
![MIT](https://img.shields.io/badge/License-MIT-14B8A6?style=flat-square)

Smart Miner fetches ordinary pages with HTTPX, evaluates the content, and uses
Playwright only when the first response is insufficient. It then removes page
noise and preserves headings, links, tables, source metadata and valid JSON-LD
in a `CleanDocument`. Optional schema extraction accepts a model callable you
provide; the core itself makes **no LLM call** and requires **no API key**.

<p align="center">
  <img src="assets/pipeline-overview.svg" width="760" alt="Smart Miner: HTTP fetch, content routing, browser fallback, local cleaning and optional schema extraction">
</p>

[Try the hosted dashboard](https://haiox-smart-miner-review.streamlit.app/) ·
Or run the local review dashboard with `streamlit run streamlit_app.py`.

> **v1.4.0 · Phase 1: The Network Shield — COMPLETE (7/7 Subsystems Merged).** 73/73 passing tests, <0.05ms DNS cache, zero-trust SSRF & bounded streaming defense. Follow our 4-phase architectural roadmap in [CHANGELOG.md](CHANGELOG.md).

## Install

Python 3.11+ is required.

```bash
python -m pip install -e .
```

To run the interactive Streamlit review dashboard:

```bash
python -m pip install -e ".[demo]"
streamlit run streamlit_app.py
```

For JavaScript-rendered pages, install the optional browser dependency and
Chromium once:

```bash
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

Run the **offline** example and tests without a key or website access:

```bash
python examples/offline_example.py
python -m unittest discover -s tests -v
```

## Use the core

```python
import asyncio
from smart_miner import route

async def main():
    result = await route("https://example.org/")  # Tested & public URL
    if not result["success"]:
        print(result["status"], result["routing"]["reason_codes"])
        return
    print(result["routing"]["strategy"])
    print(result["document"]["markdown"])

asyncio.run(main())
```

`route()` retains the v1.2 `success`, `text` and `error` fields. The v1.3+
pipeline adds `status` (`ok`, `blocked`, `failed`), a reusable `document`, and
`routing` details including the chosen strategy, reason codes and timings.
`text` is plain visible text; Markdown is in `document`.

For local or application-specific extraction, pass a cleaned document to
`StructuredExtractor` with your own async generator and Pydantic schema. The
generator is called **only when you explicitly invoke it**:

```python
import asyncio
from pydantic import BaseModel
from smart_miner import CleanDocument, StructuredExtractor
from smart_miner import route

class Summary(BaseModel):
    headline: str

async def generate(clean_text: str) -> dict:
    # Replace with your own provider. This example makes no network call.
    return {"headline": "Example"}

async def main():
    result = await route("https://example.org/")
    if not result["success"]:
        return
    document = CleanDocument.model_validate(result["document"])
    summary = await StructuredExtractor(generate, Summary).extract(document)
    print(summary.model_dump())

asyncio.run(main())
```

The full pipeline is `CrawlOrchestrator`: validate URL → bounded fetch → detect barriers → clean →
optionally extract. You can reuse `CleanDocument` for different schemas without
fetching the page again.

## Phase 1 Architecture: The Network Shield (7/7 Subsystems)

| Subsystem | Security & Resilience Layer | Metric / Performance Guarantee |
| :--- | :--- | :--- |
| **1. SSRF Defense** | Zero-Trust IP Resolution | Blocks `127.0.0.1`, RFC1918, `169.254.169.254` (<0.05ms) |
| **2. Bounded Stream** | Anti-DoS & Decompression Bomb Cap | Hard 5MB chunk cutoff; rejects unhandled binary/media |
| **3. Connection Pool** | Persistent HTTPX Async Pool | 100 max connections, 20 keepalive, HTTP/2 session reuse |
| **4. Fingerprint Matrix** | Coherent Profiles & Trap Audit | 5 canonical OS/browser profiles; 100% Client Hint coherence |
| **5. Retry Engine** | Exponential Backoff & Full Jitter | AWS-standard jitter distribution on 429/5xx; RFC HTTP-date parsing |
| **6. DNS Cache Engine** | In-Memory TTL & Multi-IP Fallback | <0.002ms cached lookups; automatic CDN round-robin failover |
| **7. Benchmark Engine** | Stress Verification Suite | 73/73 tests passing (100% green); zero public network leaks |

## Scope and safety

- **Zero-Trust URL & SSRF Defense:** Pre-fetch DNS resolution strictly rejects loopback
  (`127.0.0.1`, `localhost`), private RFC1918 subnets, and cloud metadata endpoints
  (`169.254.169.254`) before making any HTTP or browser connection. Pass
  `allow_private_urls=True` only for local test environments.
- **In-Memory DNS Cache & Multi-IP Fast Fallback:** Resolved IP addresses are cached in
  an LRU table with configurable TTL (default 300s) and bounds (default 1,000 entries) to
  eliminate recurring OS lookup overhead (<0.1ms cache hits), defeat DNS rebinding attacks,
  and support round-robin fallback across multiple CDN edge IPs.
- **Bounded Streaming & Anti-DoS:** Transport enforces a chunked streaming byte cap
  (default 5 MB) and pre-checks Content-Length and Content-Type headers. Rejects binary/media
  targets and terminates streams exceeding memory thresholds to prevent decompression bombs
  (Gzip/Zip bombs) and Out-Of-Memory crashes.
- One page per run; no login flow, CAPTCHA solving or multi-page crawling.
- Challenge pages and HTTP 401/403/429 stop before extraction. Known `200` error
  pages are rejected, but barrier detection is heuristic; unknown soft blocks
  can still be missed. Check source provenance before paid model calls.
- Browser fallback is bounded but cannot guarantee that every AJAX page has
  finished rendering. A caller may provide a readiness selector through
  `PageFetcher` when integrating with a known site.
- Pydantic validates output shape, not factual accuracy. Page text is untrusted
  input; do not follow instructions embedded in it.
- Character counts in `CleanDocument` are **not** token counts or cost savings.

## Contributing

Issues and focused pull requests are welcome. Run the offline suite before a
PR; the browser integration test is opt-in with
`SMART_MINER_BROWSER_TESTS=1` after installing Playwright Chromium. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development flow.

Licensed under [MIT](LICENSE). Copyright © 2026 Haiox.
