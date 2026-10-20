"""Unit & integration tests for Subsystem 9: Advanced Table Markdown Normalizer."""

import re
import unittest
from bs4 import BeautifulSoup

from smart_miner.pipeline.tables import TableNormalizer, TableData, clean_cell_text
from smart_miner.pipeline.document import CleanDocument, DocumentCleaner
from smart_miner.crawler.fetcher import FetchedPage


class TableNormalizerUnitTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TableNormalizer()

    def test_clean_cell_text_escapes_pipes_and_collapses_whitespace(self):
        soup = BeautifulSoup('<td> Price: $100 | Tier: A <br> Note: Active </td>', 'html.parser')
        cell = soup.find('td')
        cleaned = clean_cell_text(cell)
        self.assertEqual(cleaned, 'Price: $100 \\| Tier: A Note: Active')

    def test_simple_table_to_gfm_markdown(self):
        html = """
        <table>
            <thead>
                <tr><th>Product</th><th>Price</th><th>Stock</th></tr>
            </thead>
            <tbody>
                <tr><td>Laptop</td><td>$1,200</td><td>15</td></tr>
                <tr><td>Phone</td><td>$800</td><td>42</td></tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertEqual(data.headers, ["Product", "Price", "Stock"])
        self.assertEqual(len(data.rows), 2)
        self.assertEqual(data.rows[0], ["Laptop", "$1,200", "15"])
        self.assertEqual(data.rows[1], ["Phone", "$800", "42"])
        self.assertFalse(data.has_merged_cells)

        # Check GFM Markdown formatting
        self.assertIn("| Product | Price | Stock |", data.markdown)
        self.assertIn("| :--- | :--- | :--- |", data.markdown)
        self.assertIn("| Laptop | $1,200 | 15 |", data.markdown)

    def test_colspan_expansion(self):
        html = """
        <table>
            <tr><th colspan="2">System Specs</th><th>Status</th></tr>
            <tr><td>CPU</td><td>RAM</td><td>Online</td></tr>
            <tr><td>8 Cores</td><td>32 GB</td><td>Active</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertTrue(data.has_merged_cells)
        self.assertEqual(data.col_count, 3)
        self.assertEqual(data.headers, ["System Specs", "", "Status"])
        self.assertEqual(data.rows[0], ["CPU", "RAM", "Online"])
        self.assertEqual(data.rows[1], ["8 Cores", "32 GB", "Active"])

    def test_rowspan_expansion(self):
        html = """
        <table>
            <tr><th>Department</th><th>Employee</th><th>Role</th></tr>
            <tr><td rowspan="2">Engineering</td><td>Alice</td><td>Lead</td></tr>
            <tr><td>Bob</td><td>Dev</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertTrue(data.has_merged_cells)
        self.assertEqual(data.row_count, 2)
        # Row 0 has "Engineering"
        self.assertEqual(data.rows[0][0], "Engineering")
        self.assertEqual(data.rows[0][1], "Alice")
        # Row 1 inherits occupied rowspan from Row 0
        self.assertEqual(data.rows[1][0], "")
        self.assertEqual(data.rows[1][1], "Bob")
        self.assertEqual(data.rows[1][2], "Dev")

    def test_combined_colspan_and_rowspan_complex_matrix(self):
        html = """
        <table>
            <tr><th colspan="2" rowspan="2">Group Metrics</th><th>Q1</th><th>Q2</th></tr>
            <tr><th>$10M</th><th>$15M</th></tr>
            <tr><td>Region A</td><td>Tier 1</td><td>$4M</td><td>$6M</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertTrue(data.has_merged_cells)
        self.assertEqual(data.col_count, 4)
        self.assertEqual(len(data.rows), 2)
        self.assertEqual(data.rows[1], ["Region A", "Tier 1", "$4M", "$6M"])

    def test_pipe_character_escaping(self):
        html = """
        <table>
            <tr><th>Command</th><th>Syntax | Flags</th></tr>
            <tr><td>grep</td><td>grep -i | -v</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertIn("Syntax \\| Flags", data.markdown)
        self.assertIn("grep -i \\| -v", data.markdown)
        # Verify lines have exactly 2 columns, not 3
        for line in data.markdown.strip().split("\n"):
            # Count unescaped pipe separators
            unescaped_pipes = [m.start() for m in re.finditer(r"(?<!\\)\|", line)]
            self.assertEqual(len(unescaped_pipes), 3)  # Left, middle, right

    def test_to_records_dictionary_conversion(self):
        html = """
        <table>
            <tr><th>Node ID</th><th>IP Address</th><th>Uptime</th></tr>
            <tr><td>node-1</td><td>10.0.0.1</td><td>99.9%</td></tr>
            <tr><td>node-2</td><td>10.0.0.2</td><td>98.5%</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)
        records = data.to_records()

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], {"Node ID": "node-1", "IP Address": "10.0.0.1", "Uptime": "99.9%"})
        self.assertEqual(records[1], {"Node ID": "node-2", "IP Address": "10.0.0.2", "Uptime": "98.5%"})

    def test_table_with_caption(self):
        html = """
        <table>
            <caption>Cluster Resource Allocation</caption>
            <tr><th>Server</th><th>Cores</th></tr>
            <tr><td>Worker-1</td><td>64</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        data = self.normalizer.parse_table(table)

        self.assertEqual(data.caption, "Cluster Resource Allocation")
        self.assertIn("**Table: Cluster Resource Allocation**", data.markdown)


class DocumentCleanerTableIntegrationTests(unittest.TestCase):
    def test_document_cleaner_populates_structured_tables(self):
        html = """
        <html><body>
            <h1>Infrastructure Status</h1>
            <table>
                <tr><th>Region</th><th>Latency</th></tr>
                <tr><td>us-east</td><td>20ms</td></tr>
            </table>
        </body></html>
        """
        page = FetchedPage(html, "https://example.com/status", 200)
        doc = DocumentCleaner().clean(page)

        self.assertEqual(len(doc.tables), 1)
        table_obj = doc.tables[0]
        self.assertEqual(table_obj.headers, ["Region", "Latency"])
        self.assertEqual(table_obj.rows, [["us-east", "20ms"]])

    def test_document_cleaner_with_normalize_tables_true_produces_gfm(self):
        html = """
        <html><body>
            <h1>Merged Table Report</h1>
            <table>
                <tr><th colspan="2">Merged Header</th></tr>
                <tr><td>Cell A</td><td>Cell B</td></tr>
            </table>
        </body></html>
        """
        page = FetchedPage(html, "https://example.com/merged", 200)
        # Using normalize_tables=True converts merged table into clean GFM Markdown
        doc = DocumentCleaner(normalize_tables=True).clean(page)

        self.assertIn("| Merged Header |", doc.markdown)
        self.assertIn("| Cell A | Cell B |", doc.markdown)
        self.assertNotIn("<table", doc.markdown)
        self.assertNotIn("<th", doc.markdown)
