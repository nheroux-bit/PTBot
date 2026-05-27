#!/usr/bin/env python3
"""
Precedent Database helpers for agents.

This module exposes the historical deal database querying capabilities
so that Oz/Warp agents can:
- Explore and summarize what precedent transactions already exist in the DB
- Search and filter deals with precise criteria
- Convert results into DealCandidate objects
- Generate Excel output (full rich comps workbook or lighter simple table)
  containing *exactly* the deals the agent selected.

Usage from an agent:

    from skill.scripts.precedent_database import (
        get_database_summary,
        search_deals,
        format_results_for_user,
        get_deals_for_excel,
        export_deals_to_excel,
    )

    # 1. Let the agent understand what's available
    summary = get_database_summary()
    print(summary)

    # 2. Agent makes a precise selection
    rows = search_deals(sector="FinTech", geography="United States", qualified=True, limit=10)

    # 3. Agent can show the user a readable summary
    print(format_results_for_user(rows))

    # 4. Deliver exactly those deals as Excel (light or full style)
    export_deals_to_excel(
        rows,
        output_path="./fintech-10-pts.xlsx",
        title="Selected FinTech Precedents",
        style="light",          # or "full"
    )
"""

from __future__ import annotations

from _bootstrap import ensure_ptbot_importable

ensure_ptbot_importable()

from pathlib import Path
from typing import Any

from ptbot.db import (
    format_search_results_for_agent,
    open_db,
    row_to_deal_candidate,
    search_deals as _search_deals,
    summarize_database,
)
from ptbot.excel import generate_comps_excel_from_deals
from ptbot.models import DealCandidate

__all__ = [
    "get_database_summary",
    "search_deals",
    "format_results_for_user",
    "row_to_deal_candidate",
    "convert_rows_to_deals",
    "get_deals_for_excel",
    "export_deals_to_excel",
]


_DEFAULT_DB_PATH = Path("~/.ptbot/ptbot.db").expanduser()


def get_database_summary(db_path: str | Path | None = None) -> dict[str, Any]:
    """
    Return a high-level summary of the precedent transaction database.

    Ideal for agents to first understand what data is available before
    making specific queries.

    Returns counts, sectors covered, years covered, etc.
    """
    path = Path(db_path).expanduser() if db_path else _DEFAULT_DB_PATH
    conn = open_db(path)
    try:
        return summarize_database(conn)
    finally:
        conn.close()


def search_deals(
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = True,
    target_search: str | None = None,
    acquirer_search: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    limit: int | None = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Search the historical deal database with flexible filters.

    This is the primary tool agents should use to gather specific precedent
    transactions.

    Returns list of raw rows (with sector/geography joined). Use
    `convert_rows_to_deals()` or `get_deals_for_excel()` to turn them into
    objects suitable for Excel generation.
    """
    path = Path(db_path).expanduser() if db_path else _DEFAULT_DB_PATH
    conn = open_db(path)
    try:
        return _search_deals(
            conn,
            sector=sector,
            geography=geography,
            qualified=qualified,
            target_search=target_search,
            acquirer_search=acquirer_search,
            min_date=min_date,
            max_date=max_date,
            limit=limit,
        )
    finally:
        conn.close()


def format_results_for_user(results: list[dict[str, Any]], max_items: int = 15) -> str:
    """
    Convert search results into clean, readable text suitable for an agent
    to present to the user.
    """
    return format_search_results_for_agent(results, max_items=max_items)


def convert_rows_to_deals(rows: list[dict[str, Any]]) -> list[DealCandidate]:
    """Convert database rows into proper DealCandidate objects."""
    return [row_to_deal_candidate(row) for row in rows]


def get_deals_for_excel(
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = True,
    target_search: str | None = None,
    acquirer_search: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    limit: int | None = None,
    db_path: str | Path | None = None,
) -> list[DealCandidate]:
    """
    Convenience function: search the database and return ready-to-use
    DealCandidate objects for Excel generation.

    This is often the most direct path when an agent has decided on a
    specific set of deals it wants to deliver.
    """
    rows = search_deals(
        sector=sector,
        geography=geography,
        qualified=qualified,
        target_search=target_search,
        acquirer_search=acquirer_search,
        min_date=min_date,
        max_date=max_date,
        limit=limit,
        db_path=db_path,
    )
    return convert_rows_to_deals(rows)


def export_deals_to_excel(
    deals_or_rows: list[DealCandidate] | list[dict[str, Any]],
    output_path: str | Path,
    title: str,
    *,
    style: str = "light",   # "light" or "full"
) -> Path:
    """
    Take a list of deals (or raw search result rows) and write them to
    a precedent comps Excel file.

    - style="light": Clean, simple single-sheet table (recommended when the
      user/agent asked for a precise small number of specific deals).
    - style="full": Full rich IB-style comps workbook with stats, multiple
      parsing, sources sheet, etc.

    Returns the Path to the written Excel file.
    """
    output = Path(output_path).expanduser()

    if deals_or_rows and isinstance(deals_or_rows[0], dict):
        # We received raw rows — convert them
        deals = convert_rows_to_deals(deals_or_rows)  # type: ignore[arg-type]
    else:
        deals = deals_or_rows  # type: ignore[assignment]

    generate_comps_excel_from_deals(deals, output, title, style=style)
    return output


# ---------------------------------------------------------------------------
# Highest-level convenience for agents (very common pattern)
# ---------------------------------------------------------------------------


def query_and_export_excel(
    *,
    sector: str | None = None,
    geography: str | None = None,
    qualified: bool | None = True,
    target_search: str | None = None,
    acquirer_search: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    limit: int | None = 20,
    output_path: str | Path = "./precedent-selection.xlsx",
    title: str | None = None,
    style: str = "light",
    db_path: str | Path | None = None,
) -> Path:
    """
    One-shot helper: search the database with criteria and immediately write
    the results to an Excel file.

    This is the most agent-friendly entry point for the common case:
    "Gather X deals matching these filters and give me an Excel file with exactly those."

    Returns the path to the generated Excel file.
    """
    rows = search_deals(
        sector=sector,
        geography=geography,
        qualified=qualified,
        target_search=target_search,
        acquirer_search=acquirer_search,
        min_date=min_date,
        max_date=max_date,
        limit=limit,
        db_path=db_path,
    )

    if not title:
        parts = []
        if sector:
            parts.append(sector)
        if geography:
            parts.append(geography)
        title = "Selected Precedent Transactions" + (f" ({', '.join(parts)})" if parts else "")

    return export_deals_to_excel(
        rows,
        output_path=output_path,
        title=title,
        style=style,
    )
