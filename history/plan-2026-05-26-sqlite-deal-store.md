# Plan: SQLite Deal Store — 2026-05-26

Branch: `feat/sqlite-deal-store`
vBRIEF: `vbrief/proposed/sqlite-deal-store.vbrief.json`

## Problem
Pipeline runs write deal data to flat JSON files with no cross-run queryability. A lightweight SQLite layer fixes this using only stdlib.

## Current state
- `run_pipeline()` in `orchestrator.py` writes `qualified_deals.json` and `run_metadata.json` per-run
- `DealCandidate` and `ResearchParams` are frozen pydantic models — cannot be modified
- CLI (`cli.py`) drives `run_pipeline()` with no persistence flag today
- vBRIEF is in `vbrief/proposed/` — not yet activated

## Proposed changes

### 1. `src/ptbot/db.py` (new)
Stdlib `sqlite3` only. Two tables:
- `runs(run_id TEXT PK, params TEXT JSON, timestamp TEXT)`
- `deals(deal_id TEXT PK, run_id TEXT FK, target, acquirer, date, deal_value, multiples_disclosed INT, computed_multiples_available INT, multiples TEXT JSON, source_urls TEXT JSON, qualified INT)`

Public API:
- `open_db(db_path: Path) -> sqlite3.Connection` — create parent dirs, apply schema, WAL mode, foreign keys ON
- `new_run_id() -> str` — UUID4
- `insert_run(conn, run_id, params: ResearchParams) -> None`
- `insert_deals(conn, run_id, candidates, *, qualified_keys: set[str]) -> None` — bulk executemany, marks each deal qualified if its `.key()` is in `qualified_keys`
- `query_runs(conn) -> list[dict]`
- `query_deals(conn, run_id) -> list[dict]`

### 2. `src/ptbot/orchestrator.py` — integration
Add `db_path: Path | None = None` keyword-only param to `run_pipeline()`. After `deduped` and `qualified` are computed, if `db_path` is set:

```python
conn = db.open_db(db_path)
run_id = db.new_run_id()
db.insert_run(conn, run_id, params)
db.insert_deals(conn, run_id, deduped, qualified_keys={d.key() for d in qualified})
conn.close()
```

Existing tests pass unchanged because `db_path` defaults to `None`.

### 3. `src/ptbot/cli.py` — `--db-path` flag
Add optional `--db-path` arg (default `None`; help text shows `~/.ptbot/ptbot.db` as the typical path). Pass resolved `Path(args.db_path)` to `run_pipeline()` when set.

### 4. `tests/test_db.py` (new, ≥85% coverage on db.py)
Key cases:
- Schema idempotency (open twice, no error)
- Parent dir auto-creation
- `insert_run` / `query_runs` roundtrip
- `insert_deals` marks qualified correctly
- `query_deals` filters by `run_id`
- Multiple runs don't bleed across each other
- Empty candidate list is a no-op

## Constraints
- stdlib `sqlite3` only — no new deps
- DB is optional; `db_path=None` skips all persistence
- Existing tests unchanged
- Frozen pydantic models untouched

## Parallelization
Not beneficial — the four files are tightly coupled (db.py → orchestrator → cli → tests must land in order), and the total change surface is small (~150 lines of code + ~100 lines of tests).

## Verification
`task check` must pass green: black + isort + ruff + mypy + pytest ≥85% coverage + compileall.
