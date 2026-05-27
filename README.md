# PTBot

PTBot is a two-pass precedent transaction research bot for Warp/Oz agents. It discovers M&A transactions for a user-defined sector, geography, and date range; filters to deals with standard disclosed or computable valuation multiples; then produces a QC-checked deliverable in markdown, PDF, and Excel.

## What it does

- Runs four parallel discovery scouts across press/news, regulatory filings, deal databases, and industry/analyst sources.
- Deduplicates deal candidates by target/acquirer pair.
- Filters out transactions without qualifying standard valuation multiples.
- Runs deal-aware deep-dive agents on the qualified transaction set.
- Produces a final QC-reviewed precedent transaction report.
- Generates supporting markdown, JSON metadata, PDF output, and an Excel comps workbook.
- Persists every run and its deal candidates to a local SQLite database for cross-run queries and sweeps.

## Requirements

- Python 3.11+
- Taskfile (`task`) for project commands
- Warp/Oz CLI access for live agent orchestration
- The `attack.market` skill installed at `~/.agents/skills/attack.market/`

## Setup

```bash
task setup
```

This creates `.venv`, installs PTBot in editable mode, and installs development dependencies.

## Running a single analysis

Preview the generated pipeline configuration without running agents:

```bash
.venv/bin/ptbot \
  --sector "Vertical SaaS" \
  --geography "Boston" \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --config-only
```

Run a full precedent transaction analysis:

```bash
.venv/bin/ptbot \
  --sector "Vertical SaaS" \
  --geography "Boston" \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --output-dir ./precedent-txn-output \
  --db-path ~/.ptbot/ptbot.db
```

Flags:

- `--sector` / `--industry`: sector or industry vertical
- `--geography`: geographic scope
- `--min-multiples`: minimum standard multiples required per deal (default: 1)
- `--deal-size-min` / `--deal-size-max`: deal size filters
- `--timeout`: per-agent timeout in seconds (default: 900)
- `--output-dir`: output directory (default: `./precedent-txn-output`)
- `--db-path`: SQLite database path. When provided, runs and deals are persisted for cross-run queries and sweeps. Omit to skip persistence.
- `--config-only`: print the generated config JSON and exit

## Outputs

A full run writes:

- `final_deliverable.md`: QC-reviewed markdown report
- `final_deliverable.pdf`: PDF version of the final report
- `precedent_comps.xlsx`: IB-formatted Excel comps workbook
- `supporting/qualified_deals.json`: filtered deal manifest
- `supporting/pass1_compiled_deals.md`: compiled discovery scout output
- `supporting/pass2_compiled_deep.md`: compiled deep-dive output
- `supporting/qc_report.md`: QC agent output
- `metadata/run_metadata.json`: run parameters and agent execution metadata

## Building full-sector coverage

One command progressively builds comprehensive M&A coverage across all 38 major tech startup verticals:

```bash
# First run: sweeps all sectors, dispatches ~380 cloud agents (38 sectors × 10 years)
ptbot sweep:auto \
  --preset startup-tech \
  --geography "United States" \
  --years 10 \
  --environment <oz-env-id>

# Check what's covered vs. missing
ptbot db:coverage --preset startup-tech --geography "United States"

# Run again anytime — only missing combinations are dispatched
ptbot sweep:auto \
  --preset startup-tech \
  --geography "United States" \
  --environment <oz-env-id>
```

Output from `db:coverage`:
```
DB coverage: startup-tech (United States) | last 5 years

sector                    covered  missing  deals
---------                 -------  -------  -----
AI / Machine Learning     5        0        847
Cybersecurity             5        0        612
FinTech                   5        0        1203
MLOps                     2        3        88
...

Total: 187/190 combinations covered (98%) | 14,392 deals in DB
Run `ptbot sweep:auto --preset startup-tech --geography 'United States' --dry-run` to preview gaps.
```

The sweep is fully incremental — skip detection means re-running it weekly only fills in the new year's deals. No work is ever duplicated.

Available presets:
- `startup-tech` — 38 tech startup verticals (FinTech, AI/ML, Cybersecurity, SaaS, HealthTech, CleanTech, etc.)

