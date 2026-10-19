"""Dynamic Browser Fingerprint Matrix & Stealth Header Engine.

Generates coherent, mathematically consistent browser fingerprints across
Chrome, Edge, Firefox, and Safari to prevent WAF and bot-defense heuristics
from detecting synthetic or mismatched client headers.
"""

from dataclasses import dataclass, field
import hashlib
import random
import re
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BrowserProfile:
    name: str
    browser: str
    os_name: str
    user_agent: str
    headers: Dict[str, str]
    weight: float = 1.0


# -------------------------------------------------------------------------
# Modern 2026 Realistic Fingerprint Profiles
# -------------------------------------------------------------------------

_CHROME_WINDOWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_CHROME_MACOS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_EDGE_WINDOWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Ch-Ua": '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Note: Firefox strictly DOES NOT send Sec-Ch-Ua / Client Hints.
_FIREFOX_WINDOWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
        "Gecko/20100101 Firefox/132.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Note: Safari on macOS strictly DOES NOT send Sec-Ch-Ua.
_SAFARI_MACOS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.1 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

PROFILES: Dict[str, BrowserProfile] = {
    "chrome_windows": BrowserProfile(
        name="chrome_windows",
        browser="chrome",
        os_name="windows",
        user_agent=_CHROME_WINDOWS_HEADERS["User-Agent"],
        headers=_CHROME_WINDOWS_HEADERS,
        weight=0.50,
    ),
    "chrome_macos": BrowserProfile(
        name="chrome_macos",
        browser="chrome",
        os_name="macos",
        user_agent=_CHROME_MACOS_HEADERS["User-Agent"],
        headers=_CHROME_MACOS_HEADERS,
        weight=0.20,
    ),
    "edge_windows": BrowserProfile(
        name="edge_windows",
        browser="edge",
        os_name="windows",
        user_agent=_EDGE_WINDOWS_HEADERS["User-Agent"],
        headers=_EDGE_WINDOWS_HEADERS,
        weight=0.15,
    ),
    "firefox_windows": BrowserProfile(
        name="firefox_windows",
        browser="firefox",
        os_name="windows",
        user_agent=_FIREFOX_WINDOWS_HEADERS["User-Agent"],
        headers=_FIREFOX_WINDOWS_HEADERS,
        weight=0.10,
    ),
    "safari_macos": BrowserProfile(
        name="safari_macos",
        browser="safari",
        os_name="macos",
        user_agent=_SAFARI_MACOS_HEADERS["User-Agent"],
        headers=_SAFARI_MACOS_HEADERS,
        weight=0.05,
    ),
}


class FingerprintEngine:
    """Enterprise-grade browser fingerprint generation, rotation and consistency validator."""

    def __init__(self, default_profile: str = "chrome_windows"):
        if default_profile not in PROFILES:
            raise ValueError(f"Unknown default profile: {default_profile}. Available: {list(PROFILES.keys())}")
        self.default_profile = default_profile

    def get_profile(self, name: Optional[str] = None) -> BrowserProfile:
        """Retrieve a specific browser profile by name, or fall back to default."""
        profile_name = name or self.default_profile
        if profile_name not in PROFILES:
            raise ValueError(f"Unknown profile: {profile_name}. Available: {list(PROFILES.keys())}")
        return PROFILES[profile_name]

    def get_random_profile(self, seed: Optional[Any] = None) -> BrowserProfile:
        """Select a realistic profile weighted by modern real-world browser market share.
        
        If seed is provided (e.g. domain name or session ID), the selection is
        deterministic (Session Affinity).
        """
        keys = list(PROFILES.keys())
        weights = [PROFILES[k].weight for k in keys]
        if seed is not None:
            # Deterministic hash seed
            seed_bytes = str(seed).encode("utf-8")
            int_seed = int(hashlib.sha256(seed_bytes).hexdigest()[:8], 16)
            rng = random.Random(int_seed)
            selected_key = rng.choices(keys, weights=weights, k=1)[0]
        else:
            selected_key = random.choices(keys, weights=weights, k=1)[0]
        return PROFILES[selected_key]

    def build_headers(
        self,
        profile: Optional[BrowserProfile | str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Construct a full header set adhering to profile consistency rules."""
        if isinstance(profile, str):
            prof = self.get_profile(profile)
        elif isinstance(profile, BrowserProfile):
            prof = profile
        else:
            prof = self.get_profile(self.default_profile)

        # Base profile headers
        final_headers = dict(prof.headers)

        # Merge custom headers without breaking fundamental platform coherence
        if custom_headers:
            final_headers.update(custom_headers)

        return final_headers

    @staticmethod
    def validate_consistency(headers: Dict[str, str]) -> List[str]:
        """Audit headers for anti-bot mismatch traps (e.g., Firefox with Sec-Ch-Ua, OS platform mismatches)."""
        issues: List[str] = []
        ua = headers.get("User-Agent", "")
        sec_ch_ua = headers.get("Sec-Ch-Ua", "")
        sec_ch_platform = headers.get("Sec-Ch-Ua-Platform", "").strip('"')

        # Rule 1: Firefox strictly does NOT send Sec-Ch-Ua
        if "Firefox" in ua and sec_ch_ua:
            issues.append("FIREFOX_WITH_CLIENT_HINTS")

        # Rule 2: Safari strictly does NOT send Sec-Ch-Ua
        if "Safari" in ua and "Chrome" not in ua and "Edg" not in ua and sec_ch_ua:
            issues.append("SAFARI_WITH_CLIENT_HINTS")

        # Rule 3: OS platform mismatch between User-Agent and Sec-Ch-Ua-Platform
        if sec_ch_platform:
            if "Windows" in sec_ch_platform and "Windows" not in ua:
                issues.append("PLATFORM_MISMATCH_EXPECTED_WINDOWS")
            elif "macOS" in sec_ch_platform and "Macintosh" not in ua:
                issues.append("PLATFORM_MISMATCH_EXPECTED_MACOS")

        # Rule 4: Edge brand in Client Hints must match Edg in User-Agent
        if "Microsoft Edge" in sec_ch_ua and "Edg/" not in ua:
            issues.append("BRAND_MISMATCH_EDGE")

        return issues
