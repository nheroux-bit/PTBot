"""SQLite persistence layer for PTBot deal candidates and pipeline runs."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import CostBreakdown, DealCandidate, ResearchParams

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id    TEXT PRIMARY KEY,
    params    TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    deal_id                      TEXT PRIMARY KEY,
    run_id                       TEXT NOT NULL REFERENCES runs(run_id),
    target                       TEXT NOT NULL,
    acquirer                     TEXT NOT NULL,
    date                         TEXT,
    deal_value                   TEXT,
    multiples_disclosed          INTEGER NOT NULL DEFAULT 0,
    computed_multiples_available INTEGER NOT NULL DEFAULT 0,
    multiples                    TEXT NOT NULL DEFAULT '[]',
    source_urls                  TEXT NOT NULL DEFAULT '[]',
    qualified                    INTEGER NOT NULL DEFAULT 0,
    quality_signals              TEXT,          -- JSON DealQualitySignals (quality-signals-001)
    dedup_key                    TEXT           -- normalized key for reliable matching/updates
);
"""


def _ensure_cost_columns(conn: sqlite3.Connection) -> None:
    """Idempotent migration: add cost columns to 'runs' for DBs pre-dating cost-accounting-001.

    Safe on every open_db. PRAGMA + ALTER ADD COLUMN with defaults.
    Other swarm agents continue to work unchanged.
    """
    cur = conn.execute("PRAGMA table_info(runs)")
    existing = {row[1] for row in cur.fetchall()}
    if "input_tokens" not in existing:
        conn.execute("ALTER TABLE runs ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0")
    if "output_tokens" not in existing:
        conn.execute("ALTER TABLE runs ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0")
    if "estimated_cost_usd" not in existing:
        conn.execute("ALTER TABLE runs ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0.0")
    if "cost_model" not in existing:
        conn.execute("ALTER TABLE runs ADD COLUMN cost_model TEXT DEFAULT 'oz-default'")
    conn.commit()


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and apply the schema.

    Creates all parent directories as needed. Enables WAL journal mode
    and foreign-key enforcement on every connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")  # wait up to 10 s on writer contention
    conn.executescript(_SCHEMA)
    # Additive migrations for quality-signals-001 (idempotent)
    for col, type_decl in [
        ("quality_signals", "TEXT"),
        ("dedup_key", "TEXT"),
    ]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {type_decl}")
    conn.commit()
    _ensure_cost_columns(conn)  # cost-accounting-001: idempotent ALTERs for pre-existing DBs
    return conn


def new_run_id() -> str:
    """Return a new unique run identifier (UUID4)."""
    return str(uuid.uuid4())


def insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    params: ResearchParams,
    cost: CostBreakdown | None = None,
) -> None:
    """Insert a pipeline run record.

    Cost columns (vBRIEF ca-2) are populated when *cost* is provided; otherwise zeros.
    Signature change is backward-compatible (new param has default).
    """
    in_tok = cost.usage.input_tokens if cost else 0
    out_tok = cost.usage.output_tokens if cost else 0
    usd = cost.estimated_cost_usd if cost else 0.0
    model = cost.model if cost else "oz-default"
    conn.execute(
        """
        INSERT INTO runs (
            run_id, params, timestamp,
            input_tokens, output_tokens, estimated_cost_usd, cost_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            json.dumps(params.model_dump(mode="json")),
            datetime.now(UTC).isoformat(),
            in_tok,
            out_tok,
            usd,
            model,
        ),
    )
    conn.commit()


def insert_deals(
    conn: sqlite3.Connection,
    run_id: str,
    candidates: list[DealCandidate],
    *,
    qualified_keys: set[str],
    quality_by_key: dict[str, str] | None = None,
) -> None:
    """Insert deal candidates for a run.

    Each deal is marked as qualified if its normalised key appears in
    *qualified_keys*.  Bulk-inserted with a single ``executemany`` call.
    quality_by_key: optional {dedup_key: json-string-of-DealQualitySignals} populated
    post-QC (see orchestrator after structured extraction).
    """
    if not candidates:
        return
    quality_by_key = quality_by_key or {}
    rows = [
        (
            str(uuid.uuid4()),
            run_id,
            deal.target,
            deal.acquirer,
            deal.date,
            deal.deal_value,
            int(deal.multiples_disclosed),
            int(deal.computed_multiples_available),
            json.dumps(list(deal.multiples)),
            json.dumps(list(deal.source_urls)),
            int(deal.key() in qualified_keys),
            quality_by_key.get(deal.key()),  # may be None
            deal.key(),
        )
        for deal in candidates
    ]
    conn.executemany(
        """
        INSERT INTO deals (
            deal_id, run_id, target, acquirer, date, deal_value,
            multiples_disclosed, computed_multiples_available,
            multiples, source_urls, qualified, quality_signals, dedup_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def query_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all run records ordered by timestamp descending."""
    cursor = conn.execute("SELECT * FROM runs ORDER BY timestamp DESC")
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def query_deals(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all deal records for a specific run."""
    cursor = conn.execute("SELECT * FROM deals WHERE run_id = ?", (run_id,))
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def query_run_exists(
    conn: sqlite3.Connection,
    sector: str,
    geography: str,
    start_date: str,
    end_date: str,
) -> bool:
    """Return True if a run with matching sector, geography, and date range already exists."""
    cursor = conn.execute(
        """
        SELECT 1 FROM runs
        WHERE json_extract(params, '$.sector')     = ?
          AND json_extract(params, '$.geography')  = ?
          AND json_extract(params, '$.start_date') = ?
          AND json_extract(params, '$.end_date')   = ?
        LIMIT 1
        """,
        (sector, geography, start_date, end_date),
    )
    return cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# Cost accounting extensions (cost-accounting-001, ca-2)
# ---------------------------------------------------------------------------


def update_run_cost(conn: sqlite3.Connection, run_id: str, cost: CostBreakdown) -> None:
    """Late update of cost columns for a run (called after all agents complete in orchestrator).

    Enables full 8-agent accounting while keeping the early insert_run (for deal FKs) unchanged.
    """
    conn.execute(
        """
        UPDATE runs
        SET input_tokens = ?,
            output_tokens = ?,
            estimated_cost_usd = ?,
            cost_model = ?
        WHERE run_id = ?
        """,
        (
            cost.usage.input_tokens,
            cost.usage.output_tokens,
            cost.estimated_cost_usd,
            cost.model,
            run_id,
        ),
    )
    conn.commit()


def get_run_cost(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Fetch the cost record for a single run (or None)."""
    cursor = conn.execute(
        """
        SELECT run_id, input_tokens, output_tokens, estimated_cost_usd, cost_model, timestamp
        FROM runs
        WHERE run_id = ?
        """,
        (run_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row, strict=True))


def get_industry_cost_summary(
    conn: sqlite3.Connection, sector: str, geography: str
) -> dict[str, Any]:
    """Rollup of cost, tokens, and run count for one (sector, geography) industry.

    Powers the $50 per-industry soft budget target, warnings, and dashboard surfaces.
    Returns zeros when no matching runs exist.
    """
    cursor = conn.execute(
        """
        SELECT
            COUNT(*) AS run_count,
            COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0) AS total_cost_usd,
            COALESCE(AVG(estimated_cost_usd), 0.0) AS avg_cost_usd,
            COALESCE(MAX(estimated_cost_usd), 0.0) AS max_cost_usd
        FROM runs
        WHERE json_extract(params, '$.sector') = ?
          AND json_extract(params, '$.geography') = ?
        """,
        (sector, geography),
    )
    row = cursor.fetchone()
    cols = [d[0] for d in cursor.description]
    data = dict(zip(cols, row, strict=True))
    data["sector"] = sector
    data["geography"] = geography
    data["budget_target_usd"] = 50.0
    data["remaining_budget_usd"] = max(0.0, 50.0 - data["total_cost_usd"])
    data["over_budget"] = data["total_cost_usd"] > 50.0
    return data


# --- Quality signals helpers (quality-signals-001) ---


def update_deal_quality_signals(
            """
            UPDATE deals
            SET quality_signals = ?
            WHERE run_id = ? AND dedup_key = ?
            """,
            (qjson, run_id, key),
        )
        updated += cur.rowcount
    conn.commit()
    return updated


def query_deal_quality(conn: sqlite3.Connection, deal_id: str) -> dict[str, Any] | None:
    """Return parsed quality_signals for a specific deal_id, or None."""
    cursor = conn.execute("SELECT quality_signals FROM deals WHERE deal_id = ? LIMIT 1", (deal_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return None
    try:
        data: Any = json.loads(row[0])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None

