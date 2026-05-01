"""PDF generation for PTBot deliverables."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF


def sanitize_text(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica core fonts."""
    replacements = {
        "\u2014": "--",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2192": "->",
        "\u2264": "<=",
        "\u2265": ">=",
        "\u00d7": "x",
        "\u2248": "~",
        "\u26a0\ufe0f": "[!]",
        "\u26a0": "[!]",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def strip_markdown(text: str) -> str:
    """Strip lightweight markdown syntax for PDF rendering."""
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return sanitize_text(text)


class ReportPDF(FPDF):
    """Simple branded PDF for precedent transaction reports."""

    def __init__(self, title: str) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.report_title = title

    def header(self) -> None:
        """Render page header."""
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, sanitize_text(self.report_title), align="L")
        self.cell(0, 5, "PTBot", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        """Render page footer."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def markdown_to_pdf(markdown_path: Path, pdf_path: Path, title: str) -> None:
    """Render a markdown report to PDF."""
    pdf = ReportPDF(title)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            pdf.ln(2)
            continue
        if line == "---":
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(4)
            continue
        if line.startswith("# "):
            if pdf.get_y() > 30:
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(26, 26, 26)
            pdf.multi_cell(0, 8, strip_markdown(line[2:]))
            pdf.ln(3)
            continue
        if line.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(44, 62, 80)
            pdf.multi_cell(0, 7, strip_markdown(line[3:]))
            pdf.ln(2)
            continue
        if line.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(52, 73, 94)
            pdf.multi_cell(0, 6, strip_markdown(line[4:]))
            continue
        if line.startswith("- "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(26, 26, 26)
            pdf.set_x(pdf.l_margin + 6)
            pdf.cell(4, 5, "*")
            pdf.multi_cell(0, 5, strip_markdown(line[2:]))
            continue
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(26, 26, 26)
        pdf.multi_cell(0, 5, strip_markdown(line))
        pdf.ln(1)

    pdf.output(pdf_path)