Or use `startup-sectors.toml` for the TOML-based runner:
```bash
ptbot-sweep --config startup-sectors.toml --cloud --environment <oz-env-id>
```

## Auto-populating the database

`ptbot sweep:auto` is the fastest way to populate the database — no TOML config file needed. Pass sectors as a comma-separated list and PTBot dispatches parallel cloud agents across all missing market×year combinations:

```bash
# Sweep two sectors over the last 5 years using cloud agents (recommended)
.venv/bin/ptbot sweep:auto \
  --sectors "FinTech,HealthTech" \
  --geography "United States" \
  --years 5 \
  --environment <oz-env-id>

# Preview what would run without invoking any agents
.venv/bin/ptbot sweep:auto \
  --sectors "SaaS,Drones,AI" \
  --geography "United States" \
  --dry-run

# Sweep locally (no --environment; uses local oz agents)
.venv/bin/ptbot sweep:auto \
  --sectors "VerticalSaaS" \
  --geography "Europe" \
  --years 3
```

Flags:

- `--sectors` (required): comma-separated list of sectors
- `--geography` (required): geographic scope applied to all sectors
- `--years N`: years to look back (default: 5)
- `--environment ENV_ID`: Oz cloud environment — enables cloud dispatch and parallel execution
- `--max-workers N`: parallel pipeline cap (default: 4)
- `--timeout N`: per-pipeline agent timeout in seconds (default: 900)
- `--db-path PATH`: SQLite database (default: `~/.ptbot/ptbot.db`)
- `--max-active N`: abort if N or more cloud runs are already active — see [Cloud safeguards](#cloud-safeguards) (default: 10)
- `--dry-run`: print planned runs without invoking agents

Combinations already present in the database are skipped automatically, so it is safe to re-run.

## Sweep runner (TOML-based)

`ptbot-sweep` builds a deal database from a TOML config file. Use this for version-controlled configurations or advanced settings.

### 1. Create a config file

Copy `sweep.example.toml` and edit the `[[markets]]` list:

```toml
[sweep]
years_back = 10
db_path = "~/.ptbot/ptbot.db"
output_base_dir = "./precedent-txn-output"
min_multiples = 1
timeout = 900
max_workers = 4            # parallel pipelines
max_active_cloud_runs = 10 # WIP cap (see Cloud safeguards)

[[markets]]
sector = "Vertical SaaS"
geography = "United States"

[[markets]]
sector = "HealthTech"
geography = "United States"
```

### 2. Preview the planned runs

```bash
.venv/bin/ptbot-sweep --config my-sweep.toml --dry-run
```

### 3. Run the sweep

```bash
# Local agents
.venv/bin/ptbot-sweep --config my-sweep.toml

# Cloud agents (parallel)
.venv/bin/ptbot-sweep --config my-sweep.toml --cloud --environment <oz-env-id>
```

Progress is printed as each run completes. On a subsequent run, completed combinations are skipped automatically.

### Skip logic

Before each run the sweep checks the database for a row matching the exact `(sector, geography, start_date, end_date)` combination. If found, that combination is skipped. This means:

- Interrupting a sweep mid-way and restarting resumes from the first incomplete combination.
- Adding new markets to the config only runs those new combinations.
- Re-running a fully completed config is a no-op.

### Output layout

Each annual run writes under a slugified path:

```
{output_base_dir}/{sector-slug}/{geography-slug}/{year}/
  final_deliverable.md
  final_deliverable.pdf
  precedent_comps.xlsx
  supporting/
  metadata/
```

### Sweep CLI options

- `--config` (required): path to TOML config file
- `--db-path`: override `db_path` from config
- `--cloud`: dispatch cloud agents instead of local agents
- `--environment ENV_ID`: Oz cloud environment ID (for `--cloud` runs)
- `--max-active N`: WIP cap override
- `--dry-run`: print planned runs without executing any agents

## Querying the database

Once the database has been populated, explore it from the terminal:

```bash
# List recent pipeline runs with deal counts
.venv/bin/ptbot query runs

# Search deals by sector (qualified only)
.venv/bin/ptbot query deals --sector "FinTech" --qualified-only

# Export to CSV
.venv/bin/ptbot query export --sector "FinTech" --output fintech-deals.csv

# Export to JSON for scripting
.venv/bin/ptbot query export --format json

# JSON output for any subcommand
.venv/bin/ptbot query runs --format json
.venv/bin/ptbot query deals --geography "United States" --format json
```

Subcommands and flags:

| Subcommand | Key flags |
|---|---|
| `query runs` | `--limit N`, `--since YYYY-MM-DD`, `--format table\|json` |
| `query deals` | `--sector`, `--geography`, `--since`, `--qualified-only`, `--limit N`, `--format table\|json` |
| `query export` | `--sector`, `--geography`, `--qualified-only`, `--limit N`, `--output FILE`, `--format csv\|json` |

All subcommands accept `--db-path` (default: `~/.ptbot/ptbot.db`).

## Streamlit dashboard

Launch the interactive deal database dashboard:

```bash
.venv/bin/ptbot app
```

The dashboard provides:

- Deal browser with sector/geography/year/qualification filters and Plotly charts
- Run history and statistics
- ☁️ Cloud Control page: list active cloud dispatches and kill individual runs

## Cloud control plane

PTBot tracks every cloud agent dispatch in a persistent SQLite registry (`cloud_runs` table). This survives parent-process death and enables reliable revocation even after a crash.

```bash
# List active cloud runs
.venv/bin/ptbot cloud status

# List all runs including completed/revoked
.venv/bin/ptbot cloud status --all

# Kill a specific run
.venv/bin/ptbot cloud kill <oz-run-id>
.venv/bin/ptbot cloud kill <oz-run-id> --force  # mark revoked even if oz CLI fails

# Kill every active run — firedrill recovery
.venv/bin/ptbot cloud kill-all
.venv/bin/ptbot cloud kill-all --dry-run        # preview without acting
```

All commands accept `--db-path` to target a non-default registry.

## Cloud safeguards

Three safeguards prevent runaway cloud agent storms:

**1. `ptbot cloud kill-all`** — nuclear recovery. One command kills every active run in the registry and marks all revoked in the DB, even when the oz CLI fails. Use `--dry-run` to preview.

**2. WIP cap** — `sweep:auto` and `ptbot-sweep --cloud` check the registry before dispatching. If active cloud runs ≥ `--max-active` (default: 10), the command aborts immediately with a list of blocking run IDs. Run `ptbot cloud kill-all` to clear them, or raise `--max-active`.

**3. Timeout watchdog** — a daemon thread launched automatically during cloud sweeps. Polls every 60 seconds and kills any run past `timeout × 1.5` seconds without a terminal status. Stops cleanly on sweep completion or Ctrl-C.

## Development

```bash
task fmt           # Format source
task lint          # Lint + type-check
task test          # Run tests
task test:coverage # Tests with coverage gate (≥85%)
task build         # Compile package
task check         # Pre-commit gate (all of the above)
```

## Project structure

```
src/ptbot/
  cli.py            ptbot CLI: single run, sweep:auto, query, cloud commands
  orchestrator.py   Two-pass agent orchestration and output writing
  prompt_builder.py Scout, deep-dive, QC, and config prompt generation
  models.py         Validated data models (DealCandidate, ResearchParams)
  pdf.py            Markdown-to-PDF generation
  excel.py          IB-formatted Excel comps workbook generation
  db.py             SQLite persistence: runs, deals, cloud_runs tables
  db_sync.py        S3 pull/push helpers for cloud-backed DB persistence
  sweep.py          Sweep runner: WIP cap, watchdog thread, parallel executor
  sweep_cli.py      ptbot-sweep CLI
  app.py            Streamlit deal database dashboard
  runners.py        Local and cloud Oz agent runners with control plane

sweep.example.toml  Annotated sweep config template
skill/              Warp/Oz skill scripts (precedent-transactions, etc.)
tests/              164 tests, 87.7% coverage
```
