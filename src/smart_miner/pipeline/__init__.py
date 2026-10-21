"""Local cleaning, AST noise reduction, and structured extraction."""

try:
    from .ast_cleaner import ASTCleaner, ASTCleanReport
    from .tables import TableNormalizer, TableData
    from .headings import HeadingItem, DocumentOutline, HeadingHierarchyExtractor, slugify
    from .density import SemanticDensityScorer, SemanticDensityReport
    from .document import CleanDocument, DocumentCleaner
    from .extractor import StructuredExtractor
    from .orchestrator import CrawlOrchestrator
except (ImportError, ModuleNotFoundError):
    ASTCleaner = None  # type: ignore
    ASTCleanReport = None  # type: ignore
    TableNormalizer = None  # type: ignore
    TableData = None  # type: ignore
    HeadingItem = None  # type: ignore
    DocumentOutline = None  # type: ignore
    HeadingHierarchyExtractor = None  # type: ignore
    slugify = None  # type: ignore
    SemanticDensityScorer = None  # type: ignore
    SemanticDensityReport = None  # type: ignore
    CleanDocument = None  # type: ignore
    DocumentCleaner = None  # type: ignore
    StructuredExtractor = None  # type: ignore
    CrawlOrchestrator = None  # type: ignore

__all__ = [
    "ASTCleaner",
    "ASTCleanReport",
    "TableNormalizer",
    "TableData",
    "HeadingItem",
    "DocumentOutline",
    "HeadingHierarchyExtractor",
    "slugify",
    "SemanticDensityScorer",
    "SemanticDensityReport",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
]
