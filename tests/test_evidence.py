"""Unit & integration tests for Subsystem 14: Trilogy Evidence Artifact Builder & Grounding Packager."""

import hashlib
import unittest
from unittest.mock import AsyncMock, patch

from smart_miner.pipeline.evidence import (
    EvidenceArtifact,
    EvidenceChunk,
    EvidenceProvenance,
    EvidenceBuilder,
)
from smart_miner.pipeline.document import CleanDocument
from smart_miner.pipeline.headings import DocumentOutline, HeadingItem
from smart_miner.pipeline.tables import TableData
from smart_miner.pipeline.metadata import MetadataHarvest
from smart_miner.pipeline.jsonld import ResolvedEntityGraph, ArticleEntity
from smart_miner.crawler.router import route


class EvidenceBuilderUnitTests(unittest.TestCase):
    def setUp(self):
        self.builder = EvidenceBuilder(default_chunk_tokens=100, chars_per_token=4)

    def test_sha256_integrity_verification(self):
        markdown = "# Title\n\nThis is verifiable text content."
        expected_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        
        doc = CleanDocument(
            source_url="https://example.com/article",
            title="Title",
            markdown=markdown,
            visible_text="Title This is verifiable text content.",
            input_character_count=len(markdown),
            output_character_count=len(markdown),
        )
        artifact = self.builder.build_artifact(doc)
        
        self.assertEqual(artifact.content_sha256, expected_hash)
        self.assertTrue(artifact.verify_integrity(markdown))
        self.assertFalse(artifact.verify_integrity(markdown + " tampered"))

    def test_split_into_chunks_by_headings(self):
        markdown = (
            "# Section 1\nContent for section 1.\n\n"
            "## Section 2\nContent for section 2.\n\n"
            "### Section 3\nContent for section 3."
        )
        doc = CleanDocument(
            source_url="https://example.com/headings",
            title="Multi-heading doc",
            markdown=markdown,
            visible_text="Multi-heading doc",
            input_character_count=len(markdown),
            output_character_count=len(markdown),
        )
        artifact = self.builder.build_artifact(doc)
        
        self.assertEqual(len(artifact.chunks), 3)
        self.assertEqual(artifact.chunks[0].section_heading, "Section 1")
        self.assertEqual(artifact.chunks[1].section_heading, "Section 2")
        self.assertEqual(artifact.chunks[2].section_heading, "Section 3")
        
        for chunk in artifact.chunks:
            self.assertTrue(chunk.chunk_sha256)
            self.assertGreater(chunk.estimated_tokens, 0)

    def test_split_oversized_section_by_paragraphs(self):
        # 1 token = 4 chars, default_chunk_tokens = 20 -> max_chars = 80
        p1 = "Paragraph 1 with enough content to be substantial."
        p2 = "Paragraph 2 with even more content that will exceed the budget."
        p3 = "Paragraph 3 trailing remarks."
        markdown = f"# Giant Section\n{p1}\n\n{p2}\n\n{p3}"
        
        small_builder = EvidenceBuilder(default_chunk_tokens=15, chars_per_token=4)
        doc = CleanDocument(
            source_url="https://example.com/oversized",
            title="Oversized",
            markdown=markdown,
            visible_text="Oversized",
            input_character_count=len(markdown),
            output_character_count=len(markdown),
        )
        artifact = small_builder.build_artifact(doc)
        
        # Must split into multiple sub-chunks
        self.assertGreater(len(artifact.chunks), 1)
        # All chunks must belong to "Giant Section"
        for chunk in artifact.chunks:
            self.assertEqual(chunk.section_heading, "Giant Section")

    def test_format_grounding_prompt(self):
        markdown = "# Architecture\nHaiox Smart Miner zero-leak network shield."
        doc = CleanDocument(
            source_url="https://haiox.ai/miner",
            title="Architecture",
            markdown=markdown,
            visible_text="Architecture Haiox Smart Miner",
            input_character_count=len(markdown),
            output_character_count=len(markdown),
        )
        artifact = self.builder.build_artifact(doc, strategy="browser")
        prompt = artifact.format_grounding_prompt()
        
        self.assertIn('<haiox_evidence source="https://haiox.ai/miner"', prompt)
        self.assertIn(f'sha256="{artifact.content_sha256}"', prompt)
        self.assertIn('<title>Architecture</title>', prompt)
        self.assertIn('<strategy>browser</strategy>', prompt)
        self.assertIn('<chunk id="chunk-0"', prompt)
        self.assertIn('</haiox_evidence>', prompt)

    def test_format_grounding_prompt_token_budget_truncation(self):
        markdown = (
            "# Part 1\nContent 1\n\n"
            "# Part 2\nContent 2\n\n"
            "# Part 3\nContent 3\n\n"
            "# Part 4\nContent 4"
        )
        doc = CleanDocument(
            source_url="https://example.com/parts",
            title="Parts",
            markdown=markdown,
            visible_text="Parts",
            input_character_count=len(markdown),
            output_character_count=len(markdown),
        )
        artifact = self.builder.build_artifact(doc)
        # Budget so low that not all chunks fit
        prompt = artifact.format_grounding_prompt(max_tokens=10)
        self.assertIn("truncated by token budget", prompt)

    def test_clean_document_to_evidence_artifact_roundtrip(self):
        meta = MetadataHarvest(canonical_url="https://example.com/canonical")
        outline = DocumentOutline(
            flat_headings=[HeadingItem(level=1, normalized_level=1, text="Main", slug="main")]
        )
        graph = ResolvedEntityGraph(
            total_nodes=2,
            articles=[ArticleEntity(headline="Article Headline")]
        )
        table = TableData(headers=["Col1", "Col2"], rows=[["V1", "V2"]])
        
        doc = CleanDocument(
            source_url="https://example.com/page",
            title="Page Title",
            markdown="# Main\nContent",
            visible_text="Main Content",
            input_character_count=100,
            output_character_count=50,
            metadata=meta,
            outline=outline,
            json_ld_graph=graph,
            tables=[table],
        )
        artifact = doc.to_evidence_artifact(
            strategy="static",
            status_code=200,
            timing_ms={"fetch": 45.2, "clean": 5.1},
            security_verified=True,
            bounded_stream_verified=True,
            fingerprint_mode="balanced",
        )
        
        self.assertEqual(artifact.source_url, "https://example.com/page")
        self.assertEqual(artifact.canonical_url, "https://example.com/canonical")
        self.assertEqual(artifact.provenance.strategy, "static")
        self.assertEqual(artifact.provenance.fetch_status_code, 200)
        self.assertEqual(artifact.provenance.timing_ms["fetch"], 45.2)
        self.assertTrue(artifact.provenance.security_verified)
        self.assertTrue(artifact.provenance.bounded_stream_verified)
        self.assertEqual(artifact.entities_summary["total_nodes"], 2)
        self.assertEqual(artifact.entities_summary["articles_count"], 1)
        self.assertEqual(artifact.entities_summary["tables_count"], 1)
        self.assertEqual(artifact.entities_summary["headings_count"], 1)
        
        # Test Pydantic serialization roundtrip
        dumped = artifact.model_dump()
        reloaded = EvidenceArtifact.model_validate(dumped)
        self.assertEqual(reloaded.content_sha256, artifact.content_sha256)
        self.assertEqual(len(reloaded.chunks), len(artifact.chunks))


class RouterEvidenceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_returns_evidence_artifact(self):
        article_text = (
            "Distributed autonomous agent architectures require resilient data ingestion engines "
            "to prevent hallucinations and ground inference on verifiable evidence. In modern enterprise "
            "pipelines, untrusted HTML documents must undergo multi-stage sanitization, including AST parsing, "
            "table grid reconstruction, Unicode heading hierarchy repair, and link density evaluation. "
            "Cryptographic SHA-256 digests provide end-to-end provenance guarantees, ensuring that downstream "
            "orchestrators receive tamper-proof context slices bounded by strict token budgets."
        )
        html = (
            "<!DOCTYPE html><html><head><title>Integration Evidence</title></head>"
            f"<body><main><h1>Deep Evidence</h1><p>{article_text}</p></main></body></html>"
        )
        from smart_miner.crawler.fetcher import FetchedPage
        from unittest.mock import MagicMock
        page = FetchedPage(
            html,
            "https://example.com/grounded",
            200,
            {"content-type": "text/html"},
        )
        fetcher = MagicMock(
            fetch_static=AsyncMock(return_value=page),
            fetch_dynamic=AsyncMock(return_value=page),
            active_profile_name="chrome_windows",
        )
        
        res = await route("https://example.com/grounded", min_text_length=100, fetcher=fetcher)
        self.assertTrue(res["success"])
        self.assertIn("evidence", res)
        self.assertIsNotNone(res["evidence"])
        
        ev = res["evidence"]
        self.assertEqual(ev["source_url"], "https://example.com/grounded")
        self.assertEqual(len(ev["content_sha256"]), 64)
        self.assertGreater(len(ev["chunks"]), 0)
        self.assertEqual(ev["provenance"]["strategy"], "static")
        self.assertTrue(ev["provenance"]["security_verified"])
