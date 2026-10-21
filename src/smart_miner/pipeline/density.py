"""Semantic Density & Boilerplate Scorer.

Computes text-to-tag ratios, link density, and structural semantic weight
across DOM containers. Identifies and prunes boilerplate clusters (sidebars,
footer links, related article teasers, social widgets) while isolating the
dominant content region—without reliance on external LLM calls.
"""

from __future__ import annotations

import re
import math
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


POSITIVE_HINTS = re.compile(
    r"(article|content|entry|post|main|body|story|text|prose|document|chapter|section)",
    re.IGNORECASE,
)

NEGATIVE_HINTS = re.compile(
    r"(sidebar|comment|footer|foot|nav|menu|share|social|related|promo|widget|"
    r"banner|ad-|ads|recommend|author-bio|newsletter|popup|modal|signup|trending|"
    r"tags|meta-bar|follow|disclaimer|copyright|breadcrumbs)",
    re.IGNORECASE,
)

CONTAINER_TAGS = {"div", "section", "article", "aside", "nav", "ul", "ol", "footer", "main"}


class SemanticDensityReport(BaseModel):
    """Telemetry report describing the semantic density and boilerplate reduction."""
    overall_text_density: float = 0.0
    overall_link_density: float = 0.0
    semantic_density_score: float = 0.0
    nodes_evaluated: int = 0
    boilerplate_candidates_count: int = 0
    boilerplate_nodes_removed: int = 0
    dominant_container_tag: str = ""


