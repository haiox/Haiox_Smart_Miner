"""Unit & integration tests for Subsystem 11: Semantic Density & Boilerplate Scorer."""

import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.density import (
    SemanticDensityReport,
    SemanticDensityScorer,
)
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class SemanticDensityUnitTests(unittest.TestCase):
    def setUp(self):
        self.scorer = SemanticDensityScorer()

    def test_calculate_link_density(self):
        soup = BeautifulSoup("<p>Pure narrative text without hyperlinks.</p>", "html.parser")
        self.assertEqual(self.scorer.calculate_link_density(soup.find("p")), 0.0)

        soup_links = BeautifulSoup(
            "<div><a href='/1'>Link One</a> <a href='/2'>Link Two</a></div>",
            "html.parser",
        )
        self.assertAlmostEqual(self.scorer.calculate_link_density(soup_links.find("div")), 1.0, places=2)

        soup_mixed = BeautifulSoup(
            "<p>Learn more about our <a href='/tech'>technology</a> today.</p>",
            "html.parser",
        )
        density = self.scorer.calculate_link_density(soup_mixed.find("p"))
        self.assertTrue(0.1 < density < 0.4)

    def test_calculate_text_density(self):
        dense_soup = BeautifulSoup("<div>" + ("A" * 200) + "</div>", "html.parser")
        sparse_soup = BeautifulSoup(
            "<div><span><b><i><small>Short</small></i></b></span></div>",
            "html.parser",
        )
        dense_val = self.scorer.calculate_text_density(dense_soup.find("div"))
        sparse_val = self.scorer.calculate_text_density(sparse_soup.find("div"))
        self.assertTrue(dense_val > sparse_val * 5)

    def test_punctuation_weight_latin_and_persian(self):
        natural_latin = "The system is robust, resilient, and fast. Does it scale? Yes, completely!"
        natural_persian = "این سامانه، بسیار پایدار، سریع و مقیاس‌پذیر است؛ آیا تضمین شده است؟ بله."
        link_farm = "Apple Banana Orange Grapes Pineapple Mango Peach Plum"

        weight_latin = self.scorer.calculate_punctuation_weight(natural_latin)
        weight_persian = self.scorer.calculate_punctuation_weight(natural_persian)
        weight_farm = self.scorer.calculate_punctuation_weight(link_farm)

        self.assertTrue(weight_latin > 1.0)
        self.assertTrue(weight_persian > 1.0)
        self.assertTrue(weight_farm < 0.6)

    def test_score_element_positive_vs_negative_hints(self):
        content_text = "This is a detailed analysis of decentralized network protocols, latency benchmarks, and node distribution. " * 3
        soup_article = BeautifulSoup(f"<article class='entry-content post-body'><p>{content_text}</p></article>", "html.parser")
        soup_sidebar = BeautifulSoup(f"<aside class='sidebar-widget promo-banner'><p>{content_text}</p></aside>", "html.parser")

        score_article = self.scorer.score_element(soup_article.find("article"))
        score_sidebar = self.scorer.score_element(soup_sidebar.find("aside"))

        self.assertTrue(score_article > score_sidebar * 2)

    def test_clean_boilerplate_prunes_sidebars_and_link_farms(self):
        html = """
        <html>
            <body>
                <header><nav><a href='/'>Home</a></nav></header>
                <article id="main-content" class="post-entry">
                    <h1>Decentralized Web Crawling</h1>
                    <p>Web crawling requires resilience, low latency, and zero-trust security checks. We analyze throughput and network topologies across multiple regions.</p>
                    <p>In this study, benchmarks demonstrate over 1,000,000 DNS cache operations per second with bounded streaming limits preventing denial-of-service vulnerabilities.</p>
                </article>
                <aside class="sidebar-widget trending-topics">
                    <h3>Related Topics</h3>
                    <ul>
                        <li><a href="/topic/1">Trending Story 1</a></li>
                        <li><a href="/topic/2">Trending Story 2</a></li>
                        <li><a href="/topic/3">Trending Story 3</a></li>
                        <li><a href="/topic/4">Trending Story 4</a></li>
                    </ul>
                </aside>
                <div class="footer-links copyright-disclaimer">
                    <p>© 2026 Haiox Systems. All rights reserved.</p>
                    <a href="/privacy">Privacy</a> | <a href="/terms">Terms</a> | <a href="/cookies">Cookie Settings</a>
                </div>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        report = self.scorer.clean_boilerplate(soup, prune=True)

        self.assertGreaterEqual(report.boilerplate_nodes_removed, 1)
        self.assertIn("article#main-content", report.dominant_container_tag)
        self.assertIsNone(soup.find("aside", class_="sidebar-widget"))
        self.assertIsNotNone(soup.find("article", id="main-content"))

    def test_clean_boilerplate_prune_false_preserves_dom(self):
        html = """
        <div>
            <div class="sidebar-widget">
                <a href="/1">Link 1</a>
                <a href="/2">Link 2</a>
                <a href="/3">Link 3</a>
            </div>
            <div class="content-body">
                <p>Important article text with sufficient length, periods, and semantic prose.</p>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        report = self.scorer.clean_boilerplate(soup, prune=False)

        self.assertEqual(report.boilerplate_nodes_removed, 0)
        self.assertGreaterEqual(report.boilerplate_candidates_count, 1)
        # Verify sidebar was NOT decomposed when prune=False
        self.assertIsNotNone(soup.find("div", class_="sidebar-widget"))


