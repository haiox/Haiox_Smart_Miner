"""Advanced Table & Tabular Data Markdown Normalizer.

Parses complex HTML tables, resolves colspan and rowspan cell mergers, escapes
markdown table pipe delimiters, cleans intra-cell whitespace/linebreaks, and
generates clean, structured GitHub Flavored Markdown (GFM) tables as well as
machine-readable dictionary records.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


def clean_cell_text(cell: Tag) -> str:
    """Extracts, strips, and formats text inside a table cell for GFM compatibility."""
    # Convert <br> to space or line continuation
    for br in cell.find_all("br"):
        br.replace_with(" ")

    text = cell.get_text(" ", strip=True)
    # Collapse multiple whitespace / newlines into a single space
    text = re.sub(r"\s+", " ", text).strip()
    # Escape pipe characters so they do not break Markdown table columns
    text = text.replace("|", "\\|")
    return text


class TableData(BaseModel):
    """Structured representation of a parsed table."""
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: str = ""
    html: str = ""
    row_count: int = 0
    col_count: int = 0
    has_merged_cells: bool = False
    caption: str = ""

    def to_records(self) -> List[Dict[str, str]]:
        """Converts table rows into a list of dictionaries mapped by header names."""
        if not self.headers:
            return []
        
        records = []
        for row in self.rows:
            record: Dict[str, str] = {}
            for col_idx, header in enumerate(self.headers):
                val = row[col_idx] if col_idx < len(row) else ""
                key = header if header else f"col_{col_idx + 1}"
                # Handle duplicate header keys gracefully
                if key in record:
                    key = f"{key}_{col_idx + 1}"
                record[key] = val
            records.append(record)
        return records


class TableNormalizer:
    """Parses and normalizes HTML tables with full colspan & rowspan expansion."""

    def __init__(self, *, fill_merged_empty: bool = True) -> None:
        self.fill_merged_empty = fill_merged_empty

    def parse_table(self, table: Tag) -> TableData:
        """Parses an HTML <table> Tag into a structured TableData instance."""
        if not isinstance(table, Tag) or table.name != "table":
            return TableData()

        raw_html = str(table)
        caption_elem = table.find("caption")
        caption = caption_elem.get_text(strip=True) if caption_elem else ""

        # Identify all <tr> rows (ignoring nested tables)
        tr_elements = [
            tr for tr in table.find_all("tr")
            if tr.find_parent("table") == table
        ]

        if not tr_elements:
            return TableData(html=raw_html, caption=caption)

        # 2D Grid representation: grid[row][col] -> cell_text
        grid: Dict[int, Dict[int, str]] = {}
        occupied_slots: Dict[Tuple[int, int], str] = {}
        has_merged = False

        max_cols = 0
        total_rows = len(tr_elements)

        for row_idx, tr in enumerate(tr_elements):
            if row_idx not in grid:
                grid[row_idx] = {}

            col_idx = 0
            cells = [
                c for c in tr.find_all(["th", "td"], recursive=False)
            ]

            for cell in cells:
                # Advance col_idx past any slots occupied by active rowspans from prior rows
                while (row_idx, col_idx) in occupied_slots:
                    grid[row_idx][col_idx] = occupied_slots[(row_idx, col_idx)]
                    col_idx += 1

                # Parse colspan & rowspan
                try:
                    colspan = int(cell.get("colspan", 1))
                except (ValueError, TypeError):
                    colspan = 1

                try:
                    rowspan = int(cell.get("rowspan", 1))
                except (ValueError, TypeError):
                    rowspan = 1

                colspan = max(1, colspan)
                rowspan = max(1, rowspan)

                if colspan > 1 or rowspan > 1:
                    has_merged = True

                text = clean_cell_text(cell)
                grid[row_idx][col_idx] = text

                # Expand colspan within current row
                for c in range(1, colspan):
                    continuation_text = "" if self.fill_merged_empty else text
                    grid[row_idx][col_idx + c] = continuation_text

                # Reserve future row slots for rowspan
                for r in range(1, rowspan):
                    target_row = row_idx + r
                    for c in range(colspan):
                        target_col = col_idx + c
                        val = "" if self.fill_merged_empty else text
                        occupied_slots[(target_row, target_col)] = val

                col_idx += colspan
                max_cols = max(max_cols, col_idx)

            # Fill any remaining occupied slots at end of row
            while (row_idx, col_idx) in occupied_slots:
                grid[row_idx][col_idx] = occupied_slots[(row_idx, col_idx)]
                col_idx += 1
                max_cols = max(max_cols, col_idx)

        # Convert grid into normalized rectangular 2D matrix
        matrix: List[List[str]] = []
        for r in range(total_rows):
            row_cells: List[str] = []
            for c in range(max_cols):
                row_cells.append(grid.get(r, {}).get(c, ""))
            matrix.append(row_cells)

        if not matrix or max_cols == 0:
            return TableData(html=raw_html, caption=caption)

        # Separate headers and data rows
        # Check if first row contains <th> tags or is inside <thead>
        first_tr = tr_elements[0]
        is_first_header = bool(first_tr.find("th") or first_tr.find_parent("thead"))

        if is_first_header and len(matrix) >= 1:
            headers = matrix[0]
            data_rows = matrix[1:]
        else:
            # Synthetic generic headers
            headers = [f"Col {c + 1}" for c in range(max_cols)]
            data_rows = matrix

        # Generate GFM Markdown
        markdown = self._generate_gfm(headers, data_rows, caption)

        return TableData(
            headers=headers,
            rows=data_rows,
            markdown=markdown,
            html=raw_html,
            row_count=len(data_rows),
            col_count=max_cols,
            has_merged_cells=has_merged,
            caption=caption,
        )

    def _generate_gfm(
        self,
        headers: List[str],
        rows: List[List[str]],
        caption: str = "",
    ) -> str:
        """Constructs compliant GitHub Flavored Markdown table string."""
        if not headers:
            return ""

        lines: List[str] = []
        if caption:
            lines.append(f"**Table: {caption}**\n")

        # Header row
        header_line = "| " + " | ".join(h if h else " " for h in headers) + " |"
        lines.append(header_line)

        # Separator row with left alignment
        separator_line = "| " + " | ".join(":---" for _ in headers) + " |"
        lines.append(separator_line)

        # Data rows
        for row in rows:
            padded_row = list(row)
            while len(padded_row) < len(headers):
                padded_row.append("")
            row_line = "| " + " | ".join(c if c else " " for c in padded_row[:len(headers)]) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    def extract_all_tables(self, soup: BeautifulSoup) -> List[TableData]:
        """Extracts and parses all top-level tables in a BeautifulSoup DOM."""
        parsed_tables: List[TableData] = []
        for table in soup.find_all("table"):
            # Skip nested tables; parent table handles cells
            if table.find_parent("table"):
                continue
            parsed = self.parse_table(table)
            if parsed.col_count > 0:
                parsed_tables.append(parsed)
        return parsed_tables

    def replace_tables_with_markdown(
        self,
        soup: BeautifulSoup,
        *,
        preserve_merged_html: bool = False,
    ) -> List[Tuple[str, str]]:
        """Replaces <table> elements in soup with GFM Markdown or markers.
        
        Returns a list of (marker, markdown_or_html) tuples.
        """
        replacements: List[Tuple[str, str]] = []
        table_nodes = [t for t in soup.find_all("table") if not t.find_parent("table")]

        for idx, table in enumerate(table_nodes):
            parsed = self.parse_table(table)
            marker = f"__SMARTMINER_TABLE_{idx}__"

            if preserve_merged_html and parsed.has_merged_cells:
                # Legacy behavior: keep clean HTML for complex merged cells
                cleaned_html = str(table)
                replacements.append((marker, cleaned_html))
            else:
                # Modern GFM Markdown
                replacements.append((marker, parsed.markdown))

            table.replace_with(marker)

        return replacements
