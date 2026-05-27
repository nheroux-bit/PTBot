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


def kill_all_active_cloud_runs(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return all active (dispatched/running) cloud run records and mark them revoked.

    This is the nuclear recovery option for firestorms.  Callers are responsible
    for actually invoking ``kill_cloud_run()`` per record — this function only
    updates the registry so the state is consistent even if the oz CLI fails.

    Returns the list of runs that were active before the call (for reporting).
    """
    active = list_cloud_runs(conn, active_only=True)
    now = datetime.now(UTC).isoformat()
    if active:
        placeholders = ",".join("?" for _ in active)
        conn.execute(
            f"UPDATE cloud_runs SET status='revoked', completed_at=?"
            f" WHERE oz_run_id IN ({placeholders})",
            [now, *(r["oz_run_id"] for r in active)],
        )
        conn.commit()
    return active


def count_active_cloud_runs(conn: sqlite3.Connection) -> int:
    """Return the number of cloud runs currently in dispatched or running state."""
    row = conn.execute(
        "SELECT COUNT(*) FROM cloud_runs WHERE status IN ('dispatched', 'running')"
    ).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# New: Database querying layer for agents (exploration + precise selection)
# Goal: Allow agents to understand what's in the DB and pull exact sets of
# deals for delivery (especially Excel).
# ---------------------------------------------------------------------------


def row_to_deal_candidate(row: dict[str, Any]) -> DealCandidate:
    """Convert a row from the deals table back into a DealCandidate."""

    def _safe_json_load(val: Any, default: list[str]) -> list[str]:
        if not val:
            return default
        if isinstance(val, (list, tuple)):
            return list(val)
        try:
            loaded = json.loads(val)
            return loaded if isinstance(loaded, list) else default
        except Exception:
            return default

    multiples = tuple(_safe_json_load(row.get("multiples"), []))
    source_urls = tuple(_safe_json_load(row.get("source_urls"), []))

    return DealCandidate(
        target=row["target"],
        acquirer=row["acquirer"],
        date=row.get("date"),
        deal_value=row.get("deal_value"),
        multiples_disclosed=bool(row.get("multiples_disclosed")),
        computed_multiples_available=bool(row.get("computed_multiples_available")),
        multiples=multiples,
        source_urls=source_urls,
    )


def search_deals(
    conn: sqlite3.Connection,
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = None,
    target_search: str | None = None,
    acquirer_search: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search the deals table with common filters.

    Returns raw rows (with run metadata joined) so agents can inspect and reason.
    Use row_to_deal_candidate() if you need DealCandidate objects for Excel etc.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if sector:
        conditions.append("json_extract(r.params, '$.sector') = ?")
        params.append(sector)
    if geography:
        conditions.append("json_extract(r.params, '$.geography') = ?")
        params.append(geography)
    if qualified is not None:
        conditions.append("d.qualified = ?")
        params.append(1 if qualified else 0)
    if target_search:
        conditions.append("d.target LIKE ?")
        params.append(f"%{target_search}%")
    if acquirer_search:
        conditions.append("d.acquirer LIKE ?")
        params.append(f"%{acquirer_search}%")
    if min_date:
        conditions.append("d.date >= ?")
        params.append(min_date)
    if max_date:
        conditions.append("d.date <= ?")
        params.append(max_date)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    # Use 'is not None' so limit=0 → LIMIT 0 (return 0 rows, standard SQL semantics).
    # Plain `if limit` would treat 0 as falsy and silently return all rows.
    limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""

    sql = f"""
        SELECT
            d.*,
            json_extract(r.params, '$.sector')    AS sector,
            json_extract(r.params, '$.geography') AS geography,
            r.timestamp                           AS run_timestamp
        FROM deals d
        JOIN runs r ON d.run_id = r.run_id
        {where_clause}
        ORDER BY d.date DESC, d.target
        {limit_clause}
    """

    cursor = conn.execute(sql, params)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def summarize_database(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    High-level summary of the database contents.
    Designed to be returned to an agent so it can tell the user what's available.
    """
    summary: dict[str, Any] = {}

    # Basic counts
    summary["total_runs"] = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    summary["total_deals"] = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    summary["qualified_deals"] = conn.execute(
        "SELECT COUNT(*) FROM deals WHERE qualified = 1"
    ).fetchone()[0]

    # Sectors
    sectors = conn.execute("""
        SELECT json_extract(params, '$.sector') as sector, COUNT(*) as run_count
        FROM runs
        GROUP BY sector
        ORDER BY run_count DESC
        """).fetchall()
    summary["sectors"] = [{"sector": s[0], "runs": s[1]} for s in sectors if s[0]]

    # Year coverage (from deal dates where possible)
    years = conn.execute("""
        SELECT substr(date, 1, 4) as year, COUNT(*) as deal_count
        FROM deals
        WHERE date IS NOT NULL
        GROUP BY year
        ORDER BY year
        """).fetchall()
    summary["years_covered"] = [{"year": y[0], "deals": y[1]} for y in years if y[0]]

    return summary


def format_search_results_for_agent(
    results: list[dict[str, Any]],
    *,
    max_items: int = 15,
) -> str:
    """
    Turn the output of search_deals() into a compact, readable text block
    that an agent can directly use when talking to the user.
    """
    if not results:
        return "No matching deals found in the database."

    lines = [f"Found {len(results)} matching deals in the database:\n"]

    for i, row in enumerate(results[:max_items], 1):
        try:
            multiples = json.loads(row.get("multiples") or "[]")
        except (json.JSONDecodeError, TypeError):
            multiples = []
        mult_str = "; ".join(multiples[:2]) if multiples else "No multiples listed"

        line = (
            f"{i}. {row['target']} acquired by {row['acquirer']} "
            f"({row.get('date', 'date unknown')}) — "
            f"{row.get('deal_value', 'value unknown')} | "
            f"{mult_str} | "
            f"{'Qualified' if row.get('qualified') else 'Not qualified'}"
        )
        lines.append(line)

    if len(results) > max_items:
        lines.append(f"\n... and {len(results) - max_items} more.")

    return "\n".join(lines)


def search_deals_as_candidates(
    conn: sqlite3.Connection,
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = None,
    target_search: str | None = None,
    acquirer_search: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    limit: int | None = None,
) -> list[DealCandidate]:
    """Convenience wrapper: search_deals + convert every row to DealCandidate."""
    rows = search_deals(
        conn,
        sector=sector,
        geography=geography,
        qualified=qualified,
        target_search=target_search,
        acquirer_search=acquirer_search,
        min_date=min_date,
        max_date=max_date,
        limit=limit,
    )
    return [row_to_deal_candidate(r) for r in rows]


def get_deal_statistics(
    conn: sqlite3.Connection,
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = True,
) -> dict[str, Any]:
    """Lightweight aggregate stats for agents (counts, avg multiples, etc.)."""
    rows = search_deals(conn, sector=sector, geography=geography, qualified=qualified, limit=5000)
    if not rows:
        return {"total_deals": 0, "qualified": 0, "avg_standard_multiples": 0.0}

    total = len(rows)
    qualified_count = sum(1 for r in rows if r.get("qualified"))
    multiples_counts = []
    for r in rows:
        try:
            mults = json.loads(r.get("multiples") or "[]")
            dc = DealCandidate(target=r["target"], acquirer=r["acquirer"], multiples=mults)
            multiples_counts.append(dc.standard_multiple_count())
        except Exception:
            continue

    avg = sum(multiples_counts) / len(multiples_counts) if multiples_counts else 0.0
    return {
        "total_deals": total,
        "qualified": qualified_count,
        "avg_standard_multiples": round(avg, 2),
    }


def get_top_deals(
    conn: sqlite3.Connection,
    *,
    n: int = 5,
    by: str = "recent",
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = True,
) -> list[DealCandidate]:
    """Return top-N deals by recency or number of standard multiples."""
    candidates = search_deals_as_candidates(
        conn, sector=sector, geography=geography, qualified=qualified, limit=500
    )
    if by == "multiples":
        candidates.sort(key=lambda d: d.standard_multiple_count(), reverse=True)
    else:
        # default "recent" — rely on search_deals ordering (date DESC)
        pass
    return candidates[:n]


# ---------------------------------------------------------------------------
# Query CLI helpers (ptbot query runs / deals / export)
# ---------------------------------------------------------------------------


def list_runs_with_stats(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    """Return runs with per-run deal and qualified-deal counts.

    Each row includes the JSON-extracted sector/geography/date range plus
    total_deals and qualified_deals counts via a LEFT JOIN on deals.
    Ordered newest-first.
    """
    conditions = []
    params: list[Any] = []
    if since:
        conditions.append("r.timestamp >= ?")
        params.append(since)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
    sql = f"""
        SELECT
            r.run_id,
            json_extract(r.params, '$.sector')     AS sector,
            json_extract(r.params, '$.geography')  AS geography,
            json_extract(r.params, '$.start_date') AS start_date,
            json_extract(r.params, '$.end_date')   AS end_date,
            r.timestamp,
            COUNT(d.deal_id)                       AS total_deals,
            SUM(CASE WHEN d.qualified = 1 THEN 1 ELSE 0 END) AS qualified_deals
        FROM runs r
        LEFT JOIN deals d ON d.run_id = r.run_id
        {where}
        GROUP BY r.run_id
        ORDER BY r.timestamp DESC
        {limit_clause}
    """
    cursor = conn.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def get_run_details(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Return a single run record with deal stats, or None if not found."""
    rows = list_runs_with_stats(conn, limit=None)
    for r in rows:
        if r["run_id"] == run_id or r["run_id"].startswith(run_id):
            return r
    return None


def get_similar_deals(
    conn: sqlite3.Connection,
    *,
    sector: str | None = None,
    geography: str | None = None,
    limit: int = 10,
    qualified: bool | None = True,
) -> list[DealCandidate]:
    """Fuzzy 'similar' search using substring match on sector/geography."""
    rows = search_deals(conn, qualified=qualified, limit=500)
    results: list[DealCandidate] = []
    for r in rows:
        run_sector = r.get("sector") or ""
        run_geo = r.get("geography") or ""
        # 'not X or X in ...' → include this row when the filter is absent (None);
        # AND → both dimensions must pass, preventing an all-None call from returning nothing.
        if (not sector or sector.lower() in run_sector.lower()) and (
            not geography or geography.lower() in run_geo.lower()
        ):
            try:
                results.append(row_to_deal_candidate(r))
            except Exception:
                continue
        if len(results) >= limit:
            break
    return results
