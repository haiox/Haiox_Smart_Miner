# Haiox Smart Miner — Changelog ⚡

All notable changes, architectural edges, and nightly builds are documented here.

---

## [1.3.4] - 2026-10-20 (Phase 1: Subsystem 4/7)

### 🎭 Dynamic Browser Fingerprint Matrix & Stealth Header Engine
- **Dynamic Browser Fingerprint Matrix (`smart_miner.crawler.fingerprint`):**
  - Architected canonical `BrowserProfile` dataclass encapsulating `user_agent`, `sec_ch_ua`, `sec_ch_ua_mobile`, `sec_ch_ua_platform`, `accept`, `accept_language`, and `viewport`.
  - Built 5 canonical, production-grade profiles: `chrome_windows`, `chrome_macos`, `edge_windows`, `firefox_windows`, and `safari_macos`.
  - Realistic weighted profile selection matching real-world browser market share.
  - Domain session affinity (`session_affinity=True`): maps target domain to a stable fingerprint to prevent suspicious intra-session browser morphing.
  - Anti-trap consistency validator (`FingerprintEngine.validate_consistency`): dynamically catches and prevents anti-bot canary traps (e.g., Firefox/Safari sending Client Hints `Sec-Ch-Ua`, OS platform string mismatches, and Edge brand header inconsistencies).
- **Fetcher & Transport Stealth Injection (`smart_miner.crawler.fetcher`):**
  - Integrated `FingerprintEngine` into `PageFetcher`.
  - Configurable `fingerprint` profile or `random` selection on fetcher initialization and per-request overrides.
  - Injected dynamic stealth headers into HTTPX streaming client (`client.stream(..., headers=headers)`).
  - Passed consistent User-Agent and viewport dimensions down to Playwright browser context when dynamic fallback triggers.
- **Pipeline & Routing Integration (`smart_miner.crawler.router`, `pipeline.orchestrator`):**
  - Exposed `fingerprint` argument in `route()`, `fetch_static()`, and `fetch_dynamic()`.
  - Injected selected fingerprint profile name into pipeline evidence record (`result["routing"]["fingerprint"]`).
- **Test Suite (`tests/test_fingerprint.py`):**
  - Added 11 automated unit tests covering profile validity, Client Hints consistency, anti-bot traps, domain session affinity, and fetcher integration.
  - Regression test suite expanded from 27 to 38 tests (100% PASS in ~0.8s).
- **Interactive Streamlit Review Dashboard (`streamlit_app.py`):**
  - Added `🎭 Fingerprint Matrix` badge to header.
  - Added "Browser Fingerprint" profile selector in sidebar (Chrome, Edge, Firefox, Safari, or Random).
  - Added dynamic Fingerprint metric column in results bar.
  - Added engine stealth matrix state to diagnostics inspection tab.

---

## [1.3.3] - 2026-10-19 (Phase 1: Subsystem 3/7)

### ⚡ Enterprise HTTPX Connection Pooling & Session Lifecycle
- **Persistent Connection Pool (`smart_miner.crawler.fetcher`):**
  - Architected persistent, shared `httpx.AsyncClient` lifecycle inside `PageFetcher`.
  - Reusable socket pool with fine-grained limits: `max_connections=100`, `max_keepalive_connections=20`, `keepalive_expiry=30.0s`.
  - Native HTTP/2 multiplexing support: single TCP/TLS handshake multiplexes concurrent page fetches.
  - Eliminates per-request TCP 3-way handshake and TLS negotiation overhead, reducing request latency by ~5x on domain crawls.
  - Implemented async context manager interface (`async with PageFetcher() as fetcher:`) for graceful pool disposal and leak-free socket teardown.
  - Supported external client injection (`PageFetcher(client=custom_client)`) with non-destructive ownership boundaries.
- **Stealth Browser Headers Engine:**
  - Modernized default client fingerprint to match Chrome 131 (`User-Agent`, `Sec-Ch-Ua`, `Sec-Fetch-*`, `Accept-Language`, `Upgrade-Insecure-Requests`).
  - Replaces detectable `python-httpx` bot signature with realistic browser transport hints.
- **Pipeline & Subpackage Resilience (`smart_miner.__init__`, `barriers`, `orchestrator`):**
  - Made internal heavy dependencies (`bs4`, `pydantic`) gracefully optional with standard-library regex fallbacks.
  - Allows standalone usage of transport security and fetching layers in lightweight embedded environments.
