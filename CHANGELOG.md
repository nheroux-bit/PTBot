# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `ptbot sweep:auto` subcommand: populate the deal database without a TOML config file. Pass `--sectors 'FinTech,HealthTech'`, `--geography`, `--years`, and optionally `--environment <oz-env-id>` to dispatch parallel cloud agents across all missing market×year combinations. Existing combinations are skipped automatically; `--dry-run` previews what would run.
- `ptbot query` subcommand: explore the local deal database without a Streamlit browser. `ptbot query runs` lists pipeline runs with deal counts; `ptbot query deals` searches across all runs with `--sector`, `--geography`, `--since`, and `--qualified-only` filters; `ptbot query export` writes CSV or JSON to stdout or a file. All three accept `--format table|json` (or `csv` for export) and `--db-path`.
- COST-ESTIMATE.md with pre-build cost analysis and recorded build decision
- PROJECT-DEFINITION.vbrief.json with project identity, tech stack, and architecture
- Cloud Execution Control Plane (cloud-control-001): persistent cloud_runs registry in db.py, early registration + live Popen in runners.py for firedrill-proof revocation, ptbot cloud status/kill CLI (and cloud: variants), dashboard "☁️ Cloud Control" page with kill buttons. Robust best-effort oz kill + registry marking. All dispatches via sweep/dashboard now registered. 13 new tests in tests/test_cloud_control.py. Coordinated with parallel cost agent on db/runners.
- SQLite deal store: persistent deal database (`db.py`) with `open_db`, `insert_run`, `insert_deals`, `query_runs`, `query_deals`; full provenance tracking across pipeline runs
- Streamlit deal database dashboard (`ptbot app`): interactive exploration of the deal DB with sector/geography/year/qualification filters and Plotly charts
- Sweep runner: configurable batch pipeline execution across multiple sector configs; tech-sector sweep config (Drones, AI, Fiber Optics, Data Centers, SaaS); `max_workers` for parallel execution; 21 new tests in tests/test_sweep.py
- Agent-friendly DB query layer and Excel export: `search_deals`, `summarize_database`, `get_deal_statistics`, `get_top_deals`, `get_similar_deals` in `db.py`; `generate_comps_excel_from_deals` in `excel.py` with `style="full"` and `style="light"` paths; `skill/scripts/precedent_database.py` agent facade

### Changed
- Migrated to vBRIEF-centric document model: SPECIFICATION.md and PROJECT.md replaced with deprecated-redirect stubs
- Moved build scope vBRIEF from proposed/ to completed/
- Updated all specification.vbrief.json task statuses from pending to completed
- Fixed mypy type errors in excel.py: added Worksheet/Cell annotations, narrowed union types for implied_metric
- Applied black formatting to excel.py and test_outputs.py
- Sorted imports with isort in excel.py
- app.py: removed unused `load_runs()` function, cleaned up lambda formatting, dropped unused imports
- pyproject.toml: excluded `app.py` from coverage gate (UI layer — no core pipeline logic)

### Fixed
- excel.py: implied_metric division guard now uses explicit None check instead of `in (None, 0)` to satisfy mypy
- excel.py: write_deal_row narrows dict values through isinstance before passing to implied_metric
- excel.py: `_generate_light_excel` layout bug — headers are now written at row 3 (not row 1) so the title cell is no longer clobbered; data starts at row 4; freeze_panes and auto_filter reference the correct rows
- runners.py: removed dead `TimeoutExpired` branch (manual `time.time()` loop never raises `subprocess.TimeoutExpired`)
- skill/scripts/precedent_database.py: removed unused `db_path` parameter from `export_deals_to_excel` (conversion to `DealCandidate` does not require a DB connection)
