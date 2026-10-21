"""Unit & integration tests for Subsystem 10: Heading Hierarchy & Outline Synthesizer."""

import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.headings import (
    HeadingItem,
    DocumentOutline,
    HeadingHierarchyExtractor,
    slugify,
    clean_heading_text,
)
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class HeadingHierarchyUnitTests(unittest.TestCase):
    def setUp(self):
        self.extractor = HeadingHierarchyExtractor()

    def test_slugify_latin_persian_and_symbols(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")
        self.assertEqual(slugify("Haiox Smart Miner v1.5.3 (Fast & Secure)"), "haiox-smart-miner-v153-fast-secure")
        # Unicode Persian / Arabic test
        self.assertEqual(slugify("معماری سیستم Haiox: بخش اول"), "معماری-سیستم-haiox-بخش-اول")
        # Empty fallback
        self.assertEqual(slugify("???!!!"), "section")

    def test_clean_heading_text_removes_noise(self):
        html = """
        <h2>
            <span aria-hidden="true" class="octicon">#</span>
            <span class="sr-only">Direct link to heading</span>
            System Architecture
        </h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.find("h2")
        cleaned = clean_heading_text(h2)
        self.assertEqual(cleaned, "System Architecture")

    def test_extract_from_soup_linear_hierarchy(self):
        html = """
        <html>
            <body>
                <h1>Haiox AI Trilogy</h1>
                <p>Introduction paragraph.</p>
                <h2>Smart Miner Ingestion</h2>
                <p>Data layer.</p>
                <h3>Network Shield</h3>
                <p>SSRF and anti-DoS defenses.</p>
                <h3>AST Cleaner</h3>
                <p>DOM noise elimination.</p>
                <h2>MultiAgent Reasoning</h2>
                <p>Verification layer.</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup, page_title="Test Document")

        self.assertEqual(outline.total_count, 5)
        self.assertEqual(len(outline.flat_headings), 5)
        self.assertEqual(outline.max_depth, 3)
        self.assertFalse(outline.has_gaps)

        # Verify tree hierarchy: 1 root H1 ("Haiox AI Trilogy")
        self.assertEqual(len(outline.headings), 1)
        root = outline.headings[0]
        self.assertEqual(root.text, "Haiox AI Trilogy")
        self.assertEqual(root.level, 1)

        # Root H1 has 2 children (H2s)
        self.assertEqual(len(root.children), 2)
        h2_1, h2_2 = root.children
        self.assertEqual(h2_1.text, "Smart Miner Ingestion")
        self.assertEqual(h2_2.text, "MultiAgent Reasoning")

        # First H2 has 2 children (H3s)
        self.assertEqual(len(h2_1.children), 2)
        self.assertEqual(h2_1.children[0].text, "Network Shield")
        self.assertEqual(h2_1.children[1].text, "AST Cleaner")

    def test_extract_from_soup_duplicate_headings_slug_disambiguation(self):
        html = """
        <div>
            <h2>Overview</h2>
            <p>First overview.</p>
            <h2>Overview</h2>
            <p>Second overview.</p>
            <h2>Overview</h2>
            <p>Third overview.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)

        self.assertEqual(len(outline.flat_headings), 3)
        self.assertEqual(outline.flat_headings[0].slug, "overview")
        self.assertEqual(outline.flat_headings[1].slug, "overview-1")
        self.assertEqual(outline.flat_headings[2].slug, "overview-2")

    def test_extract_from_soup_skips_empty_and_oversized_headings(self):
        html = """
        <div>
            <h2></h2>
            <h3>   </h3>
            <h2>Valid Section</h2>
            <h1>""" + ("A" * 350) + """</h1>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)

        self.assertEqual(outline.total_count, 1)
        self.assertEqual(outline.flat_headings[0].text, "Valid Section")

    def test_hierarchy_gap_repair(self):
        # Skips H2 and H3, jumping straight from H1 to H4, then H6
        html = """
        <div>
            <h1>Main Title</h1>
            <h4>Deep Sub-Feature</h4>
            <h6>Ultra Deep Spec</h6>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)

        self.assertTrue(outline.has_gaps)
        self.assertEqual(len(outline.flat_headings), 3)

        # Original levels: 1, 4, 6
        self.assertEqual([h.level for h in outline.flat_headings], [1, 4, 6])
        # Normalized levels: 1, 2, 3
        self.assertEqual([h.normalized_level for h in outline.flat_headings], [1, 2, 3])
        self.assertEqual(outline.max_depth, 3)

    def test_explicit_id_or_name_anchor_preserved(self):
        html = """
        <div>
            <h2 id="custom-features-id">Our Features</h2>
            <h3 name="named-anchor">Specification</h3>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)

        self.assertEqual(outline.flat_headings[0].anchor, "custom-features-id")
        self.assertEqual(outline.flat_headings[0].slug, "custom-features-id")
        self.assertEqual(outline.flat_headings[1].anchor, "named-anchor")
        self.assertEqual(outline.flat_headings[1].slug, "named-anchor")

    def test_extract_from_markdown_atx(self):
        markdown = """
# Primary Heading

Paragraph text here.

## Secondary [Documentation](https://docs.example.com)

More text.

### Inner **Bold** & `Code` Spec #
        """
        outline = self.extractor.extract_from_markdown(markdown, page_title="MD Doc")

        self.assertEqual(outline.total_count, 3)
        self.assertEqual(outline.flat_headings[0].text, "Primary Heading")
        self.assertEqual(outline.flat_headings[1].text, "Secondary Documentation")
        self.assertEqual(outline.flat_headings[2].text, "Inner Bold & Code Spec")

    def test_to_markdown_toc_formatting(self):
        html = """
        <div>
            <h1>Document Title</h1>
            <h2>Section Alpha</h2>
            <h3>Subsection Alpha.1</h3>
            <h2>Section Beta</h2>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)
        toc = outline.to_markdown_toc(indent_spaces=2)

        expected_lines = [
            "- [Document Title](#document-title)",
            "  - [Section Alpha](#section-alpha)",
            "    - [Subsection Alpha.1](#subsection-alpha1)",
            "  - [Section Beta](#section-beta)",
        ]
        self.assertEqual(toc, "\n".join(expected_lines))

    def test_get_section_path_breadcrumbs(self):
        html = """
        <div>
            <h1>System Architecture</h1>
            <h2>Network Shield</h2>
            <h3>Zero-Trust SSRF</h3>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        outline = self.extractor.extract_from_soup(soup)

        path = outline.get_section_path("zero-trust-ssrf")
        self.assertEqual(path, ["System Architecture", "Network Shield", "Zero-Trust SSRF"])

        not_found = outline.get_section_path("non-existent-slug")
        self.assertEqual(not_found, [])


