from time import perf_counter

import httpx

if __package__ == "pipeline":
    from crawler.barriers import barrier_reason
    from crawler.fetcher import PageFetcher
    from crawler.router import evaluate_content_quality, _extract_visible_text
else:
    from ..crawler.barriers import barrier_reason
    from ..crawler.fetcher import PageFetcher
    from ..crawler.router import evaluate_content_quality, _extract_visible_text
from .document import DocumentCleaner


SAFE_FAILURE_CODES = {
    "PAGE_TOO_LARGE", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT",
    "DNS_LOOKUP_FAILED", "NON_PUBLIC_ADDRESS", "URL_NOT_ALLOWED",
    "IP_LITERAL_NOT_ALLOWED", "BROWSER_UNAVAILABLE",
    "INVALID_WAIT_SELECTOR", "WAIT_SELECTOR_TIMEOUT",
    "UNSUPPORTED_CONTENT_TYPE",
}


def failure_reason(exc):
    """Expose a stable code, never a raw URL, response body or credential."""
    if isinstance(exc, ValueError):
        code = str(exc)
        if code in SAFE_FAILURE_CODES or code.startswith("HTTP_STATUS_"):
            return code
    if isinstance(exc, httpx.TimeoutException):
        return "FETCH_TIMEOUT"
    if isinstance(exc, httpx.ConnectError):
        return "FETCH_CONNECTION_ERROR"
    if isinstance(exc, TimeoutError):
        return "BROWSER_TIMEOUT"
    # Playwright wraps navigation failures in its own Error class. Keep the
    # diagnostic useful without exposing the target URL or browser internals.
    if type(exc).__module__.startswith("playwright."):
        if type(exc).__name__ == "TimeoutError":
            return "BROWSER_TIMEOUT"
        return "BROWSER_NAVIGATION_FAILED"
    return "ROUTING_ERROR"


class CrawlOrchestrator:
    def __init__(self, fetcher=None, cleaner=None):
        self.fetcher = fetcher or PageFetcher()
        self.cleaner = cleaner or DocumentCleaner()

    async def run(self, url, min_text_length=600, extractor=None, *,
                  force_dynamic=False, require_clean_content=False):
        started = perf_counter()
        timings = {"static": 0.0, "dynamic": 0.0, "total": 0.0}
        fallback = False
        reasons = ["ROUTING_ERROR"]
        strategy = "static"
        static_page = None
        result = {"success": False, "text": "", "error": None,
                  "status": "failed", "document": None}
        try:
            if min_text_length < 0:
                raise ValueError("min_text_length must be non-negative")
            for strategy in (("dynamic",) if force_dynamic else ("static", "dynamic")):
                fallback = strategy == "dynamic"
                tick = perf_counter()
                try:
                    page = await getattr(self.fetcher, f"fetch_{strategy}")(url)
                finally:
                    timings[strategy] = round((perf_counter() - tick) * 1000, 2)
                blocked = barrier_reason(page)
                if blocked:
                    reasons = [blocked]
                    result.update(status="blocked", error=blocked)
                    break
                if page.status_code >= 400:
                    raise ValueError(f"HTTP_STATUS_{page.status_code}")
                text = _extract_visible_text(page.html)
                document = (self.cleaner.clean(page, structured_fallback=False)
                            if require_clean_content else None)
                quality = evaluate_content_quality(
                    document.visible_text if document else text, min_text_length)
                if require_clean_content:
                    if not document.markdown.strip():
                        quality["reason_codes"].append("EMPTY_CLEAN_DOCUMENT")
                    lowered = document.visible_text.casefold()
                    if (len(document.visible_text) < 1000 and "cookie" in lowered and
                            ("accept all" in lowered or "cookie settings" in lowered)):
                        quality["reason_codes"].append("COOKIE_NOTICE_ONLY")
                if strategy == "static" and quality["reason_codes"]:
                    reasons = quality["reason_codes"]
                    static_page = page
                    continue
                if strategy == "dynamic" and require_clean_content and quality["reason_codes"]:
                    backup = (self.cleaner.clean(static_page, structured_fallback=True)
                              if static_page else None)
                    if (backup and "STRUCTURED_DATA_FALLBACK" in backup.warnings and
                            evaluate_content_quality(
                                backup.visible_text, min_text_length)["accepted"]):
                        strategy = "metadata"
                        reasons = ["BROWSER_CONTENT_UNAVAILABLE",
                                   "STRUCTURED_DATA_FALLBACK"]
                        result.update(success=True, status="ok",
                                      text=backup.visible_text,
                                      document=backup.model_dump())
                        if extractor is not None:
                            extracted = await extractor.extract(backup)
                            result["extraction"] = extracted.model_dump()
                    else:
                        reasons = quality["reason_codes"]
                        result.update(status="failed",
                                      error="INSUFFICIENT_CLEAN_CONTENT")
                    break
                if strategy == "static":
                    reasons = ["STATIC_QUALITY_ACCEPTED"]
                elif force_dynamic:
                    reasons = ["BROWSER_REQUESTED"]
                document = document or self.cleaner.clean(page)
                if require_clean_content:
                    text = document.visible_text
                result.update(success=True, status="ok", text=text,
                              document=document.model_dump())
                if extractor is not None:
                    extracted = await extractor.extract(document)
                    result["extraction"] = extracted.model_dump()
                break
        except Exception as exc:
            # Do not leak URLs, headers, cookies or provider response bodies in errors.
            result.update(success=False, status="failed", error=type(exc).__name__)
            reasons = [failure_reason(exc)]
        timings["total"] = round((perf_counter() - started) * 1000, 2)
        result["routing"] = {
            "strategy": strategy if result["success"] else "failed",
            "fallback_used": fallback, "reason_codes": reasons,
            "browser_attempted": fallback or force_dynamic,
            "visible_character_count": len(result["text"].strip()), "timing_ms": timings,
        }
        return result
