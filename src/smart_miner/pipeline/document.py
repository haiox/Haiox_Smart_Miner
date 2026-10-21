"""Reusable local document; no credentials, response headers or raw HTML retained."""
import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify
from pydantic import BaseModel, Field

try:
    from .ast_cleaner import ASTCleaner, ASTCleanReport
    from .tables import TableNormalizer, TableData
    from .headings import HeadingHierarchyExtractor, DocumentOutline
    from .density import SemanticDensityScorer, SemanticDensityReport
    from .metadata import MetadataHarvester, MetadataHarvest
    from .jsonld import JSONLDResolver, ResolvedEntityGraph
    from .evidence import EvidenceArtifact, EvidenceBuilder
except ImportError:
    from ast_cleaner import ASTCleaner, ASTCleanReport
    from tables import TableNormalizer, TableData
    from headings import HeadingHierarchyExtractor, DocumentOutline
    from density import SemanticDensityScorer, SemanticDensityReport
    from metadata import MetadataHarvester, MetadataHarvest
    from jsonld import JSONLDResolver, ResolvedEntityGraph
    from evidence import EvidenceArtifact, EvidenceBuilder


class CleanDocument(BaseModel):
    source_url: str
    title: str = ""
    markdown: str
    visible_text: str
    json_ld: list = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    input_character_count: int
    output_character_count: int
    noise_reduction_percentage: float = 0.0
    tables: list[TableData] = Field(default_factory=list)
    outline: DocumentOutline = Field(default_factory=DocumentOutline)
    density: SemanticDensityReport = Field(default_factory=SemanticDensityReport)
    metadata: MetadataHarvest = Field(default_factory=MetadataHarvest)
    json_ld_graph: ResolvedEntityGraph = Field(default_factory=ResolvedEntityGraph)

    def extraction_text(self):
        text = f"Source: {self.source_url}\n"
        if self.title:
            text += f"Title: {self.title}\n"
        text += f"\n{self.markdown}"
        if self.json_ld and "STRUCTURED_DATA_FALLBACK" not in self.warnings:
            text += "\n\nJSON-LD (source claims, not verified):\n" + json.dumps(self.json_ld, ensure_ascii=False)
        return text

    def to_evidence_artifact(
        self,
        strategy: str = "static",
        status_code: int = 200,
        timing_ms: dict | None = None,
        security_verified: bool = True,
        bounded_stream_verified: bool = True,
        fingerprint_mode: str = "balanced",
        chunk_token_limit: int | None = None,
    ) -> EvidenceArtifact:
        """Produce a standardized, cryptographically verifiable EvidenceArtifact for Haiox Trilogy."""
        builder = EvidenceBuilder()
        return builder.build_artifact(
            document=self,
            strategy=strategy,
            status_code=status_code,
            timing_ms=timing_ms,
            security_verified=security_verified,
            bounded_stream_verified=bounded_stream_verified,
            fingerprint_mode=fingerprint_mode,
            chunk_token_limit=chunk_token_limit,
        )


def structured_data_markdown(items):
    """Recover source-supplied descriptions/FAQs when a JS page has no body."""
    nodes = []
    for item in items:
        if isinstance(item, dict):
            graph = item.get("@graph")
            nodes.extend(graph if isinstance(graph, list) else [item])
    lines = ["# Structured data supplied by the website", "",
             "The visible page body was unavailable; these are the site's own metadata claims."]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = node.get("@type", "")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(value in kinds for value in ("WebPage", "Article", "NewsArticle")):
            description = node.get("description")
            if isinstance(description, str) and description.strip():
                lines.extend(["", description.strip()])
        if "FAQPage" in kinds:
            questions = node.get("mainEntity", [])
            if isinstance(questions, dict):
                questions = [questions]
            for question in questions if isinstance(questions, list) else []:
                if not isinstance(question, dict):
                    continue
                answer = question.get("acceptedAnswer", {})
                name = question.get("name")
                response = answer.get("text") if isinstance(answer, dict) else None
                if isinstance(name, str) and isinstance(response, str):
                    lines.extend(["", f"## {name.strip()}", "", response.strip()])
    return "\n".join(lines).strip() if len(lines) > 3 else ""


