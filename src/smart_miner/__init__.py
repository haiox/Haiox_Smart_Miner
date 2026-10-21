"""Haiox Smart Miner: reusable single-page extraction core."""

__version__ = "2.0.0"

from .crawler.router import route

try:
    from .pipeline.ast_cleaner import ASTCleaner, ASTCleanReport
    from .pipeline.tables import TableNormalizer, TableData
    from .pipeline.headings import HeadingItem, DocumentOutline, HeadingHierarchyExtractor, slugify
    from .pipeline.density import SemanticDensityScorer, SemanticDensityReport
    from .pipeline.metadata import MetadataHarvester, MetadataHarvest
    from .pipeline.jsonld import JSONLDResolver, ResolvedEntityGraph, ArticleEntity, ProductEntity, FAQItem
    from .pipeline.evidence import EvidenceArtifact, EvidenceChunk, EvidenceProvenance, EvidenceBuilder
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
    SemanticDensityScorer = None
    SemanticDensityReport = None
    MetadataHarvester = None
    MetadataHarvest = None
    JSONLDResolver = None
    ResolvedEntityGraph = None
    ArticleEntity = None
    ProductEntity = None
    FAQItem = None
    EvidenceArtifact = None
    EvidenceChunk = None
    EvidenceProvenance = None
    EvidenceBuilder = None
    CleanDocument = None
    DocumentCleaner = None
    StructuredExtractor = None
    CrawlOrchestrator = None

try:
    from .telemetry.metrics import MinerMetrics, GLOBAL_METRICS
    from .batch.queue import BatchJob, JobStatus, DomainRateLimiter, BatchCrawlManager
except ModuleNotFoundError:
    MinerMetrics = None
    GLOBAL_METRICS = None
    BatchJob = None
    JobStatus = None
    DomainRateLimiter = None
    BatchCrawlManager = None

__all__ = [
    "__version__",
    "route",
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
    "MetadataHarvester",
    "MetadataHarvest",
    "JSONLDResolver",
    "ResolvedEntityGraph",
    "ArticleEntity",
    "ProductEntity",
    "FAQItem",
    "EvidenceArtifact",
    "EvidenceChunk",
    "EvidenceProvenance",
    "EvidenceBuilder",
    "CleanDocument",
    "DocumentCleaner",
    "StructuredExtractor",
    "CrawlOrchestrator",
    "MinerMetrics",
    "GLOBAL_METRICS",
    "BatchJob",
    "JobStatus",
    "DomainRateLimiter",
    "BatchCrawlManager",
]
