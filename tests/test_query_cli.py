"""Tests for the ptbot query CLI subcommand (query runs / deals / export)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from ptbot.cli import main
from ptbot.db import insert_deals, insert_run, new_run_id, open_db
from ptbot.models import DealCandidate, ResearchParams

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PARAMS_A = ResearchParams(
    sector="FinTech",
    geography="United States",
    start_date="2023-01-01",
    end_date="2023-12-31",
)
_PARAMS_B = ResearchParams(
    sector="HealthTech",
    geography="Europe",
    start_date="2024-01-01",
    end_date="2024-12-31",
)
_DEAL_A = DealCandidate(
    target="Acme Payments",
    acquirer="BigBank Corp",
    date="2023-06-15",
    deal_value="$120M",
    multiples_disclosed=True,
    multiples=("5.2x EV/Revenue", "18.1x EV/EBITDA"),
    source_urls=("https://example.com/deal-a",),
)
_DEAL_B = DealCandidate(
    target="Zeta Lending",
    acquirer="Global Finance",
    date="2023-09-01",
    deal_value="$85M",
    multiples_disclosed=False,
    multiples=(),
    source_urls=(),
)
_DEAL_C = DealCandidate(
    target="MediScan AI",
    acquirer="HealthCorp",
    date="2024-03-10",
    deal_value="$200M",
    multiples_disclosed=True,
    multiples=("8.0x EV/Revenue",),
    source_urls=("https://example.com/deal-c",),
)


def _seed_db(tmp_path: Path) -> Path:
    """Create and seed a test SQLite database."""
    db_path = tmp_path / "test.db"
    conn = open_db(db_path)

    run_a = new_run_id()
    insert_run(conn, run_a, _PARAMS_A)
    insert_deals(conn, run_a, [_DEAL_A, _DEAL_B], qualified_keys={_DEAL_A.key()})

    run_b = new_run_id()
    insert_run(conn, run_b, _PARAMS_B)
    insert_deals(conn, run_b, [_DEAL_C], qualified_keys={_DEAL_C.key()})

    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# query runs
# ---------------------------------------------------------------------------


def test_query_runs_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "runs", "--db-path", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FinTech" in out
    assert "HealthTech" in out
    assert "run_id" in out  # header row


def test_query_runs_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "runs", "--db-path", str(db_path), "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert len(data) == 2
    sectors = {r["sector"] for r in data}
    assert sectors == {"FinTech", "HealthTech"}


def test_query_runs_limit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "runs", "--db-path", str(db_path), "--limit", "1", "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1  # only newest


def test_query_runs_since(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    # Both runs were inserted just now; since far future should yield nothing
    rc = main(
        ["query", "runs", "--db-path", str(db_path), "--since", "2999-01-01", "--format", "json"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data == []


def test_query_runs_no_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "nonexistent.db"
    with pytest.raises(SystemExit) as exc:
        main(["query", "runs", "--db-path", str(missing)])
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# query deals
# ---------------------------------------------------------------------------


def test_query_deals_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "deals", "--db-path", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Acme Payments" in out
    assert "target" in out  # header


def test_query_deals_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "deals", "--db-path", str(db_path), "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    targets = {d["target"] for d in data}
    assert "Acme Payments" in targets
    assert "MediScan AI" in targets


def test_query_deals_sector_filter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(
        ["query", "deals", "--db-path", str(db_path), "--sector", "FinTech", "--format", "json"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(d["sector"] == "FinTech" for d in data)
    assert len(data) == 2  # _DEAL_A and _DEAL_B


def test_query_deals_qualified_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(
        [
            "query",
            "deals",
            "--db-path",
            str(db_path),
            "--qualified-only",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(d["qualified"] for d in data)
    targets = {d["target"] for d in data}
    assert "Acme Payments" in targets
    assert "Zeta Lending" not in targets  # unqualified


def test_query_deals_no_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "deals", "--db-path", str(db_path), "--sector", "NonExistentSector"])
    assert rc == 0
    assert "no deals" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# query export
# ---------------------------------------------------------------------------


def test_query_export_csv_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "export", "--db-path", str(db_path), "--format", "csv"])
    assert rc == 0
    raw = capsys.readouterr().out
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)
    assert len(rows) == 3
    targets = {r["target"] for r in rows}
    assert "Acme Payments" in targets


def test_query_export_json_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(["query", "export", "--db-path", str(db_path), "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert len(data) == 3


def test_query_export_to_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    out_file = tmp_path / "deals.csv"
    rc = main(
        [
            "query",
            "export",
            "--db-path",
            str(db_path),
            "--output",
            str(out_file),
        ]
    )
    assert rc == 0
    assert out_file.exists()
    rows = list(csv.DictReader(out_file.open(encoding="utf-8")))
    assert len(rows) == 3
    assert "Exported 3 deals" in capsys.readouterr().out


def test_query_export_qualified_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _seed_db(tmp_path)
    rc = main(
        [
            "query",
            "export",
            "--db-path",
            str(db_path),
            "--qualified-only",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert all(r["qualified"] == "true" for r in data)
    assert len(data) == 2  # _DEAL_A + _DEAL_C


# ---------------------------------------------------------------------------
# query:runs colon-form dispatch
# ---------------------------------------------------------------------------


def test_query_colon_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """query:runs should work the same as query runs."""
    db_path = _seed_db(tmp_path)
    rc = main(["query:runs", "--db-path", str(db_path), "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2
