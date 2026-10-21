"""JSON-LD Entity Graph Resolver & Schema.org Normalizer.

Unrolls '@graph' containers, resolves cross-node '@id' references with circular
protection, and standardizes canonical entities (Article, Product, FAQPage,
BreadcrumbList, Organization, Person) into structured, typed models.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Set, Union
from pydantic import BaseModel, Field


class ArticleEntity(BaseModel):
    """Normalized Schema.org Article / NewsArticle / BlogPosting entity."""
    headline: str = ""
    description: str = ""
    author: str = ""
    publisher: str = ""
    date_published: str = ""
    date_modified: str = ""


class ProductEntity(BaseModel):
    """Normalized Schema.org Product entity with pricing and rating metrics."""
    name: str = ""
    description: str = ""
    sku: str = ""
    price: Optional[float] = None
    currency: str = ""
    availability: str = ""
    rating_value: Optional[float] = None
    review_count: int = 0


class FAQItem(BaseModel):
    """A Question/Answer pair extracted from an FAQPage Schema."""
    question: str = ""
    answer: str = ""


class ResolvedEntityGraph(BaseModel):
    """Structured graph representation of all Schema.org entities in the document."""
    total_nodes: int = 0
    articles: List[ArticleEntity] = Field(default_factory=list)
    products: List[ProductEntity] = Field(default_factory=list)
    faqs: List[FAQItem] = Field(default_factory=list)
    breadcrumbs: List[str] = Field(default_factory=list)
    nodes_by_type: Dict[str, int] = Field(default_factory=dict)
    resolved_entities: List[Dict[str, Any]] = Field(default_factory=list)


def _get_types(node: Dict[str, Any]) -> List[str]:
    """Returns a list of Schema.org types for a node, handling single strings or lists."""
    type_val = node.get("@type", "")
    if isinstance(type_val, list):
        return [str(t).strip() for t in type_val if t]
    elif isinstance(type_val, str) and type_val.strip():
        return [type_val.strip()]
    return []


def _extract_name_or_text(val: Any) -> str:
    """Safely extracts a string or 'name' attribute from an entity reference."""
    if isinstance(val, str):
        return val.strip()
    elif isinstance(val, dict):
        return str(val.get("name") or val.get("legalName") or val.get("@id") or "").strip()
    elif isinstance(val, list) and val:
        names = [_extract_name_or_text(x) for x in val]
        return ", ".join([n for n in names if n])
    return ""


class JSONLDResolver:
    """Normalizes and resolves connected entity graphs from raw JSON-LD blobs."""

    def __init__(self, *, max_resolution_depth: int = 4):
        self.max_resolution_depth = max_resolution_depth

    def resolve(self, raw_json_ld_items: List[Any]) -> ResolvedEntityGraph:
        """Parses and cross-resolves all Schema.org entities across input JSON-LD items."""
        # 1. Unroll all items and '@graph' structures into a flat node list
        flat_nodes: List[Dict[str, Any]] = []
        for item in raw_json_ld_items:
            self._unroll_graphs(item, flat_nodes)

        # 2. Build index keyed by '@id'
        id_index: Dict[str, Dict[str, Any]] = {}
        for node in flat_nodes:
            node_id = node.get("@id")
            if node_id and isinstance(node_id, str):
                id_index[node_id] = node

        # 3. Resolve cross-node '@id' references
        resolved_nodes: List[Dict[str, Any]] = []
        for node in flat_nodes:
            resolved = self._deep_resolve(node, id_index, depth=0, seen_ids=set())
            resolved_nodes.append(resolved)

        # 4. Count node types and parse canonical entities
        nodes_by_type: Dict[str, int] = {}
        articles: List[ArticleEntity] = []
        products: List[ProductEntity] = []
        faqs: List[FAQItem] = []
        breadcrumbs: List[str] = []

        for node in resolved_nodes:
            types = _get_types(node)
            for t in types:
                nodes_by_type[t] = nodes_by_type.get(t, 0) + 1

            # Check Article
            if any(t in {"Article", "NewsArticle", "TechArticle", "BlogPosting", "Report"} for t in types):
                article = self._parse_article(node)
                if article.headline or article.description:
                    articles.append(article)

            # Check Product
            if any(t in {"Product", "IndividualProduct"} for t in types):
                product = self._parse_product(node)
                if product.name:
                    products.append(product)

            # Check FAQPage
            if "FAQPage" in types:
                faqs.extend(self._parse_faq(node))

            # Check BreadcrumbList
            if "BreadcrumbList" in types and not breadcrumbs:
                breadcrumbs.extend(self._parse_breadcrumbs(node))

        return ResolvedEntityGraph(
            total_nodes=len(resolved_nodes),
            articles=articles,
            products=products,
            faqs=faqs,
            breadcrumbs=breadcrumbs,
            nodes_by_type=nodes_by_type,
            resolved_entities=resolved_nodes,
        )

    def _unroll_graphs(self, item: Any, accumulator: List[Dict[str, Any]]) -> None:
        """Recursively traverses dictionaries and lists to extract all node entities."""
        if not isinstance(item, dict):
            if isinstance(item, list):
                for sub in item:
                    self._unroll_graphs(sub, accumulator)
            return

        if "@graph" in item and isinstance(item["@graph"], list):
            for sub_node in item["@graph"]:
                self._unroll_graphs(sub_node, accumulator)
        elif "@type" in item:
            accumulator.append(dict(item))
        else:
            # Check nested keys for embedded entities
            for v in item.values():
                if isinstance(v, (dict, list)):
                    self._unroll_graphs(v, accumulator)

    def _deep_resolve(
        self,
        value: Any,
        id_index: Dict[str, Dict[str, Any]],
        depth: int,
        seen_ids: Set[str],
    ) -> Any:
        """Recursively resolves '@id' references while preventing infinite circular loops."""
        if depth >= self.max_resolution_depth:
            return value

        if isinstance(value, dict):
            # Check if this dictionary is a reference: e.g. {"@id": "https://..."}
            ref_id = value.get("@id")
            if len(value) == 1 and ref_id and isinstance(ref_id, str):
                if ref_id in id_index and ref_id not in seen_ids:
                    return self._deep_resolve(
                        id_index[ref_id],
                        id_index,
                        depth + 1,
                        seen_ids | {ref_id},
                    )

            resolved_dict: Dict[str, Any] = {}
            for k, v in value.items():
                resolved_dict[k] = self._deep_resolve(v, id_index, depth + 1, seen_ids)
            return resolved_dict

        elif isinstance(value, list):
            return [self._deep_resolve(item, id_index, depth, seen_ids) for item in value]

        return value

    def _parse_article(self, node: Dict[str, Any]) -> ArticleEntity:
        """Standardizes an Article node into an ArticleEntity model."""
        headline = str(node.get("headline") or node.get("name") or "").strip()
        description = str(node.get("description") or "").strip()
        author = _extract_name_or_text(node.get("author"))
        publisher = _extract_name_or_text(node.get("publisher"))
        date_published = str(node.get("datePublished") or node.get("dateCreated") or "").strip()
        date_modified = str(node.get("dateModified") or "").strip()

        return ArticleEntity(
            headline=headline,
            description=description,
            author=author,
            publisher=publisher,
            date_published=date_published,
            date_modified=date_modified,
        )

    def _parse_product(self, node: Dict[str, Any]) -> ProductEntity:
        """Standardizes a Product node into a ProductEntity model."""
        name = str(node.get("name") or "").strip()
        description = str(node.get("description") or "").strip()
        sku = str(node.get("sku") or node.get("productID") or "").strip()

        # Parse Offers
        price: Optional[float] = None
        currency = ""
        availability = ""

        offers = node.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            raw_price = offers.get("price")
            if raw_price is not None:
                try:
                    price = float(raw_price)
                except (ValueError, TypeError):
                    pass
            currency = str(offers.get("priceCurrency") or "").strip()
            availability = str(offers.get("availability") or "").split("/")[-1].strip()

        # Parse AggregateRating
        rating_value: Optional[float] = None
        review_count = 0
        rating = node.get("aggregateRating")
        if isinstance(rating, dict):
            raw_rating = rating.get("ratingValue")
            if raw_rating is not None:
                try:
                    rating_value = float(raw_rating)
                except (ValueError, TypeError):
                    pass
            raw_reviews = rating.get("reviewCount") or rating.get("ratingCount")
            if raw_reviews is not None:
                try:
                    review_count = int(raw_reviews)
                except (ValueError, TypeError):
                    pass

        return ProductEntity(
            name=name,
            description=description,
            sku=sku,
            price=price,
            currency=currency,
            availability=availability,
            rating_value=rating_value,
            review_count=review_count,
        )

    def _parse_faq(self, node: Dict[str, Any]) -> List[FAQItem]:
        """Extracts Question and Answer pairs from an FAQPage node."""
        faqs: List[FAQItem] = []
        entities = node.get("mainEntity", [])
        if isinstance(entities, dict):
            entities = [entities]
        elif not isinstance(entities, list):
            return faqs

        for q in entities:
            if not isinstance(q, dict):
                continue
            question_text = str(q.get("name") or q.get("text") or "").strip()
            answer_node = q.get("acceptedAnswer") or q.get("suggestedAnswer")
            answer_text = ""
            if isinstance(answer_node, dict):
                answer_text = str(answer_node.get("text") or answer_node.get("name") or "").strip()
            elif isinstance(answer_node, list) and answer_node:
                first = answer_node[0]
                if isinstance(first, dict):
                    answer_text = str(first.get("text") or first.get("name") or "").strip()

            if question_text and answer_text:
                # Strip HTML tags if present in answer
                answer_clean = re.sub(r"<[^>]+>", " ", answer_text)
                answer_clean = re.sub(r"\s+", " ", answer_clean).strip()
                faqs.append(FAQItem(question=question_text, answer=answer_clean))

        return faqs

    def _parse_breadcrumbs(self, node: Dict[str, Any]) -> List[str]:
        """Extracts sorted breadcrumb steps from a BreadcrumbList node."""
        elements = node.get("itemListElement", [])
        if not isinstance(elements, list):
            return []

        # Sort elements by position if present
        def _get_pos(el: Any) -> int:
            if isinstance(el, dict):
                try:
                    return int(el.get("position", 0))
                except (ValueError, TypeError):
                    return 0
            return 0

        sorted_elements = sorted(elements, key=_get_pos)
        breadcrumbs: List[str] = []

        for el in sorted_elements:
            if isinstance(el, dict):
                # Breadcrumb item can be string or dict with 'name'
                name = ""
                item = el.get("item")
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                if not name:
                    name = str(el.get("name") or "").strip()
                if name:
                    breadcrumbs.append(name)

        return breadcrumbs
