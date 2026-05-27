# Plan: Wiring Precedent Database Query Helpers into the Skill

**Date**: 2026-05 (executed incrementally)
**Context**: After adding core DB query functions (`search_deals`, `summarize_database`, etc.) and flexible Excel export (`generate_comps_excel_from_deals` with light/full styles) to the main `ptbot` package, we need to make these capabilities easily usable by Oz/Warp agents through the `precedent-transactions` skill.

## Goals
- Give agents first-class access to explore the historical deal database.
- Allow agents to make precise selections and deliver exactly the requested deals as Excel (supporting both rich and light output styles).
- Follow the existing skill wrapper pattern for consistency.
- Keep the API ergonomic for agents (one high-level function for the most common case).

## Decisions Made
- **Interface priority**: Direct Python functions (via skill wrappers) are primary. CLI can come later.
- **Exploration**: Structured data + a `format_results_for_user()` helper so agents can both parse and speak results.
- **Excel styles**: Support both `"full"` (existing rich IB comps) and `"light"` (simple table) as requested.
- **Highest-leverage addition**: A single `query_and_export_excel(...)` convenience function.

## Execution Steps Completed

1. **Core package enhancements** (in `src/ptbot/`):
   - Added `search_deals`, `summarize_database`, `format_search_results_for_agent`, `row_to_deal_candidate` in `db.py`.
   - Added `generate_comps_excel_from_deals(..., style="light"|"full")` in `excel.py`.

2. **Skill wiring** (`skill/scripts/`):
   - Created `precedent_database.py` following the exact pattern of `two_pass_orchestrator.py` and `generate_comps_excel.py`.
   - Re-exports and wraps the new functions with sensible defaults.
   - Added the high-level `query_and_export_excel(...)` one-shot helper (search → convert → Excel in one call).
   - Updated `generate_comps_excel.py` to also expose the new `generate_comps_excel_from_deals`.

3. **Documentation**:
   - Significantly expanded `skill/SKILL.md` with a new "## Querying the Historical Deal Database" section, including concrete agent usage examples.

## Recommended Next Steps (in priority order)

1. **Agent testing** — Have a real agent exercise the new functions (especially `query_and_export_excel` + the two Excel styles).
2. **CLI surface** (optional but useful for humans) — Add `ptbot query deals ... --format excel --style light` on top of the same backend.
3. **Tests** — Add tests for the new `precedent_database.py` wrapper and the high-level functions (can live in the main test suite or skill-specific).
4. **Skill manifest update** — Consider whether the top-level skill description in `SKILL.md` should mention the database querying capability.
5. **Feedback loop** — Collect real usage patterns from agents and refine (e.g. more summary helpers, better default titles, etc.).

## Files Changed / Added
- `src/ptbot/db.py` (new query helpers)
- `src/ptbot/excel.py` (flexible Excel generation)
- `skill/scripts/precedent_database.py` (new — main wiring)
- `skill/scripts/generate_comps_excel.py` (minor update)
- `skill/SKILL.md` (documentation)

## Success Criteria
- An agent can say “Show me what FinTech deals we have and give me the top 10 qualified ones as a light Excel” and successfully receive exactly that file with no extra manual steps.

This integration turns the historical database from a passive store into an active, agent-usable asset.
