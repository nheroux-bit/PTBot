"""Tests for sector presets, ptbot sweep:auto --preset, and ptbot db:coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ptbot.cli import main
from ptbot.db import insert_deals, insert_run, new_run_id, open_db
from ptbot.models import DealCandidate, ResearchParams
from ptbot.presets import list_presets, load_preset, load_preset_metadata

# ---------------------------------------------------------------------------
# Preset loader
# ---------------------------------------------------------------------------


def test_load_preset_startup_tech_returns_sectors() -> None:
    sectors = load_preset("startup-tech")
    assert isinstance(sectors, list)
    assert len(sectors) >= 30  # at least 30 verticals
    assert "FinTech" in sectors
    assert "Cybersecurity" in sectors
    assert "AI / Machine Learning" in sectors
    assert "CleanTech" in sectors


def test_load_preset_returns_only_names_not_aliases() -> None:
    sectors = load_preset("startup-tech")
    # All entries should be plain strings — no dicts/aliases leaked through
    assert all(isinstance(s, str) for s in sectors)


def test_list_presets_includes_startup_tech() -> None:
    presets = list_presets()
    assert "startup-tech" in presets


def test_load_preset_unknown_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_preset("nonexistent-preset-xyz")


def test_load_preset_metadata_returns_description() -> None:
    meta = load_preset_metadata("startup-tech")
    assert meta["name"] == "startup-tech"
    assert "description" in meta
    assert "sectors" in meta
    assert len(meta["sectors"]) >= 30


# ---------------------------------------------------------------------------
# sweep:auto --preset
# ---------------------------------------------------------------------------


def test_sweep_auto_preset_dispatched(capsys: pytest.CaptureFixture[str]) -> None:
    """--preset startup-tech should load 38 sectors and forward to run_sweep."""
    captured_config = []

    def fake_run_sweep(config, **kwargs):
        captured_config.append(config)
        return 0

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", fake_run_sweep):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--preset",
                "startup-tech",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert len(captured_config) == 1
    assert len(captured_config[0].markets) >= 30
    # Geography applied uniformly
    assert all(m.geography == "United States" for m in captured_config[0].markets)
    # Log line mentions preset
    out = capsys.readouterr().out
    assert "startup-tech" in out


def test_sweep_auto_preset_and_sectors_mutually_exclusive() -> None:
    """--preset and --sectors together should fail argparse."""
    import ptbot.cli as _cli

    with pytest.raises(SystemExit) as exc:
        _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--preset",
                "startup-tech",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
            ]
        )
    assert exc.value.code != 0


def test_sweep_auto_unknown_preset_returns_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ptbot.cli as _cli

    rc = _cli._handle_sweep_auto_command(
        [
            "sweep:auto",
            "--preset",
            "no-such-preset",
            "--geography",
            "United States",
        ]
    )
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_sweep_auto_preset_dispatched_from_main(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("ptbot.cli._handle_sweep_auto_command", return_value=0) as mock_fn:
        rc = main(
            [
                "sweep:auto",
                "--preset",
                "startup-tech",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )
    assert rc == 0
    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# db:coverage
# ---------------------------------------------------------------------------


def _seed_coverage_db(tmp_path: Path) -> Path:
    """Seed a DB with a couple of runs across two sectors."""
    db_path = tmp_path / "coverage-test.db"
    conn = open_db(db_path)

    for sector, year in [("FinTech", "2023"), ("Cybersecurity", "2022")]:
        run_id = new_run_id()
        params = ResearchParams(
            sector=sector,
            geography="United States",
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
        )
        insert_run(conn, run_id, params)
        deal = DealCandidate(
            target="TestCo",
            acquirer="Buyer",
            date=f"{year}-06-01",
            deal_value="$100M",
            multiples_disclosed=True,
            multiples=("5.0x EV/Revenue",),
            source_urls=("https://example.com",),
        )
        insert_deals(conn, run_id, [deal], qualified_keys={deal.key()})

    conn.close()
    return db_path


def test_db_coverage_no_db_exits_gracefully(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nonexistent.db"
    rc = main(["db:coverage", "--db-path", str(missing)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "not found" in out.lower()


def test_db_coverage_shows_covered_sectors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _seed_coverage_db(tmp_path)
    rc = main(["db:coverage", "--db-path", str(db_path), "--years", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FinTech" in out
    assert "Cybersecurity" in out
    assert "covered" in out.lower()


def test_db_coverage_with_preset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_coverage_db(tmp_path)
    rc = main(
        [
            "db:coverage",
            "--db-path",
            str(db_path),
            "--preset",
            "startup-tech",
            "--years",
            "3",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # Should show all startup-tech sectors, including covered ones
    assert "FinTech" in out
    assert "Total:" in out
    assert "%" in out


def test_db_coverage_shows_percentage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_coverage_db(tmp_path)
    rc = main(
        [
            "db:coverage",
            "--db-path",
            str(db_path),
            "--preset",
            "startup-tech",
            "--years",
            "3",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "%" in out
    # Should suggest a sweep command for missing gaps
    assert "sweep:auto" in out
