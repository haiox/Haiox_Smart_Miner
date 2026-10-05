"""Reusable local document; no credentials, response headers or raw HTML retained."""
import json
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify
from pydantic import BaseModel, Field


class CleanDocument(BaseModel):
    source_url: str
    title: str = ""
    markdown: str
    visible_text: str
    json_ld: list = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    input_character_count: int
    output_character_count: int

    def extraction_text(self):
        text = f"Source: {self.source_url}\n"
        if self.title:
            text += f"Title: {self.title}\n"
        text += f"\n{self.markdown}"
        if self.json_ld and "STRUCTURED_DATA_FALLBACK" not in self.warnings:
            text += "\n\nJSON-LD (source claims, not verified):\n" + json.dumps(self.json_ld, ensure_ascii=False)
        return text


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
    def __init__(self, *, prefer_main: bool = False):
        self.prefer_main = prefer_main

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
        base = soup.find("base", href=True)
        base_url = urljoin(page.source_url, base["href"]) if base else page.source_url
        # Malformed pages may place <title> outside <head>; it is metadata,
        # never visible article content.
        for node in soup(["script", "style", "noscript", "head", "title", "template"]):
            node.decompose()
        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()
        # Do not drop nav/footer wholesale: they may contain useful contacts or links.
        for node in soup.select('[hidden], [aria-hidden="true"]'):
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
        tables = []
        for table in soup.find_all("table"):
            if table.find_parent("table"):
                continue
            if table.select("[rowspan], [colspan], table") or "|" in str(table):
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
        document = CleanDocument(source_url=page.source_url, title=title,
                                 markdown=markdown, visible_text=visible, json_ld=json_ld,
                                 warnings=warnings, input_character_count=len(page.html),
                                 output_character_count=0)
        document.output_character_count = len(document.extraction_text())
        return document
