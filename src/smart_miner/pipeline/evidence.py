"""Subsystem 14: Trilogy Evidence Artifact Builder & Grounding Packager.

Provides deterministic SHA-256 provenance hashing, token-budget-aware chunking,
and standardized prompt-grounding serialization for the Haiox AI Trilogy:
Haiox Smart Miner -> Haiox MultiAgent -> Haiox Orchestrator.
"""

from __future__ import annotations

import datetime
import hashlib
import math
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceChunk(BaseModel):
    """A bounded segment of document content engineered for LLM context windows."""
    chunk_id: str = Field(description="Unique identifier (e.g. chunk-0, chunk-1)")
    chunk_index: int = Field(description="0-based sequence order")
    section_heading: str = Field(default="Root", description="Active heading context")
    content: str = Field(description="Markdown content for this chunk")
    char_count: int = Field(description="Total character count")
    estimated_tokens: int = Field(description="Estimated LLM tokens (~4 chars per token)")
    chunk_sha256: str = Field(description="Cryptographic SHA-256 digest of chunk content")


class EvidenceProvenance(BaseModel):
    """Audit trail verifying the origin, network shield security, and fetch fidelity."""
    strategy: str = Field(default="static", description="Ingestion strategy ('static', 'browser')")
    fetch_status_code: int = Field(default=200, description="HTTP response code")
    content_sha256: str = Field(description="Cryptographic SHA-256 digest of the entire clean markdown")
    timing_ms: Dict[str, float] = Field(default_factory=dict, description="Latency breakdown in milliseconds")
    security_verified: bool = Field(default=True, description="Passed Zero-Trust SSRF & IP filters")
    bounded_stream_verified: bool = Field(default=True, description="Passed 5MB anti-DoS streaming bound")
    fingerprint_mode: str = Field(default="balanced", description="Fingerprint matrix profile")


class EvidenceArtifact(BaseModel):
    """Standardized, verifiable grounding packet consumed by MultiAgent and Orchestrator."""
    source_url: str = Field(description="Original target or fetch URL")
    canonical_url: Optional[str] = Field(default=None, description="Resolved canonical URL from metadata")
    document_title: str = Field(default="", description="Cleaned title of the document")
    content_sha256: str = Field(description="Cryptographic SHA-256 digest of the full markdown")
    total_chars: int = Field(description="Total markdown character count")
    total_estimated_tokens: int = Field(description="Total estimated token count")
    created_at: str = Field(description="ISO 8601 UTC creation timestamp")
    provenance: EvidenceProvenance = Field(description="Source provenance and security audit")
    chunks: List[EvidenceChunk] = Field(default_factory=list, description="Grounding chunks")
    entities_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of parsed entities")

    def verify_integrity(self, content: Optional[str] = None) -> bool:
        """Verify that content matches the cryptographic content_sha256."""
        if content is None:
            # Reconstruct from chunks if available
            reconstructed = "\n\n".join(c.content for c in self.chunks)
            expected = hashlib.sha256(reconstructed.encode("utf-8")).hexdigest()
            return expected == self.content_sha256
        computed = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
        return computed == self.content_sha256

    def format_grounding_prompt(self, max_tokens: Optional[int] = None) -> str:
        """Render a standardized GFM XML grounding prompt block for LLM prompts."""
        lines = [
            f'<haiox_evidence source="{self.source_url}" sha256="{self.content_sha256}">',
            f"  <metadata>",
            f"    <title>{self.document_title}</title>",
            f"    <canonical>{self.canonical_url or self.source_url}</canonical>",
            f"    <strategy>{self.provenance.strategy}</strategy>",
            f"    <verified>{self.provenance.security_verified}</verified>",
            f"  </metadata>",
            f"  <content>",
        ]

        accumulated_tokens = 0
        for chunk in self.chunks:
            if max_tokens and (accumulated_tokens + chunk.estimated_tokens) > max_tokens:
                lines.append(f"    <!-- Remaining {len(self.chunks) - chunk.chunk_index} chunks truncated by token budget -->")
                break
            lines.append(f'    <chunk id="{chunk.chunk_id}" heading="{chunk.section_heading}" sha256="{chunk.chunk_sha256}">')
            for content_line in chunk.content.splitlines():
                lines.append(f"      {content_line}")
            lines.append("    </chunk>")
            accumulated_tokens += chunk.estimated_tokens

        lines.append("  </content>")
        lines.append("</haiox_evidence>")
        return "\n".join(lines)


