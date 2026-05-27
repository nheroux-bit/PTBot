---
name: precedent-transactions
description: >-
  Run a two-pass precedent transaction research workflow for M&A comparables,
  acquisition research, transaction multiples, deal comps, or comparable
  transactions. Use this skill whenever the user asks for precedent transaction
  analysis, M&A comps, deal comps, acquisition multiples, recent acquisitions in
  a sector/geography, or any request combining M&A/acquisitions with valuation
  multiples, time windows, geography, or sector filters.
---

# Precedent Transactions

Use PTBot to research acquisition precedents with disclosed or computable valuation multiples.

## Workflow

1. Pass 1: four source-specialized scouts search press/news, regulatory filings, deal databases, and analyst/industry sources.
2. Compile/filter: deduplicate candidates and retain only deals with disclosed or computable multiples.
3. Pass 2: three deal-aware agents deep-dive on target terms, acquirer rationale, and comparable benchmarks.
4. QC: validate multiples, geography, dates, source attribution, and consistency.
5. Output: markdown, PDF, and Excel comps workbook.

## CLI

```bash
python ~/.agents/skills/precedent-transactions/scripts/precedent_txns.py \
  --sector "AI" \
  --geography "Orlando, FL" \
  --start-date 2025-01-01 \
  --end-date 2026-05-01 \
  --output-dir ./precedent-txn-output
```

Use `--config-only` to preview the generated Pass 1 configuration without running agents.

## Output

```
precedent-txn-output/
├── final_deliverable.md
├── final_deliverable.pdf
├── precedent_comps.xlsx
├── supporting/
│   ├── pass1_compiled_deals.md
│   ├── qualified_deals.json
│   ├── pass2_compiled_deep.md
│   └── qc_report.md
└── metadata/
    └── run_metadata.json
```

## Querying the Historical Deal Database

Once you have run sweeps (or individual analyses with `--db-path`), you can query the accumulated precedent transaction database.

This is especially powerful for agents: an agent can first explore what data already exists, make precise selections, and deliver exactly the requested deals as a clean Excel file.

### Agent-Friendly API (recommended for Oz/Warp agents)

```python
from skill.scripts.precedent_database import (
    get_database_summary,
    search_deals,
    format_results_for_user,
    get_deals_for_excel,
    export_deals_to_excel,
)

# 1. Understand what is in the database
summary = get_database_summary()
# Agent can read this to the user or reason over it

# 2. Agent gathers a precise set (example: 10 qualified FinTech US deals)
rows = search_deals(
    sector="FinTech",
    geography="United States",
    qualified=True,
    limit=10,
)

# 3. Agent can show the user a readable summary of what it found
print(format_results_for_user(rows))

# 4. Deliver *exactly* those deals as Excel
# style="light" → simple clean table (great when user asked for a specific small set)
# style="full" → rich IB-style comps workbook with stats, parsed multiples, sources, etc.
export_deals_to_excel(
    rows,
    output_path="./my-fintech-10-pts.xlsx",
    title="Selected FinTech Precedent Transactions",
    style="light",          # or "full"
)
```

### Key Functions

- `get_database_summary()` — High-level overview (sectors, years, total qualified deals, etc.)
- `search_deals(...)` — Powerful filtering (sector, geography, qualified, text search, date ranges, limit)
- `format_results_for_user(rows)` — Turns results into readable text for the agent to speak
- `get_deals_for_excel(...)` — One-shot search + conversion to `DealCandidate` objects
- `export_deals_to_excel(deals_or_rows, output_path, title, style="light"|"full")` — The main delivery mechanism

All functions accept an optional `db_path` argument and default to `~/.ptbot/ptbot.db`.

This capability lets agents move beyond running fresh research to intelligently reusing and curating the large body of historical work already stored in the database.