class SemanticDensityScorer:
    """Evaluates text density and link density to isolate core content and prune boilerplate."""

    def __init__(
        self,
        *,
        link_density_threshold: float = 0.45,
        min_text_length: int = 25,
        min_density_score: float = 2.0,
    ):
        self.link_density_threshold = link_density_threshold
        self.min_text_length = min_text_length
        self.min_density_score = min_density_score

    def calculate_link_density(self, element: Tag) -> float:
        """Calculates the ratio of hyperlink text characters to total text characters."""
        total_text = element.get_text(" ", strip=True)
        total_chars = len(re.sub(r"\s+", "", total_text))
        if total_chars == 0:
            return 1.0

        link_chars = sum(len(re.sub(r"\s+", "", a.get_text())) for a in element.find_all("a"))
        return min(1.0, link_chars / total_chars)

    def calculate_text_density(self, element: Tag) -> float:
        """Calculates text characters per child HTML tag."""
        text_len = len(element.get_text(" ", strip=True))
        tag_count = len(element.find_all(True)) + 1
        return text_len / tag_count

    def calculate_punctuation_weight(self, text: str) -> float:
        """Measures punctuation density indicative of narrative sentence structure.
        
        Articles and technical prose contain commas, periods, colons, and question marks;
        navigation lists and link menus contain almost none.
        """
        if not text:
            return 0.1
        punct_count = len(re.findall(r"[,.:;?!،؛؟]", text))
        ratio = punct_count / max(1, len(text))
        # Punctuation ratio typically ranges from 0.01 to 0.05 in natural text
        return min(2.0, max(0.2, ratio * 40.0 + 0.5))

    def score_element(self, element: Tag) -> float:
        """Computes a composite semantic density score for a DOM container."""
        text = element.get_text(" ", strip=True)
        text_len = len(text)
        if text_len < self.min_text_length:
            return 0.0

        link_density = self.calculate_link_density(element)
        text_density = self.calculate_text_density(element)
        punct_weight = self.calculate_punctuation_weight(text)

        # Attribute heuristics
        class_id_str = " ".join([
            " ".join(element.get("class", [])) if isinstance(element.get("class"), list) else str(element.get("class", "")),
            str(element.get("id", "")),
            str(element.get("role", "")),
        ])

        weight = 1.0
        if POSITIVE_HINTS.search(class_id_str):
            weight *= 1.6
        if NEGATIVE_HINTS.search(class_id_str):
            weight *= 0.35

        # Semantic tag weight
        if element.name in {"article", "main"}:
            weight *= 1.5
        elif element.name in {"aside", "nav", "footer"}:
            weight *= 0.25

        # High link density sharply penalizes score
        content_factor = max(0.01, 1.0 - math.pow(link_density, 1.3))
        
        score = text_density * content_factor * punct_weight * weight
        return max(0.0, score)

    def clean_boilerplate(self, soup: BeautifulSoup, *, prune: bool = True) -> SemanticDensityReport:
        """Identifies and optionally decomposes boilerplate containers, returning a detailed report."""
        nodes_evaluated = 0

        # Evaluate candidate containers
        candidates: List[Tuple[Tag, float]] = []
        to_remove: List[Tag] = []

        # Find all structural containers
        for tag in soup.find_all(list(CONTAINER_TAGS)):
            # Skip tags that have already been decomposed or are document roots
            if not tag.parent or tag.name in {"body", "html"}:
                continue

            nodes_evaluated += 1
            text = tag.get_text(" ", strip=True)
            text_len = len(text)
            
            if text_len == 0:
                continue

            link_density = self.calculate_link_density(tag)
            class_id_str = " ".join([
                " ".join(tag.get("class", [])) if isinstance(tag.get("class"), list) else str(tag.get("class", "")),
                str(tag.get("id", "")),
                str(tag.get("role", "")),
            ])

            # Rule 1: Explicit negative hints + moderate link density -> Boilerplate
            has_negative_hint = bool(NEGATIVE_HINTS.search(class_id_str))
            has_positive_hint = bool(POSITIVE_HINTS.search(class_id_str))

            if has_negative_hint and not has_positive_hint and link_density >= 0.25:
                to_remove.append(tag)
                continue

            # Rule 2: High link density (> threshold) with multiple links -> Link Farm / Menu
            num_links = len(tag.find_all("a"))
            if link_density > self.link_density_threshold and num_links >= 3 and not has_positive_hint:
                to_remove.append(tag)
                continue

            score = self.score_element(tag)
            candidates.append((tag, score))

        # De-duplicate removal: do not remove children if parent is already being removed
        final_to_remove: Set[Tag] = set()
        for tag in to_remove:
            # Check if any ancestor is also in to_remove
            has_ancestor_in_list = any(ancestor in to_remove for ancestor in tag.parents)
            if not has_ancestor_in_list:
                final_to_remove.add(tag)

        candidates_count = len(final_to_remove)
        removed_count = 0
        if prune:
            for tag in final_to_remove:
                tag.decompose()
                removed_count += 1

        # Identify dominant content container
        dominant_tag_str = ""
        highest_score = 0.0
        for tag, score in candidates:
            # Verify tag is still in DOM (not decomposed)
            if tag.parent and score > highest_score:
                highest_score = score
                tag_id = f"#{tag['id']}" if tag.get("id") else ""
                classes = f".{'.'.join(tag.get('class', []))}" if tag.get("class") and isinstance(tag.get("class"), list) else ""
                dominant_tag_str = f"{tag.name}{tag_id}{classes}"

        # Global document statistics after cleaning
        body = soup.body or soup
        body_text = body.get_text(" ", strip=True)
        overall_text_len = len(body_text)
        overall_tag_count = len(body.find_all(True)) + 1
        overall_text_density = overall_text_len / overall_tag_count if overall_tag_count > 0 else 0.0

        link_len = sum(len(a.get_text(" ", strip=True)) for a in body.find_all("a"))
        overall_link_density = (link_len / overall_text_len) if overall_text_len > 0 else 0.0

        # Overall semantic score normalized between 0.0 and 100.0
        normalized_score = min(100.0, highest_score * 0.5)

        return SemanticDensityReport(
            overall_text_density=round(overall_text_density, 2),
            overall_link_density=round(overall_link_density, 4),
            semantic_density_score=round(normalized_score, 2),
            nodes_evaluated=nodes_evaluated,
            boilerplate_candidates_count=candidates_count,
            boilerplate_nodes_removed=removed_count,
            dominant_container_tag=dominant_tag_str,
        )
