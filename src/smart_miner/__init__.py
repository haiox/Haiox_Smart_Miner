"""Haiox Smart Miner: reusable single-page extraction core."""

from .crawler.router import route
from .pipeline.document import CleanDocument, DocumentCleaner
from .pipeline.extractor import StructuredExtractor
from .pipeline.orchestrator import CrawlOrchestrator

__all__ = [
    "route", "CleanDocument", "DocumentCleaner", "StructuredExtractor",
    "CrawlOrchestrator",
]
