# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- COST-ESTIMATE.md with pre-build cost analysis and recorded build decision
- PROJECT-DEFINITION.vbrief.json with project identity, tech stack, and architecture
- Cloud Execution Control Plane (cloud-control-001): persistent cloud_runs registry in db.py, early registration + live Popen in runners.py for firedrill-proof revocation, ptbot cloud status/kill CLI (and cloud: variants), dashboard "☁️ Cloud Control" page with kill buttons. Robust best-effort oz kill + registry marking. All dispatches via sweep/dashboard now registered. 13 new tests in test_cloud_control.py. Coordinated with parallel cost agent on db/runners.
- Full cost-accounting-001: CostBreakdown + TokenUsage models, static price table, heuristic estimation in runners (local+cloud), orchestrator aggregation + max_cost warnings, db schema migration + industry rollups ($50 target), --max-cost CLI flag, sweep budget config + per-industry tracking, basic dashboard cost KPIs/panels vs $50, comprehensive tests/test_cost.py. All task check gates green (90%+ cov on measured modules).

### Changed
- Migrated to vBRIEF-centric document model: SPECIFICATION.md and PROJECT.md replaced with deprecated-redirect stubs
- Moved build scope vBRIEF from proposed/ to completed/
- Updated all specification.vbrief.json task statuses from pending to completed
- Fixed mypy type errors in excel.py: added Worksheet/Cell annotations, narrowed union types for implied_metric
- Applied black formatting to excel.py and test_outputs.py
- Sorted imports with isort in excel.py

### Fixed
- excel.py: implied_metric division guard now uses explicit None check instead of `in (None, 0)` to satisfy mypy
- excel.py: write_deal_row narrows dict values through isinstance before passing to implied_metric
