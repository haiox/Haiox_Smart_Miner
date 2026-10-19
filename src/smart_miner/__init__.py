"""Haiox Smart Miner: reusable single-page extraction core."""

from .crawler.router import route

try:
    from .pipeline.document import CleanDocument, DocumentCleaner
    from .pipeline.extractor import StructuredExtractor
    from .pipeline.orchestrator import CrawlOrchestrator
except ModuleNotFoundError:
    CleanDocument = None
    DocumentCleaner = None
    StructuredExtractor = None
    CrawlOrchestrator = None

__all__ = [
    "route", "CleanDocument", "DocumentCleaner", "StructuredExtractor",
    "CrawlOrchestrator",
]
