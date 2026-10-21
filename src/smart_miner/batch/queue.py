"""
Haiox Smart Miner - Subsystem 27: Domain Rate-Limiting & Batch Queue Engine
Coordinates high-throughput multi-URL ingestion while preventing IP bans and DoS triggering.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Coroutine
from urllib.parse import urlparse


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class BatchJob:
    job_id: str
    urls: List[str]
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    total_urls: int = 0
    completed_urls: int = 0

    def __post_init__(self):
        self.total_urls = len(self.urls)


class DomainRateLimiter:
    """Enforces minimum time intervals and concurrency limits per domain."""

    def __init__(self, min_interval_seconds: float = 0.5, max_domain_concurrency: int = 2):
        self.min_interval = min_interval_seconds
        self.max_domain_concurrency = max_domain_concurrency
        self._last_access: Dict[str, float] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    def _get_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return (parsed.netloc or "unknown").lower()
        except Exception:
            return "unknown"

    async def acquire(self, url: str) -> str:
        domain = self._get_domain(url)
        async with self._lock:
            if domain not in self._semaphores:
                self._semaphores[domain] = asyncio.Semaphore(self.max_domain_concurrency)
            sem = self._semaphores[domain]

        await sem.acquire()

        # Enforce rate limit interval
        now = time.monotonic()
        last = self._last_access.get(domain, 0.0)
        elapsed = now - last
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)

        self._last_access[domain] = time.monotonic()
        return domain

    def release(self, domain: str) -> None:
        if domain in self._semaphores:
            self._semaphores[domain].release()


class BatchCrawlManager:
    """In-memory async batch crawl manager with concurrency control."""

    def __init__(
        self,
        worker_concurrency: int = 4,
        rate_limiter: Optional[DomainRateLimiter] = None,
    ):
        self.worker_concurrency = worker_concurrency
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.jobs: Dict[str, BatchJob] = {}
        self._semaphore = asyncio.Semaphore(worker_concurrency)

    def create_job(self, urls: List[str]) -> BatchJob:
        job_id = str(uuid.uuid4())
        job = BatchJob(job_id=job_id, urls=urls)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        return self.jobs.get(job_id)

    async def execute_job(
        self,
        job_id: str,
        crawl_fn: Callable[[str], Coroutine[Any, Any, Dict[str, Any]]],
    ) -> BatchJob:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")

        job.status = JobStatus.PROCESSING

        async def _crawl_single(target_url: str):
            domain = await self.rate_limiter.acquire(target_url)
            try:
                async with self._semaphore:
                    res = await crawl_fn(target_url)
                    job.results.append(res)
            except Exception as exc:
                job.errors.append({"url": target_url, "error": str(exc)})
            finally:
                self.rate_limiter.release(domain)
                job.completed_urls += 1

        tasks = [_crawl_single(u) for u in job.urls]
        await asyncio.gather(*tasks, return_exceptions=True)

        job.status = JobStatus.COMPLETED if not job.errors or job.results else JobStatus.FAILED
        job.completed_at = time.time()
        return job