class EvidenceBuilder:
    """Constructs verified EvidenceArtifacts from CleanDocument models."""

    def __init__(self, default_chunk_tokens: int = 600, chars_per_token: int = 4):
        self.default_chunk_tokens = default_chunk_tokens
        self.chars_per_token = chars_per_token

    def _estimate_tokens(self, text: str) -> int:
        return max(1, math.ceil(len(text) / self.chars_per_token))

    def _split_into_chunks(self, markdown: str, chunk_token_limit: int) -> List[EvidenceChunk]:
        """Split markdown intelligently along headings and paragraphs."""
        if not markdown.strip():
            return []

        max_chars = chunk_token_limit * self.chars_per_token
        # Split by ATX headings (# ... or ## ...)
        sections = re.split(r"(?m)(?=^#{1,6}\s+)", markdown)
        raw_blocks: List[tuple[str, str]] = []  # (heading, text)

        current_heading = "Overview"
        for sec in sections:
            sec_strip = sec.strip()
            if not sec_strip:
                continue
            lines = sec_strip.splitlines()
            if lines[0].startswith("#"):
                current_heading = lines[0].lstrip("#").strip()
            raw_blocks.append((current_heading, sec_strip))

        chunks: List[EvidenceChunk] = []
        chunk_idx = 0

        for heading, block_text in raw_blocks:
            if len(block_text) <= max_chars:
                chunk_hash = hashlib.sha256(block_text.encode("utf-8")).hexdigest()
                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"chunk-{chunk_idx}",
                        chunk_index=chunk_idx,
                        section_heading=heading,
                        content=block_text,
                        char_count=len(block_text),
                        estimated_tokens=self._estimate_tokens(block_text),
                        chunk_sha256=chunk_hash,
                    )
                )
                chunk_idx += 1
            else:
                # Sub-split oversized block by double-newlines
                paragraphs = block_text.split("\n\n")
                current_buf: List[str] = []
                current_len = 0

                for para in paragraphs:
                    if (current_len + len(para) + 2) > max_chars and current_buf:
                        sub_text = "\n\n".join(current_buf).strip()
                        sub_hash = hashlib.sha256(sub_text.encode("utf-8")).hexdigest()
                        chunks.append(
                            EvidenceChunk(
                                chunk_id=f"chunk-{chunk_idx}",
                                chunk_index=chunk_idx,
                                section_heading=heading,
                                content=sub_text,
                                char_count=len(sub_text),
                                estimated_tokens=self._estimate_tokens(sub_text),
                                chunk_sha256=sub_hash,
                            )
                        )
                        chunk_idx += 1
                        current_buf = [para]
                        current_len = len(para)
                    else:
                        current_buf.append(para)
                        current_len += len(para) + 2

                if current_buf:
                    sub_text = "\n\n".join(current_buf).strip()
                    sub_hash = hashlib.sha256(sub_text.encode("utf-8")).hexdigest()
                    chunks.append(
                        EvidenceChunk(
                            chunk_id=f"chunk-{chunk_idx}",
                            chunk_index=chunk_idx,
                            section_heading=heading,
                            content=sub_text,
                            char_count=len(sub_text),
                            estimated_tokens=self._estimate_tokens(sub_text),
                            chunk_sha256=sub_hash,
                        )
                    )
                    chunk_idx += 1

        return chunks

    def build_artifact(
        self,
        document: Any,
        strategy: str = "static",
        status_code: int = 200,
        timing_ms: Optional[Dict[str, float]] = None,
        security_verified: bool = True,
        bounded_stream_verified: bool = True,
        fingerprint_mode: str = "balanced",
        chunk_token_limit: Optional[int] = None,
    ) -> EvidenceArtifact:
        """Produce a validated EvidenceArtifact from a CleanDocument."""
        token_limit = chunk_token_limit or self.default_chunk_tokens
        markdown = document.markdown.strip() if hasattr(document, "markdown") and document.markdown else ""
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest() if markdown else "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        chunks = self._split_into_chunks(markdown, token_limit)

        provenance = EvidenceProvenance(
            strategy=strategy,
            fetch_status_code=status_code,
            content_sha256=content_hash,
            timing_ms=timing_ms or {},
            security_verified=security_verified,
            bounded_stream_verified=bounded_stream_verified,
            fingerprint_mode=fingerprint_mode,
        )

        canonical_url = None
        if hasattr(document, "metadata") and document.metadata:
            canonical_url = getattr(document.metadata, "canonical_url", None)

        entities_summary: Dict[str, Any] = {}
        if hasattr(document, "json_ld_graph") and document.json_ld_graph:
            graph = document.json_ld_graph
            entities_summary = {
                "total_nodes": getattr(graph, "total_nodes", 0),
                "articles_count": len(getattr(graph, "articles", [])),
                "products_count": len(getattr(graph, "products", [])),
                "faqs_count": len(getattr(graph, "faqs", [])),
                "canonical_main_entity_type": getattr(graph, "canonical_main_entity_type", None),
            }

        if hasattr(document, "tables") and document.tables:
            entities_summary["tables_count"] = len(document.tables)

        if hasattr(document, "outline") and document.outline:
            entities_summary["headings_count"] = len(getattr(document.outline, "flat_headings", []))

        total_chars = len(markdown)
        total_tokens = self._estimate_tokens(markdown)

        return EvidenceArtifact(
            source_url=getattr(document, "source_url", ""),
            canonical_url=canonical_url,
            document_title=getattr(document, "title", ""),
            content_sha256=content_hash,
            total_chars=total_chars,
            total_estimated_tokens=total_tokens,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            provenance=provenance,
            chunks=chunks,
            entities_summary=entities_summary,
        )
