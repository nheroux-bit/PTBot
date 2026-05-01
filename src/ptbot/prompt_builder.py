"""Prompt generation for PTBot's two-pass research pipeline."""

from __future__ import annotations

import json
from datetime import date

from .models import AgentTask, DealCandidate, ResearchParams


def source_hints_for_geography(geography: str) -> str:
    """Return geography-specific source hints for scout prompts."""
    geo = geography.lower()
    if "orlando" in geo or "central florida" in geo:
        return "Orlando Business Journal, Orlando Sentinel, UCF incubator news, Florida Trend"
    if "chicago" in geo:
        return "Crain's Chicago Business, Chicago Tribune business, Built In Chicago"
    if "boston" in geo:
        return "Boston Business Journal, Boston Globe business, MassBio, BostInno"
    if "new york" in geo or "nyc" in geo:
        return "Crain's New York Business, NY Business Journal, Built In NYC"
    if "bay area" in geo or "san francisco" in geo or "silicon valley" in geo:
        return "San Francisco Business Times, Silicon Valley Business Journal, The Information"
    if "florida" in geo:
        return "Florida Trend, local Florida business journals, Orlando/Tampa/Miami business press"
    return "local business journals, regional tech publications, chamber of commerce news"


def horizon_instruction(start_date: str, end_date: str) -> str:
    """Return time-horizon instructions, including quarterly chunking for wider windows."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if months > 6:
        return (
            "The requested time horizon is wider than 6 months. Chunk the search by calendar "
            "quarter and explicitly note which quarters were searched."
        )
    return "The requested time horizon is narrow. Search the full window directly."


def build_pass1_tasks(params: ResearchParams) -> list[AgentTask]:
    """Build the four source-specialized Pass 1 scout prompts."""
    scope = (
        f"Sector: {params.sector}; Geography: {params.geography}; "
        f"Date window: {params.start_date} to {params.end_date}; "
        f"Minimum multiples required: {params.min_multiples}."
    )
    size_filter = ""
    if params.deal_size_min or params.deal_size_max:
        size_filter = (
            f" Deal size filter: min={params.deal_size_min or 'none'}, "
            f"max={params.deal_size_max or 'none'}."
        )
    common = (
        f"{scope}{size_filter}\n"
        f"{horizon_instruction(params.start_date, params.end_date)}\n"
        "Return ONLY a JSON array. Each item must include: target, acquirer, date, "
        "deal_value, multiples_disclosed, computed_multiples_available, multiples, source_urls. "
        "Only include acquisitions or majority-control transactions. If no deals are found, "
        "return an empty JSON array."
    )
    source_hints = source_hints_for_geography(params.geography)
    scouts = [
        (
            "press_news",
            "Press & News Scout",
            "Search press releases and news sources including TechCrunch, Reuters, Bloomberg, "
            f"financial news, and regional sources: {source_hints}.",
        ),
        (
            "regulatory_filings",
            "Regulatory Filings Scout",
            "Search SEC EDGAR (8-K, S-4, DEFM14A), UK RNS/Investegate, investor relations "
            "filings, and international equivalents for transaction terms.",
        ),
        (
            "deal_databases",
            "Deal Databases Scout",
            "Search Crunchbase, PitchBook summaries, Mergr, PrivSource, CB Insights, Tracxn, "
            "and comparable deal databases or database summaries.",
        ),
        (
            "industry_analyst",
            "Industry & Analyst Scout",
            "Search analyst reports, earnings call transcripts, industry publications, VC/PE "
            "firm announcements, and sector newsletters.",
        ),
    ]
    return [
        AgentTask(
            id=scout_id,
            label=label,
            prompt=(
                f"SCOUT_ID: {scout_id}\n"
                "You are a precedent transaction discovery scout.\n"
                f"{prompt}\n{common}"
            ),
        )
        for scout_id, label, prompt in scouts
    ]


def build_pass2_tasks(params: ResearchParams, deals: list[DealCandidate]) -> list[AgentTask]:
    """Build deal-aware Pass 2 deep-dive prompts."""
    manifest = json.dumps([deal.model_dump(mode="json") for deal in deals], indent=2)
    common = (
        f"Research scope: {params.sector} acquisitions in {params.geography} from "
        f"{params.start_date} to {params.end_date}.\n"
        f"Qualified deal manifest:\n{manifest}\n"
        "Only research deals in this manifest. If a deal appears to fail the scope, flag it "
        "rather than silently replacing it."
    )
    tasks = [
        (
            "target_terms",
            "Target & Terms Deep Dive",
            "For each deal, compile target profile and full transaction terms: deal value, "
            "EV/Revenue, EV/EBITDA, EV/ARR, P/E, earn-outs, structure, premium, "
            "and source URLs.",
        ),
        (
            "acquirer_rationale",
            "Acquirer & Rationale Deep Dive",
            "For each deal, profile the acquirer, strategic rationale, prior M&A, analyst "
            "commentary, synergies, integration plan, and regulatory considerations.",
        ),
        (
            "comparable_benchmarks",
            "Comparable Benchmarks Deep Dive",
            "Research sector-wide M&A multiples for the same sector and period, including "
            "median/mean EV/Revenue, EV/ARR, EV/EBITDA, premium/discount context, and sources.",
        ),
    ]
    return [
        AgentTask(
            id=task_id,
            label=label,
            prompt=(
                f"DEEP_DIVE_ID: {task_id}\n"
                "You are a precedent transaction analyst.\n"
                f"{body}\n{common}"
            ),
        )
        for task_id, label, body in tasks
    ]


def build_qc_prompt(params: ResearchParams, compiled_deep_dive: str) -> str:
    """Build the QC prompt for the final precedent transaction deliverable."""
    return f"""You are a quality-checking agent for a precedent transaction analysis.

Research scope:
- Sector: {params.sector}
- Geography: {params.geography}
- Date window: {params.start_date} to {params.end_date}
- Minimum disclosed/computable multiples per included deal: {params.min_multiples}

Check every included deal for:
1. Multiples requirement: each included transaction must have at least one explicitly stated
   or reliably computable valuation multiple.
2. Geographic accuracy: target company must fit the requested geography unless clearly labeled
   as a near-miss.
3. Date accuracy: announcement or close date must fall inside the requested date window unless
   clearly labeled as a near-miss.
4. Source attribution: every financial figure and multiple must include a source URL or filing
   reference.
5. Cross-section consistency: target, acquirer, dates, values, and multiples must match across
   sections.

Produce a polished markdown report with:
- Executive Summary
- Summary Transaction Table
- Detailed Deal Profiles
- Comparable Multiples Context
- Key Takeaways for Valuation

Compiled findings:
{compiled_deep_dive}
"""


def build_config(params: ResearchParams) -> dict[str, object]:
    """Build a serializable config preview for --config-only mode."""
    return {
        "project_name": f"precedent-transactions-{params.sector.lower().replace(' ', '-')}",
        "params": params.model_dump(mode="json"),
        "pass1_tasks": [task.model_dump(mode="json") for task in build_pass1_tasks(params)],
        "pass2_tasks": "Generated after qualified_deals.json is built from Pass 1.",
        "outputs": [
            "final_deliverable.md",
            "final_deliverable.pdf",
            "precedent_comps.xlsx",
            "supporting/qualified_deals.json",
        ],
    }
