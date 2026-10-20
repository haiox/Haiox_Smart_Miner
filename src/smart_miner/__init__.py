"""Haiox Smart Miner: reusable single-page extraction core."""

from .crawler.router import route

try:
    from .pipeline.ast_cleaner import ASTCleaner, ASTCleanReport
    from .pipeline.tables import TableNormalizer, TableData
    from .pipeline.document import CleanDocument, DocumentCleaner
    from .pipeline.extractor import StructuredExtractor
    from .pipeline.orchestrator import CrawlOrchestrator
except ModuleNotFoundError:
    ASTCleaner = None
    ASTCleanReport = None
    TableNormalizer = None
    TableData = None
    CleanDocument = None
    DocumentCleaner = None
    StructuredExtractor = None
    CrawlOrchestrator = None

__all__ = [
    "route",
    "ASTCleaner",
    "ASTCleanReport",
    "TableNormalizer",
    "TableData",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
]
