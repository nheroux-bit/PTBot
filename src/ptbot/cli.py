"""Command line interface for PTBot."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from .excel import generate_comps_excel
from .models import ResearchParams
from .orchestrator import run_pipeline
from .pdf import markdown_to_pdf
from .prompt_builder import build_config


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format headers + rows as a plain-text table (no external deps)."""
    if not rows:
        return "  (no records)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    sep = "  ".join("-" * w for w in col_widths)
    hdr = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    lines = [hdr, sep]
    for row in rows:
        lines.append("  ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(row)))
    return "\n".join(lines)


def _open_db_or_exit(db_path: Path) -> sqlite3.Connection:
    """Open the deal database, printing a friendly error if absent."""
    from . import db as _db

    if not db_path.exists():
        print(
            f"Database not found: {db_path}\n"
            "Run ptbot with --db-path to create it, or point --db-path at an existing file.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return _db.open_db(db_path)


def _handle_query_command(argv: Sequence[str]) -> int:  # noqa: C901 — intentionally long handler
    """Handle ptbot query runs / deals / export."""
    from . import db as _db

    parser = argparse.ArgumentParser(
        prog="ptbot query",
        description="Explore and export the local PTBot deal database.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the SQLite database (default: ~/.ptbot/ptbot.db)",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # ---- runs ---------------------------------------------------------------
    runs_p = sub.add_parser("runs", help="List pipeline runs in the database")
    runs_p.add_argument(
        "--db-path", default=None, help="Path to the SQLite database (default: ~/.ptbot/ptbot.db)"
    )
    runs_p.add_argument(
        "--limit", type=int, default=20, help="Maximum number of runs to show (default: 20)"
    )
    runs_p.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help="Only show runs on or after DATE (YYYY-MM-DD)",
    )
    runs_p.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # ---- deals --------------------------------------------------------------
    deals_p = sub.add_parser("deals", help="Search deals across all runs")
    deals_p.add_argument(
        "--db-path", default=None, help="Path to the SQLite database (default: ~/.ptbot/ptbot.db)"
    )
    deals_p.add_argument("--sector", default=None, help="Filter by sector (exact match)")
    deals_p.add_argument("--geography", default=None, help="Filter by geography (exact match)")
    deals_p.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help="Only show deals on or after DATE (YYYY-MM-DD)",
    )
    deals_p.add_argument(
        "--qualified-only",
        action="store_true",
        help="Only show qualified deals (have disclosed standard multiples)",
    )
    deals_p.add_argument(
        "--limit", type=int, default=50, help="Maximum number of deals to show (default: 50)"
    )
    deals_p.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # ---- export -------------------------------------------------------------
    export_p = sub.add_parser("export", help="Export deals to CSV or JSON")
    export_p.add_argument(
        "--db-path", default=None, help="Path to the SQLite database (default: ~/.ptbot/ptbot.db)"
    )
    export_p.add_argument("--sector", default=None, help="Filter by sector")
    export_p.add_argument("--geography", default=None, help="Filter by geography")
    export_p.add_argument(
        "--qualified-only",
        action="store_true",
        help="Only export qualified deals",
    )
    export_p.add_argument(
        "--limit", type=int, default=None, help="Maximum number of deals to export (default: all)"
    )
    export_p.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Export format (default: csv)",
    )
    export_p.add_argument(
        "--output",
        default="-",
        metavar="FILE",
        help="Output file path (default: stdout)",
    )

    # Normalise "query:runs" → "query runs" etc.
    argv_list = list(argv)
    if argv_list and ":" in argv_list[0]:
        sub_name = argv_list[0].split(":", 1)[1]
        argv_list = ["query", sub_name] + argv_list[1:]

    args = parser.parse_args(argv_list[1:] if argv_list and argv_list[0] == "query" else argv_list)

    db_path = (
        Path(args.db_path).expanduser() if getattr(args, "db_path", None) else _default_db_path()
    )

    # ---- dispatch -----------------------------------------------------------
    if args.subcommand == "runs":
        conn = _open_db_or_exit(db_path)
        try:
            runs = _db.list_runs_with_stats(conn, since=args.since, limit=args.limit)
        finally:
            conn.close()
        if args.format == "json":
            print(json.dumps(runs, indent=2))
            return 0
        if not runs:
            print("No runs found.")
            return 0
        headers = ["run_id", "sector", "geography", "period", "deals", "qualified"]
        table_rows = [
            [
                r["run_id"][:12] + "...",
                str(r.get("sector") or ""),
                str(r.get("geography") or ""),
                f"{r.get('start_date','?')} \u2013 {r.get('end_date','?')}",
                str(r.get("total_deals", 0)),
                str(r.get("qualified_deals") or 0),
            ]
            for r in runs
        ]
        print(f"Runs in {db_path} (newest first, limit={args.limit}):")
        print(_fmt_table(headers, table_rows))
        return 0

    if args.subcommand == "deals":
        conn = _open_db_or_exit(db_path)
        try:
            rows = _db.search_deals(
                conn,
                sector=args.sector,
                geography=args.geography,
                min_date=args.since,
                qualified=True if args.qualified_only else None,
                limit=args.limit,
            )
        finally:
            conn.close()
        if not rows:
            print("No deals found matching the given filters.")
            return 0
        if args.format == "json":
            # Omit bulky internal fields for readability
            out = [
                {
                    "target": r["target"],
                    "acquirer": r["acquirer"],
                    "date": r.get("date"),
                    "deal_value": r.get("deal_value"),
                    "sector": r.get("sector"),
                    "geography": r.get("geography"),
                    "qualified": bool(r.get("qualified")),
                    "multiples": _safe_load_json_list(r.get("multiples")),
                }
                for r in rows
            ]
            print(json.dumps(out, indent=2))
        else:
            headers = ["target", "acquirer", "date", "deal_value", "sector", "Q?"]
            table_rows = [
                [
                    _truncate(r["target"], 28),
                    _truncate(r["acquirer"], 22),
                    str(r.get("date") or ""),
                    _truncate(str(r.get("deal_value") or ""), 12),
                    _truncate(str(r.get("sector") or ""), 16),
                    "Y" if r.get("qualified") else "N",
                ]
                for r in rows
            ]
            filters = ", ".join(
                f"{k}={v}"
                for k, v in [
                    ("sector", args.sector),
                    ("geography", args.geography),
                    ("since", args.since),
                    ("qualified_only", args.qualified_only or None),
                ]
                if v
            )
            print(f"Deals ({len(rows)} shown{', ' + filters if filters else ''}):")
            print(_fmt_table(headers, table_rows))
        return 0

    if args.subcommand == "export":
        conn = _open_db_or_exit(db_path)
        try:
            rows = _db.search_deals(
                conn,
                sector=args.sector,
                geography=args.geography,
                qualified=True if args.qualified_only else None,
                limit=args.limit,
            )
        finally:
            conn.close()

        export_cols = [
            "target",
            "acquirer",
            "date",
            "deal_value",
            "sector",
            "geography",
            "qualified",
            "multiples",
        ]
        export_rows = [
            {
                "target": r["target"],
                "acquirer": r["acquirer"],
                "date": r.get("date") or "",
                "deal_value": r.get("deal_value") or "",
                "sector": r.get("sector") or "",
                "geography": r.get("geography") or "",
                "qualified": "true" if r.get("qualified") else "false",
                "multiples": "; ".join(_safe_load_json_list(r.get("multiples"))),
            }
            for r in rows
        ]

        out_path = args.output
        if args.format == "json":
            content = json.dumps(export_rows, indent=2)
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=export_cols)
            writer.writeheader()
            writer.writerows(export_rows)
            content = buf.getvalue()

        if out_path == "-":
            print(content, end="")
        else:
            Path(out_path).write_text(content, encoding="utf-8")
            print(f"Exported {len(rows)} deals to {out_path}")
        return 0

    return 1


