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

-- cloud-control-001: Cloud execution control plane registry.
-- Survives parent death for post-firedrill revocation.
-- Orthogonal to cost-accounting-001 (separate table; cost_estimate_usd
-- field allows future population from cost instrumentation).
CREATE TABLE IF NOT EXISTS cloud_runs (
    oz_run_id          TEXT PRIMARY KEY,
    parent             TEXT NOT NULL DEFAULT '',
    environment        TEXT,
    cost_estimate_usd  REAL,
    dispatched_at      TEXT NOT NULL,
    completed_at       TEXT,
    status             TEXT NOT NULL DEFAULT 'dispatched',
    run_url            TEXT NOT NULL DEFAULT '',
    prompt_excerpt     TEXT NOT NULL DEFAULT '',
    exit_code          INTEGER,
    error              TEXT
);
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and apply the schema.

    Creates all parent directories as needed. Enables WAL journal mode
    and foreign-key enforcement on every connection.

    Cloud control plane table (cloud_runs) is included; existing DBs get
    the table on next open (IF NOT EXISTS is safe and concurrent-friendly
    with WAL).
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


# ---------------------------------------------------------------------------
# Cloud execution control plane (cloud-control-001)
# ---------------------------------------------------------------------------
#
# Persistent registry for oz agent run-cloud dispatches. Survives parent
# process death (the root cause of the 2026-05 cloud sub-agent firedrill).
# Enables listing active/revoked runs + reliable revocation even when the
# launching sweep/dashboard/CLI has crashed or been killed.
#
# Soft coordination with cost-accounting-001: cost_estimate_usd field
# allows population from cost work (parallel agent in ptbot-swarm-cost).
# cloud_runs table is independent — zero conflict on schema.
#
# Enforcement: every path that calls oz run-cloud must register via
# register_cloud_dispatch (wired in runners.py + sweep.py call sites).
# See also: runners.kill_cloud_run for the revocation attempt logic.


def register_cloud_dispatch(
    conn: sqlite3.Connection,
    oz_run_id: str,
    *,
    parent: str = "",
    environment: str | None = None,
    cost_estimate_usd: float | None = None,
    run_url: str = "",
    prompt_excerpt: str = "",
) -> None:
    """Register (or update) a cloud Oz agent dispatch in the control plane.

    Idempotent on oz_run_id (supports re-registration on retries or
    post-crash reconciliation). Timestamps in UTC ISO format.

    This is the enforcement point: every cloud dispatch must call this
    (directly or via runners.py wrappers) so the registry survives parent
    death.
    """
    if not oz_run_id:
        # Never store empty; caller should synthesize "pending-<uuid>"
        raise ValueError("oz_run_id is required for cloud dispatch registration")

    now = datetime.now(UTC).isoformat()
    excerpt = (prompt_excerpt or "")[:500]  # bound size for safety

    # Idempotent insert-or-merge (no data loss on concurrent or re-entry)
    conn.execute(
        """
        INSERT OR IGNORE INTO cloud_runs (
            oz_run_id, parent, environment, cost_estimate_usd,
            dispatched_at, status, run_url, prompt_excerpt
        ) VALUES (?, ?, ?, ?, ?, 'dispatched', ?, ?)
        """,
        (oz_run_id, parent, environment, cost_estimate_usd, now, run_url, excerpt),
    )
    # Always refresh mutable fields on re-registration (e.g. cost now known,
    # parent context enriched, run_url captured from NDJSON)
    conn.execute(
        """
        UPDATE cloud_runs SET
            parent = CASE WHEN ? != '' THEN ? ELSE parent END,
            environment = COALESCE(?, environment),
            cost_estimate_usd = COALESCE(?, cost_estimate_usd),
            run_url = CASE WHEN ? != '' THEN ? ELSE run_url END,
            prompt_excerpt = CASE WHEN ? != '' THEN ? ELSE prompt_excerpt END
        WHERE oz_run_id = ?
        """,
        (
            parent,
            parent,
            environment,
            cost_estimate_usd,
            run_url,
            run_url,
            excerpt,
            excerpt,
            oz_run_id,
        ),
    )
    conn.commit()


def update_cloud_run(
    conn: sqlite3.Connection,
    oz_run_id: str,
    *,
    status: str,
    completed_at: str | None = None,
    exit_code: int | None = None,
    error: str | None = None,
    cost_estimate_usd: float | None = None,
) -> None:
    """Update lifecycle status of a registered cloud run (terminal states)."""
    now = datetime.now(UTC).isoformat()
    if completed_at is None and status in {"succeeded", "failed", "killed", "revoked", "timed_out"}:
        completed_at = now

    conn.execute(
        """
        UPDATE cloud_runs SET
            status = ?,
            completed_at = COALESCE(?, completed_at),
            exit_code = COALESCE(?, exit_code),
            error = COALESCE(?, error),
            cost_estimate_usd = COALESCE(?, cost_estimate_usd)
        WHERE oz_run_id = ?
        """,
        (status, completed_at, exit_code, error, cost_estimate_usd, oz_run_id),
    )
    conn.commit()


def list_cloud_runs(
    conn: sqlite3.Connection,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    """Return cloud run records (newest first).

    If active_only, only non-terminal statuses (for dashboard/CLI status).
    """
    if active_only:
        sql = """
            SELECT * FROM cloud_runs
            WHERE status IN ('dispatched', 'running')
            ORDER BY dispatched_at DESC
        """
        cursor = conn.execute(sql)
    else:
        cursor = conn.execute("SELECT * FROM cloud_runs ORDER BY dispatched_at DESC")
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def get_cloud_run(conn: sqlite3.Connection, oz_run_id: str) -> dict[str, Any] | None:
    """Fetch a single cloud run by its oz run_id (or None)."""
    cursor = conn.execute("SELECT * FROM cloud_runs WHERE oz_run_id = ?", (oz_run_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [d[0] for d in cursor.description]
    return dict(zip(columns, row, strict=True))


def mark_cloud_run_revoked(conn: sqlite3.Connection, oz_run_id: str) -> None:
    """Mark a cloud run revoked (called after successful or best-effort kill)."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE cloud_runs SET status='revoked', completed_at=? WHERE oz_run_id=?",
        (now, oz_run_id),
    )
    conn.commit()
