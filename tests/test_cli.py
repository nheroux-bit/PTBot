"""Tests for PTBot CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ptbot.cli import main


def test_config_only_outputs_valid_json(capsys) -> None:  # type: ignore[no-untyped-def]
    """--config-only should emit a serializable config and exit cleanly."""
    exit_code = main(
        [
            "--sector",
            "AI",
            "--geography",
            "Orlando, FL",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-01",
            "--config-only",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["params"]["sector"] == "AI"
    assert len(data["pass1_tasks"]) == 4


def test_config_only_accepts_industry_alias(capsys) -> None:  # type: ignore[no-untyped-def]
    """--industry should work as an alias for --sector."""
    exit_code = main(
        [
            "--industry",
            "Healthcare AI",
            "--geography",
            "US",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-01",
            "--config-only",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert exit_code == 0
    assert data["params"]["sector"] == "Healthcare AI"


def test_main_full_run_wires_output_generators(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Full CLI mode should call pipeline, PDF, and Excel generators."""
    calls: list[str] = []

    def fake_run_pipeline(params, output_dir, *, timeout, db_path=None):  # type: ignore[no-untyped-def]
        calls.append(f"pipeline:{params.sector}:{timeout}:{output_dir}")
        final = tmp_path / "final.md"
        qualified = tmp_path / "qualified.json"
        final.write_text("# Final", encoding="utf-8")
        qualified.write_text("[]", encoding="utf-8")
        return SimpleNamespace(
            final_markdown=final,
            final_pdf=tmp_path / "final.pdf",
            comps_excel=tmp_path / "comps.xlsx",
            qualified_deals=qualified,
        )

    def fake_pdf(markdown_path, pdf_path, title):  # type: ignore[no-untyped-def]
        calls.append(f"pdf:{title}")

    def fake_excel(qualified_deals, output_path, title):  # type: ignore[no-untyped-def]
        calls.append(f"excel:{title}")

    monkeypatch.setattr("ptbot.cli.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr("ptbot.cli.markdown_to_pdf", fake_pdf)
    monkeypatch.setattr("ptbot.cli.generate_comps_excel", fake_excel)

    exit_code = main(
        [
            "--sector",
            "AI",
            "--geography",
            "US",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-01",
            "--output-dir",
            str(tmp_path),
            "--timeout",
            "1",
        ]
    )

    assert exit_code == 0
    assert calls == [
        f"pipeline:AI:1:{tmp_path}",
        "pdf:AI Precedent Transactions",
        "excel:AI Comps",
    ]