def _safe_load_json_list(value: object) -> list[str]:
    """Parse a JSON-encoded list from a DB cell, returning [] on failure."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        loaded = json.loads(str(value))
        return [str(v) for v in loaded] if isinstance(loaded, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _truncate(s: str, n: int) -> str:
    """Truncate a string to n characters, adding an ellipsis if needed."""
    return s if len(s) <= n else s[: n - 1] + "…"


def _handle_sweep_auto_command(argv: Sequence[str]) -> int:
    """Handle ptbot sweep:auto — TOML-free parallel cloud sweep orchestrator.

    Builds a SweepConfig on-the-fly from CLI flags and calls run_sweep() with
    cloud=True so every pipeline task is dispatched as an oz agent run-cloud.
    The existing ThreadPoolExecutor inside run_sweep() handles parallelism.
    """
    from .sweep import MarketTarget, SweepConfig, SweepSettings, run_sweep

    parser = argparse.ArgumentParser(
        prog="ptbot sweep:auto",
        description=(
            "Auto-populate the deal database by sweeping one or more sectors "
            "over annual windows using parallel cloud agents. No TOML config needed."
        ),
    )
    parser.add_argument(
        "--sectors",
        required=True,
        help="Comma-separated list of sectors/industries to sweep (e.g. 'FinTech,HealthTech')",
    )
    parser.add_argument(
        "--geography",
        required=True,
        help="Geographic scope applied to all sectors (e.g. 'United States')",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Number of calendar years to look back (default: 5)",
    )
    parser.add_argument(
        "--environment",
        default=None,
        metavar="ENV_ID",
        help="Oz cloud environment ID (required for cloud dispatch; local agents used if omitted)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database path (default: ~/.ptbot/ptbot.db)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel agent dispatches (default: 4)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Per-pipeline agent timeout in seconds (default: 900)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned runs without invoking any agents",
    )

    # Accept both 'sweep:auto' and bare argv slice
    argv_list = list(argv)
    parse_from = argv_list[1:] if argv_list and argv_list[0].startswith("sweep") else argv_list
    args = parser.parse_args(parse_from)

    # Parse comma-separated sectors, stripping whitespace
    sectors = [s.strip() for s in args.sectors.split(",") if s.strip()]
    if not sectors:
        print("error: --sectors must contain at least one non-empty sector", file=sys.stderr)
        return 1

    db_path = Path(args.db_path).expanduser() if args.db_path else _default_db_path()

    # Build SweepConfig programmatically — no TOML file needed
    settings = SweepSettings(
        years_back=args.years,
        db_path=str(db_path),
        max_workers=args.max_workers,
        timeout=args.timeout,
        cloud_environment=args.environment,
    )
    markets = [MarketTarget(sector=s, geography=args.geography) for s in sectors]
    config = SweepConfig(sweep=settings, markets=markets)

    use_cloud = args.environment is not None
    mode = "cloud" if use_cloud else "local"
    print(
        f"[sweep:auto] {len(sectors)} sector(s) × {args.geography} | "
        f"years_back={args.years} | mode={mode} | max_workers={args.max_workers}"
    )
    if not use_cloud:
        print(
            "[sweep:auto] note: no --environment given; running local agents. "
            "Pass --environment <env_id> to dispatch cloud agents."
        )

    run_sweep(
        config,
        dry_run=args.dry_run,
        db_path_override=db_path,
        cloud=use_cloud,
        cloud_environment=args.environment,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the PTBot argument parser.

    Supports the original flat flags for a single pipeline run, plus the
    cloud-control-001 subcommands:
        ptbot cloud status [--db-path ...] [--all]
        ptbot cloud kill <oz-run-id> [--db-path ...]
    The colon form "cloud:status" / "cloud:kill" is also accepted for
    symmetry with other namespaced tooling.
    """
    parser = argparse.ArgumentParser(description="Run precedent transaction research.")
    parser.add_argument(
        "--sector",
        "--industry",
        dest="sector",
        required=True,
        help="Sector or industry vertical",
    )
    parser.add_argument("--geography", required=True, help="Geographic scope")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--min-multiples", type=int, default=1, help="Minimum multiples required")
    parser.add_argument("--deal-size-min", default=None, help="Minimum deal size filter")
    parser.add_argument("--deal-size-max", default=None, help="Maximum deal size filter")
    parser.add_argument("--output-dir", default="./precedent-txn-output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=900, help="Per-agent timeout in seconds")
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite database path (e.g. ~/.ptbot/ptbot.db). Omit to skip persistence.",
    )
    parser.add_argument(
        "--config-only", action="store_true", help="Print generated config and exit"
    )
    return parser


