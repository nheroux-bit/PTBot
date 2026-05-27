"""Command line interface for PTBot."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .excel import generate_comps_excel
from .models import ResearchParams
from .orchestrator import run_pipeline
from .pdf import markdown_to_pdf
from .prompt_builder import build_config


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
        "--max-cost",
        type=float,
        default=None,
        metavar="USD",
        help=(
            "Soft budget warning: emit warning if estimated cost exceeds "
            "this USD value (cost-accounting-001)"
        ),
    )
    parser.add_argument(
        "--config-only", action="store_true", help="Print generated config and exit"
    )
    # Human feedback (quality-signals-001) — lightweight CLI path alongside dashboard
    parser.add_argument(
        "--feedback-deal-id", default=None, help="Deal ID to attach human override to"
    )
    parser.add_argument("--feedback-confidence", choices=["HIGH", "MEDIUM", "LOW"], default=None)
    parser.add_argument("--feedback-notes", default=None, help="Human rationale for override")
    parser.add_argument("--feedback-reviewer", default="cli-user")
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

    if args.feedback_deal_id:
        # Lightweight human feedback path (quality-signals-001)
        if not args.db_path:
            print(
                "ERROR: --db-path is required when using --feedback-deal-id",
                file=__import__("sys").stderr,
            )
            return 2
        import sqlite3

        payload: dict[str, object] = {}
        if args.feedback_confidence:
            payload["human_confidence_override"] = args.feedback_confidence
        if args.feedback_notes:
            payload["human_notes"] = args.feedback_notes
        payload["reviewer"] = args.feedback_reviewer or "cli-user"
        payload["reviewed_at"] = datetime.now(UTC).isoformat()

        conn = sqlite3.connect(Path(args.db_path).expanduser())
        conn.execute(
            "UPDATE deals SET quality_signals = ? WHERE deal_id = ?",
            (json.dumps(payload), args.feedback_deal_id),
        )
        conn.commit()
        conn.close()
        print(f"Feedback recorded for deal {args.feedback_deal_id}")
        return 0

    if args.config_only:
        print(json.dumps(build_config(params), indent=2))
        return 0

    output_dir = Path(args.output_dir)
    db_path = Path(args.db_path) if args.db_path else None
    paths = run_pipeline(
        params, output_dir, timeout=args.timeout, db_path=db_path, max_cost=args.max_cost
    )
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