class SemanticDensityIntegrationTests(unittest.TestCase):
    def test_document_cleaner_integration_default(self):
        html = """
        <!DOCTYPE html>
        <html>
            <head><title>Density Test Page</title></head>
            <body>
                <main id="primary-article">
                    <h1>Autonomous Data Mining</h1>
                    <p>Autonomous agents require clean context windows to prevent hallucination. High text density ensures optimal token allocation and prompt efficiency.</p>
                </main>
            </body>
        </html>
        """
        page = FetchedPage(
            html=html,
            source_url="https://example.test/density",
            status_code=200,
        )
        cleaner = DocumentCleaner()
        doc = cleaner.clean(page)

        self.assertIsInstance(doc.density, SemanticDensityReport)
        self.assertGreater(doc.density.overall_text_density, 0.0)
        self.assertIn("main#primary-article", doc.density.dominant_container_tag)

        # Full Pydantic roundtrip test
        dumped = doc.model_dump_json()
        validated = CleanDocument.model_validate_json(dumped)
        self.assertEqual(validated, doc)

    def test_document_cleaner_with_filter_boilerplate_active(self):
        html = """
        <!DOCTYPE html>
        <html>
            <head><title>Boilerplate Filter Test</title></head>
            <body>
                <main id="core-story">
                    <h1>Real Research Paper</h1>
                    <p>Detailed analysis of cryptographic verifiable claims in decentralized storage systems. The proof system utilizes zero-knowledge polynomial commitments.</p>
                </main>
                <aside class="sidebar-widget related-topics">
                    <h4>Related Articles</h4>
                    <a href="/story1">Story One</a>
                    <a href="/story2">Story Two</a>
                    <a href="/story3">Story Three</a>
                </aside>
            </body>
        </html>
        """
        page = FetchedPage(
            html=html,
            source_url="https://example.test/filter",
            status_code=200,
        )
        cleaner = DocumentCleaner(filter_boilerplate=True)
        doc = cleaner.clean(page)

        self.assertIn("Real Research Paper", doc.markdown)
        self.assertNotIn("Related Articles", doc.markdown)
        self.assertNotIn("Story One", doc.markdown)
        self.assertGreaterEqual(doc.density.boilerplate_nodes_removed, 1)


if __name__ == "__main__":
    unittest.main()