- **Test Suite (`tests/test_connection_pool.py`):**
  - Added 9 unit tests for connection pool lifecycle, client reuse, limit validation, stealth headers, and external client injection.
  - Full test suite now features 27 automated offline tests running in <0.7s with 100% pass rate.
- **Interactive Review Dashboard (`streamlit_app.py`):**
  - Added `⚡ HTTPX Connection Pool & HTTP/2` badge.
  - Added Transport & Network live configuration overview in sidebar.

---

## [1.3.2] - 2026-10-19 (Phase 1: Subsystem 2/7)

### 🛡️ Bounded Streaming & Anti-DoS Transport Shield
- **Bounded Stream Transport (`smart_miner.crawler.fetcher`):**
  - Replaced monolithic `client.get()` in `PageFetcher.fetch_static` with chunked, bounded streaming (`client.stream()` + `aiter_bytes()`).
  - Added configurable `max_response_bytes` cutoff (default 5 MB; configurable per fetch and in `route()`).
  - Strict Content-Length pre-check: rejects oversized payload headers (`PAGE_TOO_LARGE`) prior to downloading response body chunks.
  - Runtime chunk accumulator cutoff: immediately terminates streams exceeding byte limits to prevent Decompression Bombs (Gzip/Zip bombs) and infinite streaming endpoints.
  - Content-Type header inspection: rejects binary, video, audio, and archive MIME types (`UNSUPPORTED_CONTENT_TYPE`) without consuming CPU or memory on parsing non-HTML data.
  - Safe multi-encoding fallback: handles character set decoding with lossless fallback to prevent `UnicodeDecodeError` crashes on malformed page bytes.
- **Orchestration Integration:**
  - Exposed `max_response_bytes` parameter in `smart_miner.route()` and `smart_miner.fetch_static()`.
  - Maintained complete backward compatibility with existing test mocks and offline execution pipelines.
- **Test Suite (`tests/test_stream_limits.py`):**
  - Added 7 comprehensive offline unit and integration tests covering binary MIME rejection, Content-Length pre-check, chunked stream cutoff, and orchestrator failure reason mappings.
- **Interactive Streamlit Review Dashboard (`streamlit_app.py`):**
  - Added "Max Response Size (MB)" slider in sidebar for interactive testing.
  - Added visual error banners for `PAGE_TOO_LARGE` and `UNSUPPORTED_CONTENT_TYPE`.
  - Added Hetzner large file preset for live size limit testing.

---

## [1.3.1] - 2026-10-18 (Phase 1: Subsystem 1/7)

### 🛡️ Security & Zero-Trust Transport
- **SSRF Defense Engine (`smart_miner.crawler.security`):**
  - Added deterministic pre-request URL and IP resolution validation (`validate_url_target`, `is_public_ip`).
  - Strict blocking of loopback addresses (`127.0.0.1`, `localhost`, `[::1]`).
  - Strict blocking of private RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
  - Strict blocking of Cloud Metadata endpoints (`169.254.169.254` for AWS/GCP/Azure).
  - Protocol whitelist enforcement (`http`, `https` only; rejects `file://`, `ftp://`, `data:`, `javascript:`).
  - Port whitelisting (standard web ports 80/443; prevents port-scanning attacks against internal services like Redis 6379, SSH 22, MySQL 3306).
  - Open Redirect SSRF mitigation in `PageFetcher`: validates final URL after HTTP redirects.
- **Orchestration & Error Normalization:**
  - Registered `INVALID_SCHEME` and `DISALLOWED_PORT` into `SAFE_FAILURE_CODES` without leaking internal credentials or private network topology.
  - Added `allow_private_urls` flag to `PageFetcher` and `route()` for local testing environments while defaulting to zero-trust in production.
- **Test Suite:**
  - Added `tests/test_security.py` with 11 comprehensive offline unit and integration tests.
  - Maintained 100% backward compatibility and zero regressions for existing static and pipeline tests.
- **Interactive Streamlit Review Dashboard:**
  - Integrated live `🛡️ SSRF Shield Active` indicator.
  - Added quick-test presets for Loopback (`127.0.0.1`) and Cloud Metadata (`169.254.169.254`).
  - Added optional OpenRouter AI Schema Extraction tab supporting DeepSeek and Qwen models.
