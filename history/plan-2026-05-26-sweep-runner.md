# Plan: PTBot Sweep Runner — 2026-05-26

Branch: `feat/sweep-runner`
vBRIEF: `vbrief/active/sweep-runner.vbrief.json`

## Problem
Building a 10-year deal database by hand-running individual `ptbot` invocations is tedious. A sweep runner automates this: it reads a config of (sector, geography) targets, slices a N-year window into annual chunks, skips combinations already in the DB, and runs the pipeline sequentially until the database is fully populated.

## Changes

### 1. `src/ptbot/db.py` — add `query_run_exists()`
Uses SQLite `json_extract` on the `params` column. Returns `bool`.

### 2. `src/ptbot/sweep.py` — core sweep logic
- `MarketTarget(sector, geography)` — pydantic model
- `SweepSettings(years_back, db_path, output_base_dir, min_multiples, timeout)` — pydantic model
- `SweepConfig(sweep, markets)` — pydantic model
- `load_config(path)` — parse TOML via `tomllib` (stdlib)
- `generate_annual_windows(years_back)` — complete calendar years oldest-first, current year as partial
- `slug(text)` — lowercase hyphen slug for directory names
- `run_sweep(config, *, runner, dry_run)` — main loop

### 3. `src/ptbot/sweep_cli.py` — `ptbot-sweep` entry point
`--config` (required), `--db-path` (override), `--dry-run`

### 4. `pyproject.toml`
Add `ptbot-sweep = "ptbot.sweep_cli:main"` to `[project.scripts]`.

### 5. `sweep.example.toml`
Annotated example config at project root.

### 6. Tests
- `tests/test_db.py` extended with `query_run_exists` cases
- `tests/test_sweep.py` new: windows, config parsing, skip/call/dry-run logic

## Constraints
- No new runtime dependencies (`tomllib` is stdlib in Python 3.11+)
- Existing `ptbot` CLI and all existing tests unchanged
- Frozen pydantic models untouched

## Verification
`task setup && task check` must pass green.
