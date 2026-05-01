"""Tests for PDF and Excel output helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ptbot.excel import generate_comps_excel
from ptbot.pdf import markdown_to_pdf, sanitize_text, strip_markdown


def test_sanitize_text_replaces_common_unicode() -> None:
    """PDF sanitization should replace characters unsupported by core fonts."""
    assert sanitize_text("A — B ≥ C") == "A -- B >= C"


def test_strip_markdown_removes_links_and_bold() -> None:
    """Markdown syntax should be simplified for PDF text."""
    assert strip_markdown("**Deal** [source](https://example.com)") == "Deal source"


def test_markdown_to_pdf_writes_file(tmp_path: Path) -> None:
    """Markdown reports should render to a non-empty PDF."""
    markdown = tmp_path / "report.md"
    pdf = tmp_path / "report.pdf"
    markdown.write_text("# Report\n\n## Summary\n\n- One item", encoding="utf-8")

    markdown_to_pdf(markdown, pdf, "Report")

    assert pdf.exists()
    assert pdf.stat().st_size > 0


def test_generate_comps_excel_writes_expected_sheets(tmp_path: Path) -> None:
    """Excel generator should create the expected workbook tabs."""
    deals = tmp_path / "qualified_deals.json"
    workbook_path = tmp_path / "comps.xlsx"
    deals.write_text(
        json.dumps(
            [
                {
                    "target": "Dexibit",
                    "acquirer": "accesso",
                    "date": "2026-03-30",
                    "deal_value": "$12.1M",
                    "multiples_disclosed": True,
                    "computed_multiples_available": True,
                    "multiples": ["5.1x EV/ARR"],
                    "source_urls": ["https://example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )

    generate_comps_excel(deals, workbook_path, "AI Comps")

    workbook = load_workbook(workbook_path)
    assert workbook.sheetnames == ["Cover", "Comps Table", "Benchmarks", "Sources"]
    assert workbook["Comps Table"]["A2"].value == "Dexibit"


def test_generate_comps_excel_rejects_non_list_json(tmp_path: Path) -> None:
    """Qualified deals JSON must be a list."""
    deals = tmp_path / "qualified_deals.json"
    deals.write_text(json.dumps({"target": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        generate_comps_excel(deals, tmp_path / "comps.xlsx", "Bad")
