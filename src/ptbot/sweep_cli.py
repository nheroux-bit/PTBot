"""Command line interface for the PTBot sweep runner."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .sweep import load_config, run_sweep


def build_parser() -> argparse.ArgumentParser:
    """Build the ptbot-sweep argument parser."""
    parser = argparse.ArgumentParser(
        prog="ptbot-sweep",
        description=(
            "Sweep a set of markets over annual windows, "
            "persisting results to a SQLite database. "
            "Combinations already in the database are skipped automatically."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        metavar="FILE",
        help="Path to TOML sweep config (see sweep.example.toml)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help="Override the db_path from config (e.g. ~/custom/ptbot.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned runs without invoking any agents",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ptbot-sweep CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser()
    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    db_path_override = Path(args.db_path).expanduser() if args.db_path else None

    run_sweep(config, dry_run=args.dry_run, db_path_override=db_path_override)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
