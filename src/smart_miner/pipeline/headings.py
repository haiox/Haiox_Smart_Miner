"""Heading Hierarchy & Document Outline Synthesizer.

Extracts, cleans, normalizes, and reconstructs the structural heading hierarchy
(H1 through H6) of documents. Fixes irregular hierarchy gaps, generates
collision-free URL-safe anchors/slugs, builds a hierarchical outline tree,
and renders clean GitHub Flavored Markdown (GFM) Tables of Contents (TOC).
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


def slugify(text: str) -> str:
    """Converts a heading string into a URL-friendly, deterministic anchor slug.
    
    Supports Latin, Persian, Arabic, and Unicode character sets.
    """
    cleaned = text.lower().strip()
    # Remove characters that are neither word characters, whitespace, nor hyphens
    cleaned = re.sub(r"[^\w\s-]", "", cleaned, flags=re.UNICODE)
    # Collapse consecutive whitespace or hyphens into a single hyphen
    cleaned = re.sub(r"[\s_-]+", "-", cleaned)
    slug = cleaned.strip("-")
    return slug if slug else "section"


def clean_heading_text(element: Tag) -> str:
    """Extracts text from a heading tag, removing hidden noise and collapsing whitespace."""
    # Remove hidden elements or tracking badges inside the heading
    for hidden in element.find_all(attrs={"aria-hidden": "true"}):
        hidden.decompose()
    for hidden in element.find_all(class_=re.compile(r"hidden|sr-only|invisible", re.I)):
        hidden.decompose()
        
    text = element.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


class HeadingItem(BaseModel):
    """Represents a single heading node in the document hierarchy."""
    level: int  # Original HTML level (1 to 6)
    normalized_level: int  # Level adjusted to repair hierarchy skips (e.g. H1 -> H3 becomes H1 -> H2)
    text: str
    slug: str
    anchor: str = ""
    children: List[HeadingItem] = Field(default_factory=list)

    def to_toc_line(self, base_level: int = 1, indent_spaces: int = 2) -> str:
        """Formats this heading into a Markdown Table of Contents bullet line."""
        indent = " " * (max(0, self.normalized_level - base_level) * indent_spaces)
        target = self.anchor or self.slug
        return f"{indent}- [{self.text}](#{target})"

    def to_dict_tree(self) -> Dict[str, Any]:
        """Serializes the heading node and its sub-tree to a dictionary."""
        return {
            "level": self.level,
            "normalized_level": self.normalized_level,
            "text": self.text,
            "slug": self.slug,
            "anchor": self.anchor,
            "children": [child.to_dict_tree() for child in self.children],
        }


class DocumentOutline(BaseModel):
    """Complete document outline containing hierarchical and flattened headings."""
    title: str = ""
    headings: List[HeadingItem] = Field(default_factory=list)
    flat_headings: List[HeadingItem] = Field(default_factory=list)
    max_depth: int = 0
    total_count: int = 0
    has_gaps: bool = False

    def to_markdown_toc(self, max_depth: int = 6, indent_spaces: int = 2) -> str:
        """Renders the document outline as a GitHub Flavored Markdown (GFM) TOC."""
        if not self.flat_headings:
            return ""

        # Determine the minimum normalized level to use as base indent
        min_level = min(h.normalized_level for h in self.flat_headings)
        lines: List[str] = []

        for item in self.flat_headings:
            if item.normalized_level <= max_depth:
                lines.append(item.to_toc_line(base_level=min_level, indent_spaces=indent_spaces))

        return "\n".join(lines)

    def find_by_slug(self, slug: str) -> Optional[HeadingItem]:
        """Finds a heading item by its slug."""
        for item in self.flat_headings:
            if item.slug == slug:
                return item
        return None

    def get_section_path(self, target_slug: str) -> List[str]:
        """Returns the breadcrumb path of heading texts leading to the target slug."""
        def _search(nodes: List[HeadingItem], path: List[str]) -> Optional[List[str]]:
            for node in nodes:
                current_path = path + [node.text]
                if node.slug == target_slug:
                    return current_path
                res = _search(node.children, current_path)
                if res:
                    return res
            return None

        result = _search(self.headings, [])
        return result or []


class HeadingHierarchyExtractor:
    """Extracts, normalizes, and constructs hierarchical outlines from HTML or Markdown."""

    def __init__(
        self,
        *,
        min_heading_length: int = 1,
        max_heading_length: int = 300,
        repair_gaps: bool = True,
    ):
        self.min_heading_length = min_heading_length
        self.max_heading_length = max_heading_length
        self.repair_gaps = repair_gaps

    def extract_from_soup(self, soup: BeautifulSoup, page_title: str = "") -> DocumentOutline:
        """Extracts headings from a BeautifulSoup DOM tree and builds an outline."""
        heading_tags = soup.find_all(re.compile(r"^h[1-6]$", re.IGNORECASE))
        seen_slugs: Dict[str, int] = {}
        raw_items: List[HeadingItem] = []

        for tag in heading_tags:
            try:
                level = int(tag.name[1])
            except (ValueError, IndexError):
                continue

            text = clean_heading_text(tag)
            if not text or len(text) < self.min_heading_length or len(text) > self.max_heading_length:
                continue

            # Anchor preference: tag id > tag name > slug
            explicit_anchor = tag.get("id") or tag.get("name") or ""
            base_slug = slugify(explicit_anchor) if explicit_anchor else slugify(text)

            # Deduplicate slug
            if base_slug in seen_slugs:
                seen_slugs[base_slug] += 1
                unique_slug = f"{base_slug}-{seen_slugs[base_slug]}"
            else:
                seen_slugs[base_slug] = 0
                unique_slug = base_slug

            raw_items.append(
                HeadingItem(
                    level=level,
                    normalized_level=level,
                    text=text,
                    slug=unique_slug,
                    anchor=explicit_anchor or unique_slug,
                )
            )

        return self._build_outline(raw_items, page_title)

    def extract_from_markdown(self, markdown_text: str, page_title: str = "") -> DocumentOutline:
        """Extracts headings from ATX-style Markdown text (# Heading) and builds an outline."""
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$", re.MULTILINE)
        seen_slugs: Dict[str, int] = {}
        raw_items: List[HeadingItem] = []

        for match in heading_pattern.finditer(markdown_text):
            level = len(match.group(1))
            text = match.group(2).strip()
            # Strip inline markdown symbols from heading text: **bold**, `code`, etc.
            text = re.sub(r"[*_`~]", "", text)
            # Strip markdown links [text](url) -> text
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
            text = re.sub(r"\s+", " ", text).strip()

            if not text or len(text) < self.min_heading_length or len(text) > self.max_heading_length:
                continue

            base_slug = slugify(text)
            if base_slug in seen_slugs:
                seen_slugs[base_slug] += 1
                unique_slug = f"{base_slug}-{seen_slugs[base_slug]}"
            else:
                seen_slugs[base_slug] = 0
                unique_slug = base_slug

            raw_items.append(
                HeadingItem(
                    level=level,
                    normalized_level=level,
                    text=text,
                    slug=unique_slug,
                    anchor=unique_slug,
                )
            )

        return self._build_outline(raw_items, page_title)

    def _build_outline(self, raw_items: List[HeadingItem], title: str) -> DocumentOutline:
        """Normalizes levels to repair hierarchy gaps and constructs the tree hierarchy."""
        if not raw_items:
            return DocumentOutline(title=title)

        has_gaps = False
        normalized_items: List[HeadingItem] = []

        # Step 1: Detect gaps and normalize levels if repair_gaps is True
        if self.repair_gaps:
            # Maintain a level mapping stack
            # Example: [H1, H4, H6] -> [H1, H2, H3]
            # When dropping back down (e.g. H2 after H4), map appropriately
            prev_level = 0
            prev_norm = 0
            level_map: Dict[int, int] = {}

            for item in raw_items:
                orig = item.level
                if orig > prev_level:
                    # Going deeper
                    if prev_level > 0 and orig > prev_level + 1:
                        has_gaps = True
                    norm = prev_norm + 1 if prev_norm > 0 else 1
                    level_map[orig] = norm
                    prev_norm = norm
                elif orig == prev_level:
                    norm = prev_norm
                else:
                    # Going up
                    # Look up in map or find highest mapped level <= orig
                    candidates = [lvl for lvl in level_map if lvl <= orig]
                    if candidates:
                        best = max(candidates)
                        norm = level_map[best]
                    else:
                        norm = 1
                    # Invalidate deeper mappings
                    level_map = {lvl: lnorm for lvl, lnorm in level_map.items() if lvl <= orig}
                    level_map[orig] = norm
                    prev_norm = norm

                prev_level = orig
                item.normalized_level = norm
                normalized_items.append(item)
        else:
            normalized_items = raw_items

        # Step 2: Build tree structure using a stack
        # Root dummy item with normalized_level = 0
        root = HeadingItem(level=0, normalized_level=0, text="ROOT", slug="root")
        stack: List[HeadingItem] = [root]

        for item in normalized_items:
            # Pop stack until we find a parent whose level is strictly lower
            target_level = item.normalized_level if self.repair_gaps else item.level
            while len(stack) > 1:
                top_level = stack[-1].normalized_level if self.repair_gaps else stack[-1].level
                if top_level >= target_level:
                    stack.pop()
                else:
                    break
            stack[-1].children.append(item)
            stack.append(item)

        max_depth = max(h.normalized_level for h in normalized_items) if normalized_items else 0

        return DocumentOutline(
            title=title,
            headings=root.children,
            flat_headings=normalized_items,
            max_depth=max_depth,
            total_count=len(normalized_items),
            has_gaps=has_gaps,
        )
