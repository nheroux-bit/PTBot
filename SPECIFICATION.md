# PTBot — Precedent Transaction Bot SPECIFICATION

PTBot is a two-pass parallel agent pipeline for precedent transaction analysis. It uses Oz local agents to discover M&A deals matching user-defined criteria (sector, geography, time window), filters to only deals with disclosed multiples, then deep-dives on qualified deals with deal-aware agents. Output is a QC-checked precedent transaction analysis in markdown, PDF, and IB-formatted Excel. Installed as a standalone Warp skill at `~/.agents/skills/precedent-transactions/` with a CLI launcher. Built in Python, reusing `run_local_agent()` from attack.market's orchestrator. References: approved implementation plan (Precedent Transaction Analysis Skill), attack.market skill (`~/.agents/skills/attack.market/`), financial-analyst skill (`~/.agents/skills/financial-analyst/`).

## Requirements

### Functional Requirements

- **FR-1**: Pass 1 fan-out spawns 4 source-specialized scouts in parallel (press/news, regulatory filings, deal databases, industry/analyst), each returning structured JSON deal candidates
- **FR-2**: Compile step deduplicates candidates across scouts by matching on target+acquirer name pairs
- **FR-3**: Filter step removes deals where `multiples_disclosed` is false and no multiples are computable from disclosed deal value + financials
- **FR-4**: QC agent enforces: multiples present, geographic accuracy, date accuracy, source attribution on every figure, cross-section consistency
- **FR-5**: CLI accepts `--sector`, `--geography`, `--start-date`, `--end-date` as required parameters
- **FR-6**: CLI accepts optional `--min-multiples`, `--deal-size-min`, `--deal-size-max`, `--output-dir`, `--config-only`, `--timeout`
- **FR-7**: Scout prompts dynamically adjust for geography (region-appropriate sources) and time horizon (quarterly chunking for >6 months)
- **FR-8**: PDF output uses fpdf2 with headers, footers, section breaks, and Unicode sanitization
- **FR-9**: Excel output produces IB-formatted comps workbook with Cover, Comps Table, Benchmarks, and Sources sheets using IB color convention
- **FR-10**: SKILL.md triggers on "precedent transaction", "M&A comps", "deal comps", "transaction multiples", "acquisition research", and related phrases
- **FR-11**: Reference files provide reusable QC criteria template and standard deliverable template
- **FR-12**: Skill installs to `~/.agents/skills/precedent-transactions/` and runs end-to-end via CLI

### Non-Functional Requirements

- **NFR-1**: Per-agent timeout defaults to 900s; pipeline continues with partial results on agent failure (graceful degradation)
- **NFR-2**: Reuses `run_local_agent()` from attack.market — no duplicated agent-spawning logic
- **NFR-3**: Output directory structure is self-contained (all deliverables + supporting files + metadata)
- **NFR-4**: ≥85% test coverage per deft standards

## Architecture

Two-pass fan-out/fan-in pipeline:

```
CLI args → Prompt Builder → Pass 1 (4 scouts parallel)
                               ↓
                          Compile & Filter → qualified_deals.json
                               ↓
                          Pass 2 (3 deep-dive agents parallel, deal-aware)
                               ↓
                          QC Agent → final_deliverable.md
                               ↓
                          PDF Generator → final_deliverable.pdf
                          Excel Generator → precedent_comps.xlsx
```

Key design decision: Pass 2 agents receive the qualified deals manifest from Pass 1, eliminating the cross-agent inconsistency observed in single-pass fan-outs where agents independently discover different deals.

### Dependencies

- `attack.market` orchestrator (`~/.agents/skills/attack.market/scripts/orchestrate.py`) — imported for `run_local_agent()`
- `oz` CLI — spawns local agents
- `fpdf2` — PDF generation
- `openpyxl` — Excel generation

## Phase 1: Core Pipeline

### t1.1.1: Create two_pass_orchestrator.py with Pass 1 fan-out, compile/filter, and Pass 2 fan-out (traces: FR-1, FR-2, FR-3)

Create `scripts/two_pass_orchestrator.py` that imports `run_local_agent` from attack.market's orchestrator and implements the two-pass pipeline. Pass 1 spawns 4 scouts in parallel via `ThreadPoolExecutor`. Each scout returns structured JSON with `{target, acquirer, date, deal_value, multiples_disclosed, source_urls}`. Compile step deduplicates by target+acquirer. Filter keeps only `multiples_disclosed=true`. Writes `qualified_deals.json`. Pass 2 spawns 3 agents with the manifest injected into their prompts.

- Pass 1 spawns 4 scouts in parallel via run_local_agent()
- Compile step deduplicates candidates and filters to deals with multiples_disclosed=true
- Pass 2 spawns 3 agents with qualified_deals.json as prompt context
- All agents complete or gracefully degrade on timeout

