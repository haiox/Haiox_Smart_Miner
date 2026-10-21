"""OpenGraph, Twitter Cards & Semantic Metadata Harvester.

Extracts, standardizes, resolves, and normalizes rich publication metadata,
authorship attribution, canonical URLs, OpenGraph properties, Twitter Cards,
and reading time estimates from HTML headers and DOM tags.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


class MetadataHarvest(BaseModel):
    """Normalized metadata describing publication context, provenance, and social cards."""
    title: str = ""
    description: str = ""
    author: str = ""
    published_time: str = ""
    modified_time: str = ""
    canonical_url: str = ""
    site_name: str = ""
    locale: str = ""
    og_type: str = ""
    image_url: str = ""
    twitter_card: str = ""
    twitter_creator: str = ""
    keywords: List[str] = Field(default_factory=list)
    reading_time_minutes: int = 0
    raw_meta: Dict[str, str] = Field(default_factory=dict)


class MetadataHarvester:
    """Scans and extracts standard, OpenGraph, and Twitter Card metadata from HTML DOM."""

    def __init__(self, *, words_per_minute: int = 200):
        self.words_per_minute = max(50, words_per_minute)

    def harvest(
        self,
        soup: BeautifulSoup,
        base_url: str,
        text_content: str = "",
    ) -> MetadataHarvest:
        """Extracts and standardizes all available metadata from the BeautifulSoup tree."""
        raw_meta: Dict[str, str] = {}

        # 1. Collect all <meta> tags
        for tag in soup.find_all("meta"):
            content = tag.get("content") or tag.get("value")
            if not content or not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            # Identify key attribute: property, name, itemprop, or http-equiv
            key = (
                tag.get("property")
                or tag.get("name")
                or tag.get("itemprop")
                or tag.get("http-equiv")
            )
            if key and isinstance(key, str):
                norm_key = key.strip().lower()
                # Do not overwrite earlier more specific properties
                if norm_key not in raw_meta:
                    raw_meta[norm_key] = content

        # 2. Extract Title
        title = (
            raw_meta.get("og:title")
            or raw_meta.get("twitter:title")
            or raw_meta.get("title")
            or ""
        )
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)

        # 3. Extract Description
        description = (
            raw_meta.get("og:description")
            or raw_meta.get("twitter:description")
            or raw_meta.get("description")
            or raw_meta.get("dc.description")
            or ""
        )

        # 4. Extract Author
        author = (
            raw_meta.get("author")
            or raw_meta.get("article:author")
            or raw_meta.get("og:article:author")
            or raw_meta.get("twitter:creator")
            or raw_meta.get("dc.creator")
            or ""
        )

        # 5. Extract Publication & Modification Timestamps
        published_time = (
            raw_meta.get("article:published_time")
            or raw_meta.get("og:published_time")
            or raw_meta.get("publication_date")
            or raw_meta.get("date")
            or raw_meta.get("dc.date")
            or raw_meta.get("dc.date.issued")
            or ""
        )
        modified_time = (
            raw_meta.get("article:modified_time")
            or raw_meta.get("og:modified_time")
            or raw_meta.get("last-modified")
            or raw_meta.get("dc.date.modified")
            or ""
        )

        # 6. Extract Canonical URL
        canonical_url = ""
        link_canonical = soup.find("link", rel=lambda r: r and "canonical" in r.lower() if isinstance(r, str) else False)
        if link_canonical and link_canonical.get("href"):
            canonical_url = urljoin(base_url, link_canonical["href"].strip())
        elif raw_meta.get("og:url"):
            canonical_url = urljoin(base_url, raw_meta["og:url"].strip())

        # 7. Extract Feature Image URL
        image_url = (
            raw_meta.get("og:image")
            or raw_meta.get("og:image:url")
            or raw_meta.get("og:image:secure_url")
            or raw_meta.get("twitter:image")
            or raw_meta.get("twitter:image:src")
            or ""
        )
        if image_url:
            image_url = urljoin(base_url, image_url.strip())

        # 8. Extract Site Name, Locale, and Type
        site_name = raw_meta.get("og:site_name") or raw_meta.get("twitter:site") or ""
        locale = raw_meta.get("og:locale") or ""
        og_type = raw_meta.get("og:type") or ""

        # 9. Extract Twitter Specifics
        twitter_card = raw_meta.get("twitter:card") or ""
        twitter_creator = raw_meta.get("twitter:creator") or ""

        # 10. Extract Keywords
        keywords: List[str] = []
        raw_keywords = raw_meta.get("keywords") or raw_meta.get("news_keywords") or ""
        if raw_keywords:
            keywords = [k.strip() for k in re.split(r"[,;]+", raw_keywords) if k.strip()]

        # 11. Calculate Reading Time
        reading_time = 0
        if text_content:
            word_count = len(re.findall(r"\w+", text_content))
            reading_time = max(1, round(word_count / self.words_per_minute))

        return MetadataHarvest(
            title=title,
            description=description,
            author=author,
            published_time=published_time,
            modified_time=modified_time,
            canonical_url=canonical_url,
            site_name=site_name,
            locale=locale,
            og_type=og_type,
            image_url=image_url,
            twitter_card=twitter_card,
            twitter_creator=twitter_creator,
            keywords=keywords,
            reading_time_minutes=reading_time,
            raw_meta=raw_meta,
        )
