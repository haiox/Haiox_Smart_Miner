"""
Haiox Smart Miner - Subsystem 26: Telemetry & Prometheus Metrics
Tracks real-time crawl counts, latencies, memory footprint, and barrier triggers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class MinerMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    blocked_requests: int = 0
    static_fetches: int = 0
    dynamic_fetches: int = 0
    dns_cache_hits: int = 0
    dns_cache_misses: int = 0
    total_bytes_fetched: int = 0
    total_latency_seconds: float = 0.0
    barrier_detections: Dict[str, int] = field(default_factory=lambda: {
        "cloudflare_turnstile": 0,
        "cloudflare_managed": 0,
        "datadome": 0,
        "aws_waf": 0,
        "generic": 0,
    })

    def record_fetch(
        self,
        success: bool,
        latency_sec: float,
        is_dynamic: bool,
        bytes_count: int = 0,
        barrier_type: str | None = None,
        dns_cached: bool = False,
    ) -> None:
        self.total_requests += 1
        self.total_latency_seconds += latency_sec
        self.total_bytes_fetched += bytes_count

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        if is_dynamic:
            self.dynamic_fetches += 1
        else:
            self.static_fetches += 1

        if dns_cached:
            self.dns_cache_hits += 1
        else:
            self.dns_cache_misses += 1

        if barrier_type:
            self.blocked_requests += 1
            key = barrier_type.lower()
            if key in self.barrier_detections:
                self.barrier_detections[key] += 1
            else:
                self.barrier_detections["generic"] += 1

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.total_latency_seconds / self.total_requests) * 1000.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0

    def to_prometheus_format(self) -> str:
        """Render metrics in standard Prometheus text format."""
        lines = [
            "# HELP haiox_smart_miner_requests_total Total number of crawl requests processed",
            "# TYPE haiox_smart_miner_requests_total counter",
            f"haiox_smart_miner_requests_total {self.total_requests}",
            "",
            "# HELP haiox_smart_miner_requests_success_total Successful crawl requests",
            "# TYPE haiox_smart_miner_requests_success_total counter",
            f"haiox_smart_miner_requests_success_total {self.successful_requests}",
            "",
            "# HELP haiox_smart_miner_requests_failed_total Failed crawl requests",
            "# TYPE haiox_smart_miner_requests_failed_total counter",
            f"haiox_smart_miner_requests_failed_total {self.failed_requests}",
            "",
            "# HELP haiox_smart_miner_requests_blocked_total Requests blocked by bot barriers",
            "# TYPE haiox_smart_miner_requests_blocked_total counter",
            f"haiox_smart_miner_requests_blocked_total {self.blocked_requests}",
            "",
            "# HELP haiox_smart_miner_bytes_fetched_total Total raw bytes ingested",
            "# TYPE haiox_smart_miner_bytes_fetched_total counter",
            f"haiox_smart_miner_bytes_fetched_total {self.total_bytes_fetched}",
            "",
            "# HELP haiox_smart_miner_latency_ms_avg Average request processing latency in ms",
            "# TYPE haiox_smart_miner_latency_ms_avg gauge",
            f"haiox_smart_miner_latency_ms_avg {self.avg_latency_ms:.2f}",
            "",
            "# HELP haiox_smart_miner_dns_cache_hits_total DNS cache hits",
            "# TYPE haiox_smart_miner_dns_cache_hits_total counter",
            f"haiox_smart_miner_dns_cache_hits_total {self.dns_cache_hits}",
        ]
        for barrier, count in self.barrier_detections.items():
            lines.append(f'haiox_smart_miner_barrier_detected_total{{type="{barrier}"}} {count}')
        return "\n".join(lines) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "blocked_requests": self.blocked_requests,
            "success_rate_pct": round(self.success_rate, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "static_fetches": self.static_fetches,
            "dynamic_fetches": self.dynamic_fetches,
            "dns_cache_hits": self.dns_cache_hits,
            "dns_cache_misses": self.dns_cache_misses,
            "total_bytes_fetched": self.total_bytes_fetched,
            "barrier_detections": self.barrier_detections,
        }


# Global singleton instance
GLOBAL_METRICS = MinerMetrics()
