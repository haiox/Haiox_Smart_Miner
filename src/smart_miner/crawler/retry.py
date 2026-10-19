"""Fault-tolerant retry engine with exponential backoff and full jitter.

Follows AWS Architecture recommendations for decorrelated full jitter
to prevent thundering herd problems on rate-limited endpoints (HTTP 429)
and transient gateway failures (HTTP 500, 502, 503, 504).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
from typing import Any, Mapping

DEFAULT_RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_DELAY: float = 0.5  # seconds
DEFAULT_MAX_DELAY: float = 10.0  # seconds

TRANSIENT_EXCEPTION_NAMES: frozenset[str] = frozenset(
    {
        "TimeoutException",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectError",
        "NetworkError",
        "RemoteProtocolError",
        "CloseError",
    }
)


def is_transient_error(exc: Exception) -> bool:
    """Determines whether an exception represents a transient network/connection failure."""
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
            ConnectionRefusedError,
            asyncio.TimeoutError,
        ),
    ):
        return True
    return type(exc).__name__ in TRANSIENT_EXCEPTION_NAMES


def parse_retry_after(header_value: str | None, max_delay: float = 60.0) -> float | None:
    """Parses HTTP 'Retry-After' header (either integer seconds or HTTP-date).

    Returns the delay in seconds clamped to max_delay, or None if unparseable.
    """
    if not header_value:
        return None

    cleaned = header_value.strip()
    if not cleaned:
        return None

    # 1. Attempt parsing as integer/float seconds
    try:
        seconds = float(cleaned)
        if seconds < 0:
            return 0.0
        return min(seconds, max_delay)
    except ValueError:
        pass

    # 2. Attempt parsing as HTTP-date (RFC 2822 / RFC 7231)
    try:
        target_dt = parsedate_to_datetime(cleaned)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        diff = (target_dt - now_dt).total_seconds()
        if diff <= 0:
            return 0.0
        return min(diff, max_delay)
    except Exception:
        return None


def calculate_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: bool = True,
) -> float:
    """Calculates exponential backoff with optional Full Jitter.

    Full Jitter formula: sleep = Uniform(0, min(max_delay, base_delay * 2^attempt))
    This spreads out concurrent scraper retries across the entire interval,
    completely eliminating synchronized retry waves.
    """
    safe_attempt = max(0, attempt)
    ceiling = min(max_delay, base_delay * (2 ** safe_attempt))
    if jitter:
        return random.uniform(0.0, ceiling)
    return ceiling


@dataclass(frozen=True)
class RetryConfig:
    """Immutable configuration for transient error retries."""

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    retry_on_status: tuple[int, ...] = DEFAULT_RETRY_STATUSES
    respect_retry_after: bool = True
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.base_delay < 0:
            raise ValueError(f"base_delay must be >= 0, got {self.base_delay}")
        if self.max_delay < self.base_delay:
            raise ValueError(
                f"max_delay ({self.max_delay}) must be >= base_delay ({self.base_delay})"
            )


class RetryEngine:
    """Manages retry decision logic, status checks, and jitter backoff."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()

    def should_retry_status(self, status_code: int) -> bool:
        """Determines if an HTTP status code qualifies as a transient failure."""
        return status_code in self.config.retry_on_status

    def get_delay(
        self,
        attempt: int,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """Calculates backoff delay, respecting server 'Retry-After' if present."""
        if self.config.respect_retry_after and headers:
            retry_after_val: str | None = None
            if hasattr(headers, "get"):
                retry_after_val = headers.get("retry-after") or headers.get("Retry-After")
            if retry_after_val:
                parsed = parse_retry_after(retry_after_val, max_delay=self.config.max_delay)
                if parsed is not None:
                    return parsed

        return calculate_backoff(
            attempt=attempt,
            base_delay=self.config.base_delay,
            max_delay=self.config.max_delay,
            jitter=self.config.jitter,
        )

    async def sleep_backoff(
        self,
        attempt: int,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """Computes backoff delay and sleeps asynchronously, returning duration slept."""
        delay = self.get_delay(attempt, headers)
        if delay > 0:
            await asyncio.sleep(delay)
        return delay
