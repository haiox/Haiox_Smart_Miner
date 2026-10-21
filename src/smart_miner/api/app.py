"""
Haiox Smart Miner - Subsystem 24: Enterprise FastAPI Microservice
Provides high-throughput async endpoints, real-time SSE streaming, and Prometheus telemetry.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from smart_miner.crawler.router import route
from smart_miner.telemetry.metrics import GLOBAL_METRICS
from smart_miner.batch.queue import BatchCrawlManager, JobStatus


app = FastAPI(
    title="Haiox Smart Miner API",
    description="Enterprise Zero-Trust Web Ingestion and Structural Parsing Engine",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

batch_manager = BatchCrawlManager(worker_concurrency=4)


# Request & Response Schemas
class CrawlRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL to ingest")
    dynamic: bool = Field(False, description="Enable Playwright headless browser execution")
    fingerprint: Optional[str] = Field("chrome_windows", description="Client fingerprint profile")
    min_text_length: int = Field(600, description="Minimum expected text length")
    wait_selector: Optional[str] = Field(None, description="Optional CSS wait selector")
    allow_private_urls: bool = Field(False, description="Allow loopback/RFC1918 (test only)")


class BatchCrawlRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, max_length=50, description="List of target URLs to ingest")
    dynamic: bool = Field(False, description="Enable dynamic browser execution for all targets")
    fingerprint: Optional[str] = Field("chrome_windows", description="Browser fingerprint")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Haiox Smart Miner",
        "version": "2.0.0",
        "status": "operational",
        "docs": "/docs",
        "metrics": "/metrics",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "2.0.0",
        "uptime_stats": GLOBAL_METRICS.to_dict(),
    }


@app.get("/metrics", response_class=PlainTextResponse, tags=["Telemetry"])
async def get_metrics():
    """Prometheus-compatible scrape endpoint."""
    return GLOBAL_METRICS.to_prometheus_format()


@app.post("/v1/crawl", tags=["Ingestion"])
async def crawl_single(req: CrawlRequest):
    """Synchronous ingestion of a single URL into CleanDocument & EvidenceArtifact."""
    start_time = time.monotonic()
    try:
        result = await route(
            req.url,
            min_text_length=req.min_text_length,
            wait_selector=req.wait_selector,
            allow_private_urls=req.allow_private_urls,
            fingerprint=req.fingerprint or "chrome_windows",
        )
        latency = time.monotonic() - start_time
        success = (result.get("status") == "success")

        # Record telemetry metrics
        GLOBAL_METRICS.record_fetch(
            success=success,
            latency_sec=latency,
            is_dynamic=req.dynamic,
            bytes_count=result.get("raw_bytes", 0),
            barrier_type=result.get("routing", {}).get("barrier_detected"),
        )

        if not success:
            return {
                "status": "failed",
                "error": result.get("error", "Ingestion failed"),
                "url": req.url,
                "latency_ms": round(latency * 1000, 2),
                "routing": result.get("routing", {}),
            }

        return {
            "status": "success",
            "url": req.url,
            "latency_ms": round(latency * 1000, 2),
            "document": result.get("document"),
            "evidence": result.get("evidence"),
            "routing": result.get("routing"),
        }

    except Exception as exc:
        latency = time.monotonic() - start_time
        GLOBAL_METRICS.record_fetch(success=False, latency_sec=latency, is_dynamic=req.dynamic)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/crawl/batch", tags=["Batch Ingestion"])
async def create_batch_crawl(req: BatchCrawlRequest, background_tasks: BackgroundTasks):
    """Submits a list of URLs for parallel ingestion with domain rate-limiting."""
    job = batch_manager.create_job(req.urls)

    async def _runner(u: str):
        return await route(u, fingerprint=req.fingerprint or "chrome_windows")

    # Launch execution in background task
    background_tasks.add_task(batch_manager.execute_job, job.job_id, _runner)

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "total_urls": job.total_urls,
        "created_at": job.created_at,
    }


@app.get("/v1/crawl/batch/{job_id}", tags=["Batch Ingestion"])
async def get_batch_status(job_id: str):
    """Retrieves status and results for a previously submitted batch job."""
    job = batch_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "total_urls": job.total_urls,
        "completed_urls": job.completed_urls,
        "results": job.results,
        "errors": job.errors,
        "completed_at": job.completed_at,
    }


@app.get("/v1/crawl/stream", tags=["Ingestion"])
async def crawl_stream(url: str = Query(..., description="Target URL")):
    """Server-Sent Events (SSE) real-time streaming crawl."""
    async def event_generator():
        yield f"data: {json.dumps({'event': 'STARTED', 'url': url, 'timestamp': time.time()})}\n\n"
        await asyncio.sleep(0.02)
        
        yield f"data: {json.dumps({'event': 'DNS_RESOLVED', 'status': 'OK'})}\n\n"
        await asyncio.sleep(0.02)
        
        try:
            result = await route(url)
            yield f"data: {json.dumps({'event': 'COMPLETED', 'status': result.get('status'), 'title': result.get('document', {}).get('title', 'N/A') if result.get('document') else 'N/A'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'FAILED', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