class DocumentCleaner:
    def __init__(
        self,
        *,
        prefer_main: bool = False,
        ast_cleaner: ASTCleaner | None = None,
        table_normalizer: TableNormalizer | None = None,
        heading_extractor: HeadingHierarchyExtractor | None = None,
        density_scorer: SemanticDensityScorer | None = None,
        metadata_harvester: MetadataHarvester | None = None,
        jsonld_resolver: JSONLDResolver | None = None,
        normalize_tables: bool = False,
        filter_boilerplate: bool = False,
    ):
        self.prefer_main = prefer_main
        self.ast_cleaner = ast_cleaner or ASTCleaner()
        self.table_normalizer = table_normalizer or TableNormalizer()
        self.heading_extractor = heading_extractor or HeadingHierarchyExtractor()
        self.density_scorer = density_scorer or SemanticDensityScorer()
        self.metadata_harvester = metadata_harvester or MetadataHarvester()
        self.jsonld_resolver = jsonld_resolver or JSONLDResolver()
        self.normalize_tables = normalize_tables
        self.filter_boilerplate = filter_boilerplate

    def clean(self, page, *, structured_fallback=True):
        if __package__ == "pipeline":
            from crawler.barriers import barrier_reason
        else:
            from ..crawler.barriers import barrier_reason
        if barrier_reason(page):
            raise ValueError("Blocked pages cannot become CleanDocument")
        soup = BeautifulSoup(page.html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        json_ld, warnings = [], []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                value = json.loads(script.string or script.get_text())
                if value not in json_ld:
                    json_ld.append(value)
            except (ValueError, TypeError):
                warnings.append("INVALID_JSON_LD")
        resolved_graph = self.jsonld_resolver.resolve(json_ld)
        base = soup.find("base", href=True)
        base_url = urljoin(page.source_url, base["href"]) if base else page.source_url
        metadata_harvest = self.metadata_harvester.harvest(soup, base_url)
        if metadata_harvest.title and not title:
            title = metadata_harvest.title
        # Malformed pages may place <title> outside <head>; it is metadata,
        # never visible article content.
        for node in soup(["head", "title"]):
            node.decompose()
        clean_report = self.ast_cleaner.clean_soup(soup)
        density_report = self.density_scorer.clean_boilerplate(soup, prune=self.filter_boilerplate)

        if False:  # comments already extracted in ast_cleaner
            comment.extract()
        # Do not drop nav/footer wholesale: they may contain useful contacts or links.
        if False:  # hidden nodes already decomposed in ast_cleaner
            node.decompose()
        # Choose the content region only after removing scripts and hidden
        # nodes. Otherwise a JS shell can look substantial and then clean to
        # an empty document (the Grass homepage is one example).
        if self.prefer_main:
            articles = [node for node in soup.find_all("article")
                        if len(node.get_text(" ", strip=True)) >= 300]
            if len(articles) == 1:
                soup = BeautifulSoup(str(articles[0]), "html.parser")
            else:
                main = soup.select_one("main, [role='main']")
                if main and len(main.get_text(" ", strip=True)) >= 300:
                    soup = BeautifulSoup(str(main), "html.parser")
        for node in soup.find_all(["a", "img"]):
            attr = "href" if node.name == "a" else "src"
            if node.get(attr):
                resolved = urljoin(base_url, node[attr])
                if urlsplit(resolved).scheme in {"http", "https", "mailto", "tel"}:
                    node[attr] = resolved
                else:
                    del node[attr]
        # Only deduplicate identical navigation blocks, never repeated data rows.
        seen = set()
        for node in soup.find_all("nav"):
            signature = str(node)
            if signature in seen:
                node.decompose()
            seen.add(signature)
        visible = soup.get_text(" ", strip=True)
        outline = self.heading_extractor.extract_from_soup(soup, page_title=title)
        structured_tables = self.table_normalizer.extract_all_tables(soup)
        tables = []
        for table in soup.find_all("table"):
            if table.find_parent("table"):
                continue
            if self.normalize_tables:
                parsed_table = self.table_normalizer.parse_table(table)
                marker = f"SMARTMINERTABLE{len(tables)}PLACEHOLDER"
                tables.append((marker, parsed_table.markdown))
                table.replace_with(marker)
            elif table.select("[rowspan], [colspan], table") or "|" in str(table):
                # Markdown pipe tables cannot represent merged/nested cells.
                for node in [table, *table.find_all(True)]:
                    node.attrs = {k: v for k, v in node.attrs.items()
                                  if k in {"rowspan", "colspan", "href", "src", "alt"}}
                marker = f"SMARTMINERTABLE{len(tables)}PLACEHOLDER"
                tables.append((marker, str(table)))
                table.replace_with(marker)
        markdown = markdownify(str(soup), heading_style="ATX").strip()
        for marker, table in tables:
            markdown = markdown.replace(marker, table)
        lower_visible = visible.casefold()
        cookie_notice_only = (len(visible) < 1000 and "cookie" in lower_visible
                              and ("accept all" in lower_visible or
                                   "cookie settings" in lower_visible))
        if (self.prefer_main and structured_fallback and
                (len(visible) < 300 or cookie_notice_only)):
            metadata_markdown = structured_data_markdown(json_ld)
            if len(metadata_markdown) >= 300:
                markdown = metadata_markdown
                visible = metadata_markdown
                warnings.append("STRUCTURED_DATA_FALLBACK")
                outline = self.heading_extractor.extract_from_markdown(markdown, page_title=title)
        elif not outline.flat_headings and markdown:
            outline = self.heading_extractor.extract_from_markdown(markdown, page_title=title)
        if visible and not metadata_harvest.reading_time_minutes:
            words = len(re.findall(r"\w+", visible))
            metadata_harvest.reading_time_minutes = max(1, round(words / self.metadata_harvester.words_per_minute))
        document = CleanDocument(source_url=page.source_url, title=title,
                                 markdown=markdown, visible_text=visible, json_ld=json_ld,
                                 warnings=warnings, input_character_count=len(page.html),
                                 output_character_count=0,
                                 noise_reduction_percentage=clean_report.noise_reduction_percentage,
                                 tables=structured_tables,
                                 outline=outline,
                                 density=density_report,
                                 metadata=metadata_harvest,
                                 json_ld_graph=resolved_graph)
        document.output_character_count = len(document.extraction_text())
        return document
