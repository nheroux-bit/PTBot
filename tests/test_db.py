"""Tests for the SQLite deal store (ptbot.db)."""

from __future__ import annotations

import json
from pathlib import Path

from ptbot.db import (
    insert_deals,
    insert_run,
    new_run_id,
    open_db,
    query_deal_quality,
    query_deals,
    query_runs,
    update_deal_quality_signals,
)
from ptbot.models import DealCandidate, ResearchParams

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PARAMS = ResearchParams(
    sector="HealthTech",
    geography="Boston, MA",
    start_date="2024-01-01",
    end_date="2024-12-31",
)

_DEAL_A = DealCandidate(
    target="Acme Health",
    acquirer="BigMed Corp",
    date="2024-06-15",
    deal_value="$50M",
    multiples_disclosed=True,
    multiples=("5.0x EV/Revenue",),
    source_urls=("https://example.com/deal-a",),
)

_DEAL_B = DealCandidate(
    target="Zeta Diagnostics",
    acquirer="GlobalLab Inc",
    date="2024-09-01",
    deal_value="$120M",
    multiples_disclosed=True,
    computed_multiples_available=True,
    multiples=("8.2x EV/Revenue", "22.1x EV/EBITDA"),
    source_urls=("https://example.com/deal-b",),
)

_DEAL_C = DealCandidate(
    target="Plain Target",
    acquirer="Plain Acquirer",
)


# ---------------------------------------------------------------------------
# open_db
# ---------------------------------------------------------------------------


def test_open_db_creates_file(tmp_path: Path) -> None:
    """open_db should create the database file."""
    db_file = tmp_path / "test.db"
    conn = open_db(db_file)
    conn.close()
    assert db_file.exists()


def test_open_db_creates_parent_dirs(tmp_path: Path) -> None:
    """open_db should create missing parent directories."""
    db_file = tmp_path / "nested" / "dir" / "ptbot.db"
    conn = open_db(db_file)
    conn.close()
    assert db_file.exists()


def test_open_db_is_idempotent(tmp_path: Path) -> None:
    """Calling open_db twice on the same file should not raise."""
    db_file = tmp_path / "test.db"
    conn1 = open_db(db_file)
    conn1.close()
    conn2 = open_db(db_file)
    conn2.close()


def test_open_db_schema_has_runs_table(tmp_path: Path) -> None:
    """The 'runs' table should exist after open_db."""
    conn = open_db(tmp_path / "test.db")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    assert cursor.fetchone() is not None
    conn.close()


def test_open_db_schema_has_deals_table(tmp_path: Path) -> None:
    """The 'deals' table should exist after open_db."""
    conn = open_db(tmp_path / "test.db")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deals'")
    assert cursor.fetchone() is not None
    conn.close()


# ---------------------------------------------------------------------------
# new_run_id
# ---------------------------------------------------------------------------


def test_new_run_id_returns_string() -> None:
    """new_run_id should return a non-empty string."""
    assert isinstance(new_run_id(), str)
    assert len(new_run_id()) > 0


def test_new_run_id_is_unique() -> None:
    """Consecutive calls should return different IDs."""
    assert new_run_id() != new_run_id()


# ---------------------------------------------------------------------------
# insert_run / query_runs
# ---------------------------------------------------------------------------


def test_insert_run_roundtrip(tmp_path: Path) -> None:
    """An inserted run should appear in query_runs with correct params."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)

    rows = query_runs(conn)
    conn.close()

    assert len(rows) == 1
    assert rows[0]["run_id"] == run_id
    stored_params = json.loads(rows[0]["params"])
    assert stored_params["sector"] == "HealthTech"
    assert stored_params["geography"] == "Boston, MA"


def test_query_runs_ordered_newest_first(tmp_path: Path) -> None:
    """query_runs should return runs ordered by timestamp descending."""
    conn = open_db(tmp_path / "test.db")
    run_id_1 = new_run_id()
    run_id_2 = new_run_id()
    insert_run(conn, run_id_1, _PARAMS)
    insert_run(conn, run_id_2, _PARAMS)

    rows = query_runs(conn)
    conn.close()

    assert len(rows) == 2
    # Most recent insertion is run_id_2; timestamps are UTC ISO strings so
    # lexicographic order matches temporal order.
    assert rows[0]["run_id"] == run_id_2


# ---------------------------------------------------------------------------
# insert_deals / query_deals
# ---------------------------------------------------------------------------


def test_insert_deals_marks_qualified(tmp_path: Path) -> None:
    """Deals whose key is in qualified_keys should be stored with qualified=1."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)

    insert_deals(
        conn,
        run_id,
        [_DEAL_A, _DEAL_B],
        qualified_keys={_DEAL_A.key()},
    )

    rows = {r["target"]: r for r in query_deals(conn, run_id)}
    conn.close()

    assert rows["Acme Health"]["qualified"] == 1
    assert rows["Zeta Diagnostics"]["qualified"] == 0


def test_insert_deals_stores_multiples_as_json(tmp_path: Path) -> None:
    """Multiples should be persisted as a JSON array string."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)
    insert_deals(conn, run_id, [_DEAL_B], qualified_keys={_DEAL_B.key()})

    rows = query_deals(conn, run_id)
    conn.close()

    stored = json.loads(rows[0]["multiples"])
    assert "8.2x EV/Revenue" in stored
    assert "22.1x EV/EBITDA" in stored


def test_insert_deals_stores_source_urls(tmp_path: Path) -> None:
    """Source URLs should be persisted as a JSON array string."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)
    insert_deals(conn, run_id, [_DEAL_A], qualified_keys=set())

    rows = query_deals(conn, run_id)
    conn.close()

    stored = json.loads(rows[0]["source_urls"])
    assert "https://example.com/deal-a" in stored


