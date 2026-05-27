# PTBot — Handoff to Gamma
**Date:** 2026-05-26
**Branch:** `main` (all work merged)
**Repo:** https://github.com/nheroux-bit/PTBot

---

## What this project is

PTBot is a CLI tool that automates M&A precedent transaction (deal comps) research using parallel Oz/Warp AI agents. Given a sector, geography, and date range it runs a two-pass pipeline, then produces a QC-checked markdown report, PDF, and IB-formatted Excel comps workbook.

---

## Architecture

### Two-pass pipeline (`ptbot`)

```
Pass 1 — Discovery (4 parallel scouts)
  press_news | regulatory_filings | deal_databases | analyst_sources
        ↓
  Deduplicate by target/acquirer key
  Filter: keep only deals with ≥N standard valuation multiples
        ↓
Pass 2 — Deep Dive (3 parallel agents per qualified deal)
  target_terms | acquirer_rationale | comparable_benchmarks
        ↓
  QC agent → final_deliverable.md
        ↓
  PDF + Excel generation
```

### Database layer (`ptbot.db`)

Every pipeline run optionally writes to a local SQLite database at `~/.ptbot/ptbot.db` (controlled by `--db-path`).

**Schema:**
- `runs(run_id TEXT PK, params TEXT JSON, timestamp TEXT)` — one row per pipeline invocation
- `deals(deal_id TEXT PK, run_id FK, target, acquirer, date, deal_value, multiples_disclosed INT, computed_multiples_available INT, multiples TEXT JSON, source_urls TEXT JSON, qualified INT)` — one row per deduplicated candidate

### Sweep runner (`ptbot-sweep`)

Reads a TOML config of `[[markets]]` (sector + geography pairs), generates annual windows from `years_back` (default 10) back to today, queries the DB to skip already-completed combinations, and runs the pipeline sequentially.

Skip logic: `SELECT 1 FROM runs WHERE json_extract(params, '$.sector') = ? AND json_extract(params, '$.geography') = ? AND json_extract(params, '$.start_date') = ? AND json_extract(params, '$.end_date') = ?`

Idempotent — safe to interrupt and resume at any time.

---

## File map

```
src/ptbot/
  cli.py           — ptbot CLI (single run)
  sweep_cli.py     — ptbot-sweep CLI
  orchestrator.py  — two-pass pipeline orchestration
  sweep.py         — sweep config models, window generation, run_sweep()
  db.py            — SQLite persistence (open_db, insert_run, insert_deals,
                     query_runs, query_deals, query_run_exists)
  models.py        — frozen pydantic models (ResearchParams, DealCandidate, etc.)
  prompt_builder.py — scout/deep-dive/QC prompt construction
  pdf.py           — markdown → PDF (fpdf2)
  excel.py         — IB-formatted Excel comps (openpyxl)

tests/
  test_cli.py, test_db.py, test_sweep.py,
  test_orchestrator.py, test_models.py,
  test_outputs.py, test_prompt_builder.py

sweep.example.toml  — annotated sweep config template
```

---

## Stack

- Python 3.11+, no new runtime deps beyond what's in pyproject.toml
- `pydantic` (models), `fpdf2` (PDF), `openpyxl` (Excel), `tomllib` (stdlib, TOML config)
- SQLite via stdlib `sqlite3`
- Oz/Warp agents via the `attack.market` skill at `~/.agents/skills/attack.market/`
- Quality gate: `task check` (black + isort + ruff + mypy + pytest ≥85% coverage + compileall)

---

## Current test state

```
62 tests passing | 87% total coverage
db.py:    100%
sweep.py: 100%
cli.py:    98%
```

---

## vBRIEF state

Two scope vBRIEFs are marked `active` / `running` but their code is fully merged and working. They should be transitioned to `completed`:

- `vbrief/active/sqlite-deal-store.vbrief.json`
- `vbrief/active/sweep-runner.vbrief.json`

To close them out:
```bash
task -t .deft/core/Taskfile.yml scope:complete -- vbrief/active/sqlite-deal-store.vbrief.json
task -t .deft/core/Taskfile.yml scope:complete -- vbrief/active/sweep-runner.vbrief.json
```
(If those fail due to the `plan` key format issue, just move them manually to `vbrief/completed/` and set `"status": "completed"`.)

---

## How to run

```bash
# Install / reinstall (required after pyproject.toml changes)
task setup

# Single run (no DB)
.venv/bin/ptbot --sector "Vertical SaaS" --geography "Boston" \
  --start-date 2024-01-01 --end-date 2024-12-31

# Single run with DB persistence
.venv/bin/ptbot --sector "Vertical SaaS" --geography "Boston" \
  --start-date 2024-01-01 --end-date 2024-12-31 \
  --db-path ~/.ptbot/ptbot.db

# Sweep dry-run (no agents)
.venv/bin/ptbot-sweep --config sweep.example.toml --dry-run

# Sweep (builds database)
.venv/bin/ptbot-sweep --config sweep.example.toml

# Pre-commit gate
task check
```

---

## What was built in this session (2026-05-26)

1. **Deft upgrade** — framework bumped v0.23.0 → v0.34.0, submodule relocated from `deft/` to `.deft/core/`, `AGENTS.md` created at project root.
2. **SQLite deal store** (`src/ptbot/db.py`) — `open_db`, `new_run_id`, `insert_run`, `insert_deals`, `query_runs`, `query_deals`, `query_run_exists`. `--db-path` flag added to `ptbot` CLI.
3. **Sweep runner** (`src/ptbot/sweep.py` + `src/ptbot/sweep_cli.py`) — TOML config, annual window generation, skip-if-exists logic, `ptbot-sweep` entry point.
4. **Tests** — `tests/test_db.py` (19 tests), `tests/test_sweep.py` (18 tests).
5. **README** updated with `--db-path`, sweep runner usage, skip logic, and output layout docs.

---

## Immediate next steps (suggested)

- **Close out vBRIEFs** as noted above.
- **Choose markets and kick off the sweep.** Copy `sweep.example.toml`, add/edit `[[markets]]` blocks, run `ptbot-sweep`. With 4 markets × 11 windows = 44 runs at ~15 min each this is an overnight job.
- **Add a `query` CLI command** — expose `query_runs` / `query_deals` as a `ptbot query` subcommand so the DB can be explored without a SQLite client.
- **CHANGELOG** — no `CHANGELOG.md` entries have been written for the three PRs merged today.

---

## Known constraints / design decisions to be aware of

- **Frozen pydantic models** — `DealCandidate` and `ResearchParams` in `models.py` use `frozen=True`. Do not add fields or remove `frozen`. All persistence serializes via `.model_dump(mode="json")`.
- **DB is optional** — every code path where `db_path=None` must continue to work. The skip check is only run inside the sweep; the single `ptbot` run never queries the DB, only writes.
- **No new runtime deps** — the project deliberately uses only stdlib + existing deps. Adding a new dep requires updating `pyproject.toml` and re-running `task setup`.
- **`task check` is the gate** — never commit without it passing. It is wired as the pre-commit standard.
- **attack.market dependency** — the pipeline requires the `attack.market` skill at `~/.agents/skills/attack.market/scripts/orchestrate.py`. Tests bypass this via a fake runner injected through the `runner=` parameter.
