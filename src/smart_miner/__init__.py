"""Haiox Smart Miner: reusable single-page extraction core."""

from .crawler.router import route

try:
    from .pipeline.ast_cleaner import ASTCleaner, ASTCleanReport
    from .pipeline.tables import TableNormalizer, TableData
    from .pipeline.headings import HeadingItem, DocumentOutline, HeadingHierarchyExtractor, slugify
    from .pipeline.document import CleanDocument, DocumentCleaner
    from .pipeline.extractor import StructuredExtractor
    from .pipeline.orchestrator import CrawlOrchestrator
except ModuleNotFoundError:
    ASTCleaner = None
    ASTCleanReport = None
    TableNormalizer = None
    TableData = None
    HeadingItem = None
    DocumentOutline = None
    HeadingHierarchyExtractor = None
    slugify = None
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
    "HeadingItem",
    "DocumentOutline",
    "HeadingHierarchyExtractor",
    "slugify",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
]