def test_insert_deals_handles_none_fields(tmp_path: Path) -> None:
    """Deals with no date/deal_value/multiples should not raise."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)
    insert_deals(conn, run_id, [_DEAL_C], qualified_keys=set())

    rows = query_deals(conn, run_id)
    conn.close()

    assert len(rows) == 1
    assert rows[0]["date"] is None
    assert rows[0]["deal_value"] is None


def test_insert_deals_empty_list_is_noop(tmp_path: Path) -> None:
    """Inserting an empty candidate list should not write any rows."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)
    insert_deals(conn, run_id, [], qualified_keys=set())

    assert query_deals(conn, run_id) == []
    conn.close()


def test_query_deals_filters_by_run_id(tmp_path: Path) -> None:
    """query_deals should only return rows belonging to the requested run."""
    conn = open_db(tmp_path / "test.db")
    run_id_1 = new_run_id()
    run_id_2 = new_run_id()
    insert_run(conn, run_id_1, _PARAMS)
    insert_run(conn, run_id_2, _PARAMS)
    insert_deals(conn, run_id_1, [_DEAL_A], qualified_keys=set())
    insert_deals(conn, run_id_2, [_DEAL_B], qualified_keys=set())

    rows_1 = query_deals(conn, run_id_1)
    rows_2 = query_deals(conn, run_id_2)
    conn.close()

    assert len(rows_1) == 1
    assert rows_1[0]["target"] == "Acme Health"
    assert len(rows_2) == 1
    assert rows_2[0]["target"] == "Zeta Diagnostics"


# ---------------------------------------------------------------------------
# query_run_exists
# ---------------------------------------------------------------------------


def test_query_run_exists_returns_true_when_match(tmp_path: Path) -> None:
    """query_run_exists should return True when a matching run is present."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)

    from ptbot.db import query_run_exists

    result = query_run_exists(conn, "HealthTech", "Boston, MA", "2024-01-01", "2024-12-31")
    conn.close()

    assert result is True


def test_query_run_exists_returns_false_when_empty_db(tmp_path: Path) -> None:
    """query_run_exists should return False when the database has no runs."""
    conn = open_db(tmp_path / "test.db")

    from ptbot.db import query_run_exists

    result = query_run_exists(conn, "HealthTech", "Boston, MA", "2024-01-01", "2024-12-31")
    conn.close()

    assert result is False


def test_query_run_exists_returns_false_for_different_params(tmp_path: Path) -> None:
    """query_run_exists should not match when any param differs."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)  # HealthTech / Boston, MA / 2024-01-01 / 2024-12-31

    from ptbot.db import query_run_exists

    # Different sector
    assert query_run_exists(conn, "FinTech", "Boston, MA", "2024-01-01", "2024-12-31") is False
    # Different geography
    assert query_run_exists(conn, "HealthTech", "New York", "2024-01-01", "2024-12-31") is False
    # Different year
    assert query_run_exists(conn, "HealthTech", "Boston, MA", "2023-01-01", "2023-12-31") is False
    conn.close()


def test_multiple_runs_do_not_bleed(tmp_path: Path) -> None:
    """Data from one run should not appear in another run's results."""
    conn = open_db(tmp_path / "test.db")
    run_id_1 = new_run_id()
    run_id_2 = new_run_id()
    insert_run(conn, run_id_1, _PARAMS)
    insert_run(conn, run_id_2, _PARAMS)
    insert_deals(conn, run_id_1, [_DEAL_A, _DEAL_B], qualified_keys={_DEAL_A.key()})
    insert_deals(conn, run_id_2, [_DEAL_C], qualified_keys=set())

    assert len(query_deals(conn, run_id_1)) == 2
    assert len(query_deals(conn, run_id_2)) == 1
    assert len(query_runs(conn)) == 2
    conn.close()


# --- quality-signals-001 persistence tests ---


def test_deals_table_has_quality_columns(tmp_path: Path) -> None:
    """New columns from quality-signals-001 must exist (additive migration)."""
    conn = open_db(tmp_path / "test.db")
    cursor = conn.execute("PRAGMA table_info(deals)")
    cols = {row[1] for row in cursor.fetchall()}
    assert "quality_signals" in cols
    assert "dedup_key" in cols
    conn.close()


def test_insert_and_update_quality_signals(tmp_path: Path) -> None:
    """Insert deals, then update quality via key, then query it back."""
    conn = open_db(tmp_path / "test.db")
    run_id = new_run_id()
    insert_run(conn, run_id, _PARAMS)
    insert_deals(conn, run_id, [_DEAL_A], qualified_keys={_DEAL_A.key()})

    qjson = json.dumps({"overall_confidence": "HIGH", "confidence_score": 0.92})
    n = update_deal_quality_signals(conn, run_id, {_DEAL_A.key(): qjson})
    assert n == 1

    deals = query_deals(conn, run_id)
    assert deals[0]["quality_signals"] == qjson
    assert deals[0]["dedup_key"] == _DEAL_A.key()

    q = query_deal_quality(conn, deals[0]["deal_id"])
    assert q["overall_confidence"] == "HIGH"
    conn.close()
