"""Haiox Smart Miner: reusable single-page extraction core."""

from .crawler.router import route

try:
    from .pipeline.ast_cleaner import ASTCleaner, ASTCleanReport
    from .pipeline.document import CleanDocument, DocumentCleaner
    from .pipeline.extractor import StructuredExtractor
    from .pipeline.orchestrator import CrawlOrchestrator
except ModuleNotFoundError:
    ASTCleaner = None
    ASTCleanReport = None
    CleanDocument = None
    DocumentCleaner = None
    StructuredExtractor = None
    CrawlOrchestrator = None

__all__ = [
    "route",
    "ASTCleaner",
    "ASTCleanReport",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
]
