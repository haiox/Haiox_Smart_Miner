# Haiox Smart Miner — Changelog ⚡

All notable changes, architectural edges, and nightly builds are documented here.

---

## [1.3.1] - 2026-10-18 (Night 1 / 30)

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
