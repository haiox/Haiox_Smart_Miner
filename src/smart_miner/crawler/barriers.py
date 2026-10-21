"""Conservative, explicitly heuristic access-barrier detection and diagnostics.

Identifies Cloudflare Turnstile, Cloudflare Managed Challenge, Datadome, reCAPTCHA,
hCaptcha, AWS WAF, and HTTP access blocking errors, returning actionable mitigation
recommendations for downstream orchestration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover
    BeautifulSoup = None


@dataclass
class BarrierReport:
    """Detailed diagnostics of barrier inspection."""

    is_blocked: bool
    barrier_type: str
    confidence: float
    suggested_action: str
    details: str

    def to_dict(self) -> dict:
        return {
            "is_blocked": self.is_blocked,
            "barrier_type": self.barrier_type,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "details": self.details,
        }


class BarrierDetector:
    """Inspects fetched HTML documents and response codes for active bot barriers."""

    # Cloudflare Turnstile patterns
    TURNSTILE_PATTERNS = (
        r"challenges\.cloudflare\.com/turnstile",
        r"cf-turnstile",
        r"turnstile-container",
        r"data-turnstile",
    )

    # Cloudflare Managed Challenge / WAF patterns
    CF_CHALLENGE_PATTERNS = (
        r"cf-challenge-running",
        r"challenge-form",
        r"cf-browser-verification",
        r"cf-please-wait",
        r"cloudflare-challenge",
        r"__cf_chl_opt",
        r"cfl_opt",
    )

    # Datadome patterns
    DATADOME_PATTERNS = (
        r"geo\.captcha-delivery\.com",
        r"datadome\.js",
        r"window\.datadome",
    )

    # AWS WAF patterns
    AWS_WAF_PATTERNS = (
        r"token\.awswaf\.com",
        r"aws-waf-captcha",
    )

    # General Captcha patterns
    GENERAL_CAPTCHA_PATTERNS = (
        r"recaptcha/api\.js",
        r"hcaptcha\.com/1/api\.js",
        r"class=[\"'].*?g-recaptcha",
        r"class=[\"'].*?h-captcha",
    )

    @classmethod
    def detect(cls, page: Any) -> BarrierReport:
        """Run comprehensive barrier diagnostics against the fetched page."""
        raw_html = getattr(page, "html", "") or ""
        status_code = getattr(page, "status_code", 200)

        # 1. Check HTTP Status Codes
        if status_code in {401, 403, 429}:
            return BarrierReport(
                is_blocked=True,
                barrier_type="ACCESS_BLOCKED",
                confidence=1.0,
                suggested_action="ROTATE_IP",
                details=f"HTTP {status_code} status code encountered.",
            )

        # 2. Check Cloudflare Turnstile
        for pattern in cls.TURNSTILE_PATTERNS:
            if re.search(pattern, raw_html, re.IGNORECASE):
                return BarrierReport(
                    is_blocked=True,
                    barrier_type="CLOUDFLARE_TURNSTILE",
                    confidence=0.95,
                    suggested_action="ACTIVATE_STEALTH",
                    details=f"Matched Turnstile pattern: {pattern}",
                )

        # 3. Check Cloudflare Managed Challenge
        for pattern in cls.CF_CHALLENGE_PATTERNS:
            if re.search(pattern, raw_html, re.IGNORECASE):
                return BarrierReport(
                    is_blocked=True,
                    barrier_type="CLOUDFLARE_CHALLENGE",
                    confidence=0.95,
                    suggested_action="ACTIVATE_STEALTH",
                    details=f"Matched CF Challenge pattern: {pattern}",
                )

        # 4. Check Datadome
        for pattern in cls.DATADOME_PATTERNS:
            if re.search(pattern, raw_html, re.IGNORECASE):
                return BarrierReport(
                    is_blocked=True,
                    barrier_type="DATADOME",
                    confidence=0.98,
                    suggested_action="ROTATE_IP",
                    details="Datadome bot challenge detected.",
                )

        # 5. Check AWS WAF
        for pattern in cls.AWS_WAF_PATTERNS:
            if re.search(pattern, raw_html, re.IGNORECASE):
                return BarrierReport(
                    is_blocked=True,
                    barrier_type="AWS_WAF",
                    confidence=0.95,
                    suggested_action="ROTATE_IP",
                    details="AWS WAF captcha integration detected.",
                )

        # 6. Check standard Captchas
        for pattern in cls.GENERAL_CAPTCHA_PATTERNS:
            if re.search(pattern, raw_html, re.IGNORECASE):
                return BarrierReport(
                    is_blocked=True,
                    barrier_type="CAPTCHA_OR_CHALLENGE",
                    confidence=0.90,
                    suggested_action="ROTATE_IP",
                    details="reCAPTCHA or hCaptcha iframe found.",
                )

        # 7. Check Text Phrases & Titles
        legacy_reason = barrier_reason(page)
        if legacy_reason:
            action = "ROTATE_IP" if legacy_reason == "ACCESS_BLOCKED" else (
                "FALLBACK_STATIC" if legacy_reason == "SOFT_ERROR_PAGE" else "ACTIVATE_STEALTH"
            )
            return BarrierReport(
                is_blocked=True,
                barrier_type=legacy_reason,
                confidence=0.85,
                suggested_action=action,
                details=f"Matched legacy heuristic: {legacy_reason}",
            )

        return BarrierReport(
            is_blocked=False,
            barrier_type="NONE",
            confidence=1.0,
            suggested_action="PROCEED",
            details="No barrier detected.",
        )


def barrier_reason(page: Any) -> Optional[str]:
    """Legacy backward-compatible heuristic function."""
    html = getattr(page, "html", "") or ""
    status_code = getattr(page, "status_code", 200)

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        text = soup.get_text(" ", strip=True).casefold()
        title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
        heading = soup.h1.get_text(" ", strip=True).casefold() if soup.h1 else ""
        challenge = soup.select_one(
            'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], '
            '.g-recaptcha, .h-captcha, #challenge-form, #cf-challenge-running'
        )
    else:  # pragma: no cover
        clean_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", clean_html).casefold()
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
        title = title_m.group(1).strip().casefold() if title_m else ""
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.DOTALL | re.IGNORECASE)
        heading = h1_m.group(1).strip().casefold() if h1_m else ""
        challenge = bool(re.search(r"recaptcha|hcaptcha|challenge-form|cf-challenge-running", html, flags=re.IGNORECASE))

    phrases = r"verify (?:that )?you are (?:a )?human|complete the captcha|checking your browser|confirm you are human"
    if challenge or re.search(phrases, text) or title in {"just a moment...", "access denied"}:
        return "CAPTCHA_OR_CHALLENGE"
    if status_code in {401, 403, 429}:
        return "ACCESS_BLOCKED"

    error_titles = {"404", "404 not found", "page not found", "not found", "error 404"}
    if title in error_titles or heading in error_titles:
        return "SOFT_ERROR_PAGE"
    if title.startswith(("access denied - ", "access denied | ")):
        return "ACCESS_BLOCKED"
    return None
