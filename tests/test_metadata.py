"""Unit & integration tests for Subsystem 12: OpenGraph, Twitter Cards & Metadata Harvester."""

import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.metadata import (
    MetadataHarvest,
    MetadataHarvester,
)
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class MetadataHarvesterUnitTests(unittest.TestCase):
    def setUp(self):
        self.harvester = MetadataHarvester(words_per_minute=200)

    def test_opengraph_properties_extraction(self):
        html = """
        <html>
            <head>
                <meta property="og:title" content="DePIN Protocols & AI Mining">
                <meta property="og:description" content="Decentralized physical infrastructure network analysis.">
                <meta property="og:image" content="/images/depin-hero.jpg">
                <meta property="og:site_name" content="Haiox Research Labs">
                <meta property="og:type" content="article">
                <meta property="og:locale" content="en_US">
            </head>
            <body><p>Content</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/research/")

        self.assertEqual(meta.title, "DePIN Protocols & AI Mining")
        self.assertEqual(meta.description, "Decentralized physical infrastructure network analysis.")
        self.assertEqual(meta.image_url, "https://haiox.ai/images/depin-hero.jpg")
        self.assertEqual(meta.site_name, "Haiox Research Labs")
        self.assertEqual(meta.og_type, "article")
        self.assertEqual(meta.locale, "en_US")

    def test_twitter_card_properties_extraction(self):
        html = """
        <html>
            <head>
                <meta name="twitter:card" content="summary_large_image">
                <meta name="twitter:creator" content="@haioxlab">
                <meta name="twitter:title" content="Haiox Smart Miner v1.5.5">
                <meta name="twitter:description" content="Bedrock data ingestion engine.">
                <meta name="twitter:image" content="https://cdn.haiox.ai/card.png">
            </head>
            <body><p>Content</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/")

        self.assertEqual(meta.twitter_card, "summary_large_image")
        self.assertEqual(meta.twitter_creator, "@haioxlab")
        self.assertEqual(meta.title, "Haiox Smart Miner v1.5.5")
        self.assertEqual(meta.description, "Bedrock data ingestion engine.")
        self.assertEqual(meta.image_url, "https://cdn.haiox.ai/card.png")

    def test_canonical_url_resolution(self):
        html = """
        <html>
            <head>
                <link rel="canonical" href="/whitepaper/v2/">
            </head>
            <body><p>Content</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/docs/intro")

        self.assertEqual(meta.canonical_url, "https://haiox.ai/whitepaper/v2/")

    def test_author_and_publication_timestamps(self):
        html = """
        <html>
            <head>
                <meta name="author" content="Hatef (haiox)">
                <meta property="article:published_time" content="2026-10-21T03:00:00Z">
                <meta property="article:modified_time" content="2026-10-21T03:15:00Z">
            </head>
            <body><p>Content</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/blog")

        self.assertEqual(meta.author, "Hatef (haiox)")
        self.assertEqual(meta.published_time, "2026-10-21T03:00:00Z")
        self.assertEqual(meta.modified_time, "2026-10-21T03:15:00Z")

    def test_keywords_parsing(self):
        html = """
        <html>
            <head>
                <meta name="keywords" content="smart-miner, depin, web-scraping, zero-trust, python">
            </head>
            <body><p>Content</p></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/")

        self.assertEqual(meta.keywords, ["smart-miner", "depin", "web-scraping", "zero-trust", "python"])

    def test_reading_time_estimation(self):
        # 400 words at 200 words/min = 2 minutes
        text = "word " * 400
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        meta = self.harvester.harvest(soup, "https://haiox.ai/", text_content=text)

        self.assertEqual(meta.reading_time_minutes, 2)


class MetadataHarvesterIntegrationTests(unittest.TestCase):
    def test_document_cleaner_integration_and_pydantic_roundtrip(self):
        html = """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Page Fallback Title</title>
                <meta property="og:title" content="Master Plan for Haiox Ecosystem">
                <meta property="og:description" content="Detailed trilogy roadmap.">
                <meta property="og:image" content="/assets/architecture.png">
                <meta name="author" content="AIrash">
                <link rel="canonical" href="https://haiox.ai/master-plan">
            </head>
            <body>
                <main>
                    <h1>Master Plan Overview</h1>
                    <p>""" + ("Prose explaining autonomous multi-agent systems and decentralized data networks. " * 30) + """</p>
                </main>
            </body>
        </html>
        """
        page = FetchedPage(
            html=html,
            source_url="https://haiox.ai/overview",
            status_code=200,
        )
        cleaner = DocumentCleaner()
        doc = cleaner.clean(page)

        self.assertIsInstance(doc.metadata, MetadataHarvest)
        self.assertEqual(doc.metadata.title, "Master Plan for Haiox Ecosystem")
        self.assertEqual(doc.metadata.author, "AIrash")
        self.assertEqual(doc.metadata.canonical_url, "https://haiox.ai/master-plan")
        self.assertEqual(doc.metadata.image_url, "https://haiox.ai/assets/architecture.png")
        self.assertGreaterEqual(doc.metadata.reading_time_minutes, 1)

        # Full Pydantic JSON Roundtrip Verification
        dumped = doc.model_dump_json()
        validated = CleanDocument.model_validate_json(dumped)
        self.assertEqual(validated, doc)
        self.assertEqual(validated.metadata.author, "AIrash")


if __name__ == "__main__":
    unittest.main()