### t1.1.2: Implement QC agent stage with precedent-transaction-specific criteria (traces: FR-4)

QC agent receives compiled Pass 2 output plus criteria from `references/qc-criteria.md`. Enforces: multiples present for every deal, geographic accuracy against user's `--geography`, date accuracy against `--start-date`/`--end-date`, source attribution on every financial figure, cross-section consistency (same deal described the same way across agents).

- QC agent produces qc_report.md and final_deliverable.md
- Deals without multiples are excluded from the deliverable (may appear as contextual notes only)

### t1.2.1: Create precedent_txns.py CLI launcher (traces: FR-5, FR-6)

CLI launcher using argparse, modeled on `market_sizing.py`. Parses all arguments, builds scout and deep-dive prompts dynamically, calls `two_pass_orchestrator`. `--config-only` prints config JSON and exits.

- CLI parses all required and optional arguments
- Builds prompts dynamically from parameters
- --config-only prints config JSON and exits without running

### t1.2.2: Implement dynamic prompt generation for geography and time horizon scaling (traces: FR-7)

Scout prompts include geography-appropriate source names (e.g., Orlando Business Journal for Orlando, Crain's Chicago Business for Chicago, Boston Business Journal for Boston). Time horizons >6 months instruct scouts to chunk research by quarter. Pass 2 prompts include full deal names and basic details from `qualified_deals.json`.

- Geography-specific source names in scout prompts
- Quarterly chunking for time horizons >6 months
- Pass 2 prompts are deal-aware

## Phase 2: Output Generation

### t2.1.1: PDF generation with fpdf2 (traces: FR-8)

Implement PDF generation from `final_deliverable.md`. Renders all sections from the deliverable template: executive summary, summary transaction table, detailed deal profiles, comparable multiples context, key takeaways. Unicode characters sanitized for Helvetica encoding. Page headers show report title and date. Page breaks between major sections.

- PDF renders all template sections
- Unicode handled via sanitization
- Page headers, footers, and section breaks

### t2.2.1: IB-formatted Excel comps workbook (traces: FR-9)

Create `scripts/generate_comps_excel.py` using openpyxl. Workbook contains: Cover sheet (title, date, thesis), Comps Table (target, acquirer, date, deal value, EV/Revenue, EV/EBITDA, EV/ARR, P/E, deal structure), Benchmarks sheet (sector-wide multiples for context), Sources sheet. IB color convention: blue (#0070C0) for inputs, black for formulas, green (#00B050) for cross-sheet links. Median/mean rows use Excel formulas, not hardcoded values.

- Cover, Comps Table, Benchmarks, Sources sheets
- IB color convention applied
- Median/mean as formulas

## Phase 3: Skill Packaging

### t3.1.1: Write SKILL.md (traces: FR-10)

SKILL.md frontmatter description triggers on: "precedent transaction", "precedent transactions", "comparable transactions", "comps table", "M&A comps", "deal comps", "transaction multiples", "acquisition research", "who acquired", "recent acquisitions in", "M&A activity in", or any request combining acquisition/M&A + multiples + a sector or geography. Body documents the two-pass pipeline, CLI usage with examples, output structure, and configuration options.

- Trigger description covers all relevant phrases
- Body documents pipeline, CLI, outputs

### t3.1.2: Write reference files (traces: FR-11)

`references/qc-criteria.md` — reusable QC criteria template with `{geography}`, `{start_date}`, `{end_date}`, `{sector}` placeholders. `references/output-template.md` — standard deliverable structure: executive summary, summary transaction table, detailed deal profiles, comparable multiples context, key takeaways for valuation.

- QC criteria template with parameterized placeholders
- Output template defines standard deliverable structure

### t3.2.1: Install and verify (traces: FR-12)

Copy skill directory to `~/.agents/skills/precedent-transactions/`. Verify: `--config-only` runs without errors, full pipeline test completes with at least graceful degradation on all agents, output directory structure matches plan.

- Skill directory matches plan structure
- CLI --config-only works
- Full pipeline completes or gracefully degrades

## Testing Strategy

- Unit tests for prompt generation (geography-specific sources, time horizon chunking)
- Unit tests for compile/filter logic (deduplication, multiples filtering)
- Unit tests for PDF sanitization
- Integration test: `--config-only` produces valid config JSON
- End-to-end test: full pipeline run (may be slow, tagged as integration)
- ≥85% coverage per deft standards

## Deployment

Install to `~/.agents/skills/precedent-transactions/` with this structure:

```
precedent-transactions/
├── SKILL.md
├── scripts/
│   ├── precedent_txns.py
│   ├── two_pass_orchestrator.py
│   └── generate_comps_excel.py
└── references/
    ├── qc-criteria.md
    └── output-template.md
```
