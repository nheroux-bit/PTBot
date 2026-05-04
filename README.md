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

- `src/ptbot/cli.py`: command-line interface
- `src/ptbot/orchestrator.py`: two-pass agent orchestration and output writing
- `src/ptbot/prompt_builder.py`: scout, deep-dive, QC, and config prompt generation
- `src/ptbot/models.py`: validated data models
- `src/ptbot/pdf.py`: markdown-to-PDF generation
- `src/ptbot/excel.py`: Excel comps workbook generation
- `tests/`: unit and integration tests
