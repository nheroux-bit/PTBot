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
