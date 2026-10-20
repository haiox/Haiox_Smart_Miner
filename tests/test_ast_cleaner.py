"""Unit & integration tests for Subsystem 8: High-Performance AST HTML Cleaner."""

import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.ast_cleaner import ASTCleaner, ASTCleanReport
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class ASTCleanerUnitTests(unittest.TestCase):
    def setUp(self):
        self.cleaner = ASTCleaner()

    def test_strip_disallowed_tags(self):
        html = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Real Heading</h1>
                <script>console.log("tracking code");</script>
                <style>body { background: #000; }</style>
                <noscript><p>Please enable JS</p></noscript>
                <svg width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>
                <canvas id="myCanvas"></canvas>
                <iframe src="https://ad.example.com"></iframe>
                <template><p>Unrendered template</p></template>
                <p>Real paragraph text that must survive.</p>
            </body>
        </html>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn("Real Heading", cleaned)
        self.assertIn("Real paragraph text that must survive.", cleaned)
        self.assertNotIn("console.log", cleaned)
        self.assertNotIn("background: #000", cleaned)
        self.assertNotIn("Please enable JS", cleaned)
        self.assertNotIn("<svg", cleaned)
        self.assertNotIn("<canvas", cleaned)
        self.assertNotIn("<iframe", cleaned)
        self.assertNotIn("<template", cleaned)
        self.assertGreater(report.tags_removed_count, 5)

    def test_strip_cookie_consent_banners(self):
        html = """
        <div>
            <div id="onetrust-consent-sdk">
                <h3>We use cookies</h3>
                <button>Accept All</button>
            </div>
            <div class="cookie-banner cookie-consent">
                <p>This website stores cookies on your device.</p>
            </div>
            <article>
                <h1>Deep Learning Breakthroughs</h1>
                <p>Actual article content explaining neural architectures.</p>
            </article>
            <div id="cookie-law-info-bar">
                <span>By continuing you agree</span>
            </div>
        </div>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn("Deep Learning Breakthroughs", cleaned)
        self.assertIn("Actual article content explaining neural architectures.", cleaned)
        self.assertNotIn("We use cookies", cleaned)
        self.assertNotIn("This website stores cookies", cleaned)
        self.assertNotIn("By continuing you agree", cleaned)
        self.assertNotIn("onetrust-consent-sdk", cleaned)

    def test_strip_ads_and_promotional_modals(self):
        html = """
        <main>
            <div class="ad-container top-leaderboard">
                <ins class="adsbygoogle" style="display:block"></ins>
            </div>
            <h1>Quarterly Financial Report</h1>
            <p>Revenue increased by 34% year-over-year.</p>
            <aside class="sidebar-ad">
                <div id="taboola-ad-widget">Sponsored Stories</div>
            </aside>
            <div class="modal-backdrop" aria-modal="true" role="dialog">
                <div class="newsletter-popup">Subscribe to our newsletter!</div>
            </div>
        </main>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn("Quarterly Financial Report", cleaned)
        self.assertIn("Revenue increased by 34% year-over-year.", cleaned)
        self.assertNotIn("adsbygoogle", cleaned)
        self.assertNotIn("Sponsored Stories", cleaned)
        self.assertNotIn("Subscribe to our newsletter!", cleaned)

    def test_strip_inline_styles_and_event_handlers(self):
        html = """
        <div style="margin: 0; padding: 20px; font-family: Roboto, sans-serif; background-color: #fff;">
            <a href="https://haiox.ai" onclick="trackClickEvent(1234)" onmouseover="highlight(this)">Haiox AI</a>
            <button onload="init()" onerror="handleError()">Submit</button>
        </div>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn('href="https://haiox.ai"', cleaned)
        self.assertNotIn("font-family", cleaned)
        self.assertNotIn("background-color", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("onmouseover", cleaned)
        self.assertNotIn("onload", cleaned)
        self.assertNotIn("onerror", cleaned)
        self.assertGreater(report.attributes_stripped_count, 3)

    def test_strip_analytics_and_framework_attributes(self):
        html = """
        <article data-v-8493021="" ng-app="myApp" data-reactroot="">
            <h2 data-track="title_click" data-gtm-event="view" data-analytics-id="991">Clean Title</h2>
            <p data-sentry-component="ArticleBody">Semantic body text.</p>
        </article>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn("Clean Title", cleaned)
        self.assertIn("Semantic body text.", cleaned)
        self.assertNotIn("data-v-", cleaned)
        self.assertNotIn("ng-app", cleaned)
        self.assertNotIn("data-reactroot", cleaned)
        self.assertNotIn("data-track", cleaned)
        self.assertNotIn("data-gtm", cleaned)
        self.assertNotIn("data-analytics", cleaned)
        self.assertNotIn("data-sentry", cleaned)

    def test_preserve_semantic_attributes(self):
        html = """
        <table>
            <tr>
                <th colspan="2" rowspan="1">Header</th>
            </tr>
            <tr>
                <td><a href="https://example.com" title="Example Link" id="main-link">Click Here</a></td>
                <td><img src="https://example.com/logo.png" alt="Company Logo" name="brand-img"/></td>
            </tr>
        </table>
        """
        cleaned, _ = self.cleaner.clean_html(html)
        self.assertIn('colspan="2"', cleaned)
        self.assertIn('rowspan="1"', cleaned)
        self.assertIn('href="https://example.com"', cleaned)
        self.assertIn('title="Example Link"', cleaned)
        self.assertIn('alt="Company Logo"', cleaned)
        self.assertIn('src="https://example.com/logo.png"', cleaned)
        self.assertIn('id="main-link"', cleaned)

    def test_prune_empty_structural_tags(self):
        html = """
        <div>
            <div></div>
            <span></span>
            <p>   </p>
            <section></section>
            <p>Survivor paragraph text</p>
        </div>
        """
        cleaned, report = self.cleaner.clean_html(html)
        self.assertIn("Survivor paragraph text", cleaned)
        soup = BeautifulSoup(cleaned, "html.parser")
        paragraphs = soup.find_all("p")
        self.assertEqual(len(paragraphs), 1)

    def test_clean_report_telemetry_metrics(self):
        html = """
        <html><body>
            <div style="font-size:12px; color:red;" onclick="noop()">
                <script>var x = 1;</script>
                <!-- A long comment about nothing -->
                <p>Essential semantic text.</p>
            </div>
        </body></html>
        """
        _, report = self.cleaner.clean_html(html)
        self.assertIsInstance(report, ASTCleanReport)
        self.assertGreater(report.original_char_count, report.cleaned_char_count)
        self.assertGreater(report.tags_removed_count, 0)
        self.assertGreater(report.attributes_stripped_count, 0)
        self.assertGreater(report.noise_reduction_percentage, 0.0)


class DocumentCleanerASTIntegrationTests(unittest.TestCase):
    def test_document_cleaner_integrates_ast_cleaner_and_records_reduction(self):
        bloated_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Quantum Computing Advances</title>
            <script type="application/ld+json">{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Quantum"}</script>
        </head>
        <body style="margin: 0; background-color: #f0f0f0;">
            <div id="onetrust-consent-sdk"><p>Cookie Notice</p></div>
            <div class="ad-container"><ins class="adsbygoogle">Ad Content</ins></div>
            <article>
                <h1>Quantum Supremacy Reached</h1>
                <p style="color: blue;" onclick="analytics(1)">A new 1000-qubit processor solved the benchmark in 3 minutes.</p>
            </article>
            <svg viewBox="0 0 100 100"><path d="M10 10 H 90 V 90 H 10 L 10 10"/></svg>
        </body>
        </html>
        """
        page = FetchedPage(bloated_html, "https://example.com/quantum", 200)
        doc = DocumentCleaner().clean(page)

        self.assertIsInstance(doc, CleanDocument)
        self.assertEqual(doc.title, "Quantum Computing Advances")
        self.assertIn("# Quantum Supremacy Reached", doc.markdown)
        self.assertIn("A new 1000-qubit processor solved the benchmark in 3 minutes.", doc.markdown)
        # Verify bloat was completely eradicated
        self.assertNotIn("Cookie Notice", doc.markdown)
        self.assertNotIn("Ad Content", doc.markdown)
        self.assertNotIn("color: blue", doc.markdown)
        self.assertNotIn("analytics(1)", doc.markdown)
        self.assertNotIn("<svg", doc.markdown)
        # Verify telemetry
        self.assertGreater(doc.noise_reduction_percentage, 20.0)
        self.assertEqual(doc.json_ld[0]["headline"], "Quantum")
