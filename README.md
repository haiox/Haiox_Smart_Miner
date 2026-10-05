# Haiox Smart Miner ⚡

**A reusable engine that turns one web page into a clean, structured document.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![HTTPX](https://img.shields.io/badge/HTTPX-HTTP_fetch-3B82F6?style=flat-square)
![Playwright](https://img.shields.io/badge/Playwright-browser_fallback-2EAD33?style=flat-square&logo=playwright)
![Pydantic](https://img.shields.io/badge/Pydantic-schema_validation-E92063?style=flat-square&logo=pydantic)
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
Access may require an invitation. Its application source and credentials are
not part of this repository.

> **v1.3 open-core source.** Install from this repository checkout.
> A PyPI package and an official GitHub Release have not been published.

## Install

Python 3.11+ is required.

```bash
python -m pip install -e .
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
    result = await route("https://example.org/")  # A URL you trust
    if not result["success"]:
        print(result["status"], result["routing"]["reason_codes"])
        return
    print(result["routing"]["strategy"])
    print(result["document"]["markdown"])

asyncio.run(main())
```

`route()` retains the v1.2 `success`, `text` and `error` fields. The v1.3
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

The full pipeline is `CrawlOrchestrator`: fetch → detect barriers → clean →
optionally extract. You can reuse `CleanDocument` for different schemas without
fetching the page again.

## Scope and safety

- One page per run; no login flow, CAPTCHA solving or multi-page crawling.
- Challenge pages and HTTP 401/403/429 stop before extraction. Known `200` error
  pages are rejected, but barrier detection is heuristic; unknown soft blocks
  can still be missed. Check source provenance before paid model calls.
- The core `PageFetcher` is for **trusted URLs**. It does not enforce a public
  URL allowlist, block private network targets or cap response size. A hosted
  URL-input service needs its own network sandbox, URL policy and rate limits.
- Browser fallback is bounded but cannot guarantee that every AJAX page has
  finished rendering. A caller may provide a readiness selector through
  `PageFetcher` when integrating with a known site.
- Pydantic validates output shape, not factual accuracy. Page text is untrusted
  input; do not follow instructions embedded in it.
- Character counts in `CleanDocument` are **not** token counts or cost savings.

The hosted portfolio dashboard and deployment secrets are maintained
separately from this open core. No credentials or revenue-project targets are
included here.

## Contributing

Issues and focused pull requests are welcome. Run the offline suite before a
PR; the browser integration test is opt-in with
`SMART_MINER_BROWSER_TESTS=1` after installing Playwright Chromium. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development flow.

Licensed under [MIT](LICENSE). Copyright © 2026 Haiox.
