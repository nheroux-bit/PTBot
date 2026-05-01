"""Command line interface for PTBot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .excel import generate_comps_excel
from .models import ResearchParams
from .orchestrator import run_pipeline
from .pdf import markdown_to_pdf
from .prompt_builder import build_config


def build_parser() -> argparse.ArgumentParser:
    """Build the PTBot argument parser."""
    parser = argparse.ArgumentParser(description="Run precedent transaction research.")
    parser.add_argument("--sector", required=True, help="Sector or industry vertical")
    parser.add_argument("--geography", required=True, help="Geographic scope")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--min-multiples", type=int, default=1, help="Minimum multiples required")
    parser.add_argument("--deal-size-min", default=None, help="Minimum deal size filter")
    parser.add_argument("--deal-size-max", default=None, help="Maximum deal size filter")
    parser.add_argument("--output-dir", default="./precedent-txn-output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=900, help="Per-agent timeout in seconds")
    parser.add_argument(
        "--config-only", action="store_true", help="Print generated config and exit"
    )
    return parser


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
    """Run the PTBot CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    params = params_from_args(args)

    if args.config_only:
        print(json.dumps(build_config(params), indent=2))
        return 0

    output_dir = Path(args.output_dir)
    paths = run_pipeline(params, output_dir, timeout=args.timeout)
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