class HeadingHierarchyIntegrationTests(unittest.TestCase):
    def test_document_cleaner_integration_and_pydantic_roundtrip(self):
        html = """
        <!DOCTYPE html>
        <html>
            <head><title>Test Outline Page</title></head>
            <body>
                <h1>Main Article Title</h1>
                <p>Opening paragraph content with sufficient length for article detection.</p>
                <h2>Key Findings</h2>
                <p>Data findings.</p>
                <table><tr><th>Col1</th><th>Col2</th></tr><tr><td>A</td><td>B</td></tr></table>
                <h3>Methodology</h3>
                <p>Method details.</p>
            </body>
        </html>
        """
        page = FetchedPage(
            html=html,
            source_url="https://example.test/outline",
            status_code=200,
        )
        cleaner = DocumentCleaner(normalize_tables=True)
        doc = cleaner.clean(page)

        self.assertIsInstance(doc.outline, DocumentOutline)
        self.assertEqual(doc.outline.total_count, 3)
        self.assertEqual(doc.outline.flat_headings[0].text, "Main Article Title")
        self.assertEqual(doc.outline.flat_headings[1].text, "Key Findings")
        self.assertEqual(doc.outline.flat_headings[2].text, "Methodology")
        self.assertIn("- [Main Article Title](#main-article-title)", doc.outline.to_markdown_toc())

        # Crucial Pydantic Roundtrip Test
        serialized = doc.model_dump_json()
        deserialized = CleanDocument.model_validate_json(serialized)
        self.assertEqual(deserialized, doc)
        self.assertEqual(deserialized.outline.total_count, 3)
        self.assertEqual(len(deserialized.outline.headings[0].children), 1)


if __name__ == "__main__":
    unittest.main()
