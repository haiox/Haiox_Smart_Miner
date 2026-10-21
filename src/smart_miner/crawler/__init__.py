"""HTTP/browser fetching, routing, access-barrier detection and security validation."""

from .barriers import BarrierDetector, BarrierReport, barrier_reason
from .browser_pool import BrowserPoolConfig, PlaywrightBrowserPool, PoolStats
from .dns import DNSCacheEntry, DNSResolver
from .fingerprint import BrowserProfile, FingerprintEngine, PROFILES
from .resource_blocker import BlockMetrics, RouteBlocker, RouteBlockerConfig
from .retry import (
    RetryConfig,
    RetryEngine,
    calculate_backoff,
    is_transient_error,
    parse_retry_after,
)
from .scroll import ScrollConfig, ScrollEmulator, ScrollReport
from .security import SecurityError, is_public_ip, validate_url_target
from .smart_wait import SmartWait, WaitResult
from .stealth import StealthConfig, StealthEngine
from .visual_evidence import VisualEvidence, VisualEvidenceCapture

__all__ = [
    "BarrierDetector",
    "BarrierReport",
    "BlockMetrics",
    "BrowserPoolConfig",
    "BrowserProfile",
    "DNSCacheEntry",
    "DNSResolver",
    "FingerprintEngine",
    "PROFILES",
    "PlaywrightBrowserPool",
    "PoolStats",
    "RetryConfig",
    "RetryEngine",
    "RouteBlocker",
    "RouteBlockerConfig",
    "ScrollConfig",
    "ScrollEmulator",
    "ScrollReport",
    "SecurityError",
    "SmartWait",
    "StealthConfig",
    "StealthEngine",
    "VisualEvidence",
    "VisualEvidenceCapture",
    "WaitResult",
    "barrier_reason",
    "calculate_backoff",
    "is_public_ip",
    "is_transient_error",
    "parse_retry_after",
    "validate_url_target",
]
