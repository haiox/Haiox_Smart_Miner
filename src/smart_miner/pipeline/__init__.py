"""Local cleaning, AST noise reduction, and structured extraction."""

try:
    from .ast_cleaner import ASTCleaner, ASTCleanReport
    from .tables import TableNormalizer, TableData
    from .document import CleanDocument, DocumentCleaner
    from .extractor import StructuredExtractor
    from .orchestrator import CrawlOrchestrator
except (ImportError, ModuleNotFoundError):
    ASTCleaner = None  # type: ignore
    ASTCleanReport = None  # type: ignore
    TableNormalizer = None  # type: ignore
    TableData = None  # type: ignore
    CleanDocument = None  # type: ignore
    DocumentCleaner = None  # type: ignore
    StructuredExtractor = None  # type: ignore
    CrawlOrchestrator = None  # type: ignore

__all__ = [
    "ASTCleaner",
    "ASTCleanReport",
    "TableNormalizer",
    "TableData",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
]
