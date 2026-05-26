"""SQLite persistence layer for PTBot deal candidates and pipeline runs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import DealCandidate, ResearchParams

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
    qualified                    INTEGER NOT NULL DEFAULT 0
);
"""


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
    conn.commit()
    return conn


def new_run_id() -> str:
    """Return a new unique run identifier (UUID4)."""
    return str(uuid.uuid4())


def insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    params: ResearchParams,
) -> None:
    """Insert a pipeline run record."""
    conn.execute(
        "INSERT INTO runs (run_id, params, timestamp) VALUES (?, ?, ?)",
        (
            run_id,
            json.dumps(params.model_dump(mode="json")),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def insert_deals(
    conn: sqlite3.Connection,
    run_id: str,
    candidates: list[DealCandidate],
    *,
    qualified_keys: set[str],
) -> None:
    """Insert deal candidates for a run.

    Each deal is marked as qualified if its normalised key appears in
    *qualified_keys*.  Bulk-inserted with a single ``executemany`` call.
    """
    if not candidates:
        return
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
        )
        for deal in candidates
    ]
    conn.executemany(
        """
        INSERT INTO deals (
            deal_id, run_id, target, acquirer, date, deal_value,
            multiples_disclosed, computed_multiples_available,
            multiples, source_urls, qualified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
