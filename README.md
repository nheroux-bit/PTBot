# PTBot

PTBot is a two-pass precedent transaction research bot for Warp/Oz agents. It discovers M&A transactions for a user-defined sector, geography, and date range; filters to deals with standard disclosed or computable valuation multiples; then produces a QC-checked deliverable in markdown, PDF, and Excel.

## What it does

- Runs four parallel discovery scouts across press/news, regulatory filings, deal databases, and industry/analyst sources.
- Deduplicates deal candidates by target/acquirer pair.
- Filters out transactions without qualifying standard valuation multiples.
- Runs deal-aware deep-dive agents on the qualified transaction set.
- Produces a final QC-reviewed precedent transaction report.
- Generates supporting markdown, JSON metadata, PDF output, and an Excel comps workbook.

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

## Usage

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
  --output-dir ./precedent-txn-output
```

Optional filters:

- `--min-multiples`: minimum number of standard multiples required per included deal
- `--deal-size-min`: minimum deal size filter
- `--deal-size-max`: maximum deal size filter
- `--timeout`: per-agent timeout in seconds, defaulting to `900`
- `--output-dir`: output directory, defaulting to `./precedent-txn-output`
- `--db-path`: SQLite database path (e.g. `~/.ptbot/ptbot.db`). Omit to skip persistence.

When `--db-path` is provided, the run is recorded in a local SQLite database alongside all deal candidates and their qualified status. This enables cross-run queries and powers the sweep runner.

## Sweep runner

`ptbot-sweep` builds a deal database automatically by running `ptbot` across a configurable set of markets and annual time windows. Combinations already present in the database are detected and skipped, so the sweep can be interrupted and resumed freely.

### 1. Create a config file

Copy `sweep.example.toml` and edit the `[[markets]]` list:

```toml
[sweep]
years_back = 10
db_path = "~/.ptbot/ptbot.db"
output_base_dir = "./precedent-txn-output"
min_multiples = 1
timeout = 900

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

Prints every `(sector, geography, year)` combination that would be executed — no agents are invoked.

### 3. Run the sweep

```bash
.venv/bin/ptbot-sweep --config my-sweep.toml
```

Runs all combinations sequentially, oldest year first. Progress is printed as each run completes:

```
[sweep] 2 market(s) × 11 windows = 22 combinations
[sweep] run   Vertical SaaS / United States 2016 ...
[sweep] done  Vertical SaaS / United States 2016
[sweep] run   Vertical SaaS / United States 2017 ...
...
[sweep] complete — 22 run(s), 0 skipped
```

On a subsequent run, completed combinations are skipped automatically:

```
[sweep] skip  Vertical SaaS / United States 2016
[sweep] skip  Vertical SaaS / United States 2017
...
[sweep] complete — 0 run(s), 22 skipped
```

### Skip logic

Before each run the sweep queries the SQLite database for an existing row in the `runs` table whose stored `params` JSON matches the exact `(sector, geography, start_date, end_date)` combination. If a match is found the combination is skipped without calling any agents. This means:

- Interrupting a sweep mid-way and restarting resumes from the first incomplete combination.
- Adding new markets to the config only runs those new combinations.
- Re-running the same config after it fully completes is a no-op.

### Output layout

Each annual run writes its outputs under a slugified path:

```
{output_base_dir}/{sector-slug}/{geography-slug}/{year}/
  final_deliverable.md
  final_deliverable.pdf
  precedent_comps.xlsx
  supporting/
  metadata/
```

For example: `./precedent-txn-output/vertical-saas/united-states/2023/`

### Sweep CLI options

- `--config` (required): path to TOML config file
- `--db-path`: override the `db_path` from config
- `--dry-run`: print planned runs without executing any agents

## Querying the database

Once the database has been populated (via `--db-path` or `ptbot-sweep`), explore it from the terminal:

```bash
# List recent pipeline runs with deal counts
.venv/bin/ptbot query runs --db-path ~/.ptbot/ptbot.db

# Search deals by sector and show only qualified ones
.venv/bin/ptbot query deals --sector "FinTech" --qualified-only

# Export all deals matching a filter to CSV
.venv/bin/ptbot query export --sector "FinTech" --output fintech-deals.csv

# Export to JSON for scripting
.venv/bin/ptbot query export --format json

# JSON output for any subcommand
.venv/bin/ptbot query runs --format json
.venv/bin/ptbot query deals --geography "United States" --format json
```

Flags available on all `query` subcommands:
- `--db-path`: path to the SQLite database (default: `~/.ptbot/ptbot.db`)
- `--format table|json` (or `csv|json` for `export`)

Additional flags:
- `query runs`: `--limit N`, `--since YYYY-MM-DD`
- `query deals`: `--sector`, `--geography`, `--since`, `--qualified-only`, `--limit N`
- `query export`: `--sector`, `--geography`, `--qualified-only`, `--limit N`, `--output FILE`

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

## Development

```bash
task fmt
task lint
task test
task test:coverage
task build
task check
```

`task check` is the pre-commit gate and runs formatting checks, linting, type checking, tests with coverage, and package compilation.

## Project structure

- `src/ptbot/cli.py`: `ptbot` command-line interface
- `src/ptbot/orchestrator.py`: two-pass agent orchestration and output writing
- `src/ptbot/prompt_builder.py`: scout, deep-dive, QC, and config prompt generation
- `src/ptbot/models.py`: validated data models
- `src/ptbot/pdf.py`: markdown-to-PDF generation
- `src/ptbot/excel.py`: Excel comps workbook generation
- `src/ptbot/db.py`: SQLite persistence layer (runs and deals tables)
- `src/ptbot/sweep.py`: sweep runner logic (config models, window generation, orchestration)
- `src/ptbot/sweep_cli.py`: `ptbot-sweep` command-line interface
- `sweep.example.toml`: annotated sweep config template
- `tests/`: unit and integration tests