def _default_db_path() -> Path:
    return Path("~/.ptbot/ptbot.db").expanduser()


def _handle_cloud_command(argv: Sequence[str]) -> int:
    """Handle ptbot cloud status / kill (and cloud:status / cloud:kill forms)."""
    from . import db as _db
    from .runners import kill_cloud_run

    parser = argparse.ArgumentParser(
        prog="ptbot cloud", description="Cloud execution control plane (revocation & status)."
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Database containing the cloud_runs registry (default: ~/.ptbot/ptbot.db)",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    status_p = sub.add_parser("status", help="List cloud runs (active by default)")
    status_p.add_argument(
        "--all", action="store_true", help="Include terminal (completed/revoked) runs"
    )

    kill_p = sub.add_parser("kill", help="Revoke/kill a cloud Oz run by its run_id")
    kill_p.add_argument("run_id", help="The oz run_id from a prior cloud dispatch (or run_url)")
    kill_p.add_argument(
        "--force",
        action="store_true",
        help="Mark revoked in registry even if oz kill command fails",
    )

    # Support "cloud:status" as argv[0] too
    args = parser.parse_args(argv[1:] if argv and argv[0].startswith("cloud") else argv)

    db_path = (
        Path(args.db_path).expanduser() if getattr(args, "db_path", None) else _default_db_path()
    )
    conn = _db.open_db(db_path)

    if args.subcommand in ("status", None):  # direct status?
        active_only = not getattr(args, "all", False)
        runs = _db.list_cloud_runs(conn, active_only=active_only)
        if not runs:
            print("No cloud runs recorded in registry.")
            conn.close()
            return 0
        print(f"Cloud runs in {db_path} ({'active only' if active_only else 'all'}):")
        for r in runs:
            age = ""
            if r.get("dispatched_at"):
                try:
                    from datetime import UTC, datetime

                    disp = datetime.fromisoformat(r["dispatched_at"].replace("Z", "+00:00"))
                    delta = (datetime.now(UTC) - disp).total_seconds()
                    age = (
                        f" ({int(delta//60)}m ago)"
                        if delta < 86400
                        else f" ({int(delta//3600)}h ago)"
                    )
                except Exception:
                    pass
            cost = (
                f" cost~${r['cost_estimate_usd']:.2f}"
                if r.get("cost_estimate_usd") is not None
                else ""
            )
            print(
                f"  {r['oz_run_id'][:12]}...  status={r['status']}{age}{cost}\n"
                f"    parent={r.get('parent','') } env={r.get('environment','')}\n"
                f"    url={r.get('run_url','')}"
            )
        conn.close()
        return 0

    if args.subcommand == "kill":
        rid = args.run_id.strip()
        rec = _db.get_cloud_run(conn, rid)
        if rec is None:
            # Try prefix match for convenience
            all_runs = _db.list_cloud_runs(conn, active_only=False)
            matches = [
                r for r in all_runs if r["oz_run_id"].startswith(rid) or rid in r.get("run_url", "")
            ]
            if len(matches) == 1:
                rec = matches[0]
                rid = rec["oz_run_id"]
            elif len(matches) > 1:
                print("Ambiguous run_id prefix; be more specific.")
                conn.close()
                return 1
        if rec is None:
            print(f"No registry entry for {rid}. (Has it been launched via this DB?)")
            conn.close()
            return 1

        print(f"Attempting revocation of {rid} (current status: {rec.get('status')}) ...")
        success, msg = kill_cloud_run(rid, rec.get("run_url", ""))
        print(msg)
        if success or getattr(args, "force", False):
            _db.mark_cloud_run_revoked(conn, rid)
            print(f"Registry marked 'revoked' for {rid}.")
        else:
            print("Registry left unchanged (use --force to mark anyway).")
        conn.close()
        return 0 if success else 2

    conn.close()
    return 1


def params_from_args(args: argparse.Namespace) -> ResearchParams:
    """Create validated research params from parsed args."""
    return ResearchParams(
        sector=args.sector,
        geography=args.geography,
        start_date=args.start_date,
        end_date=args.end_date,
        min_multiples=args.min_multiples,
        deal_size_min=args.deal_size_min,
        deal_size_max=args.deal_size_max,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the PTBot CLI.

    Cloud control plane commands (cloud-control-001) are dispatched early
    so that "ptbot cloud status" and "ptbot cloud kill <id>" (or the
    cloud:status / cloud:kill spellings) work without requiring the
    full single-run flag set.
    """
    raw_argv: list[str] = list(argv) if argv is not None else sys.argv[1:]

    # Early dispatch for sweep:auto
    if raw_argv and raw_argv[0] == "sweep:auto":
        return _handle_sweep_auto_command(raw_argv)

    # Early dispatch for query subcommand
    if raw_argv and (raw_argv[0] == "query" or raw_argv[0].startswith("query:")):
        return _handle_query_command(raw_argv)

    # Early dispatch for cloud control plane (does not consume the run parser)
    if (
        raw_argv
        and raw_argv[0] in {"cloud", "cloud:status", "cloud:kill"}
        or (raw_argv and raw_argv[0].startswith("cloud:"))
    ):
        # normalise "cloud:xxx" -> cloud subcommand; keep --db-path before sub for argparse
        if raw_argv[0].startswith("cloud:"):
            sub = raw_argv[0].split(":", 1)[1]
            # Reorder so --db-path (if present) comes before the subcommand name
            rest = raw_argv[1:]
            if "--db-path" in rest:
                idx = rest.index("--db-path")
                if idx + 1 < len(rest):
                    db_val = rest[idx + 1]
                    raw_argv = ["cloud", "--db-path", db_val, sub] + [
                        x for i, x in enumerate(rest) if i not in (idx, idx + 1)
                    ]
                else:
                    raw_argv = ["cloud", sub] + rest
            else:
                raw_argv = ["cloud", sub] + rest
        return _handle_cloud_command(raw_argv)

    parser = build_parser()
    args = parser.parse_args(raw_argv)
    params = params_from_args(args)

    if args.config_only:
        print(json.dumps(build_config(params), indent=2))
        return 0

    output_dir = Path(args.output_dir)
    db_path = Path(args.db_path) if args.db_path else None
    paths = run_pipeline(params, output_dir, timeout=args.timeout, db_path=db_path)
    markdown_to_pdf(
        paths.final_markdown, paths.final_pdf, f"{params.sector} Precedent Transactions"
    )
    generate_comps_excel(paths.qualified_deals, paths.comps_excel, f"{params.sector} Comps")
    print(f"Final deliverable: {paths.final_markdown}")
    print(f"PDF: {paths.final_pdf}")
    print(f"Excel: {paths.comps_excel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
