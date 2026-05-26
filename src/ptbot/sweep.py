"""Sweep runner for PTBot — orchestrates many sector × year pipelines in parallel."""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cloud_runner import make_cloud_runner
from .models import ResearchParams
from .orchestrator import run_pipeline

# Default environment for cloud sweeps (ptbot-sweep Oz environment)
_DEFAULT_ENV_ID = "fEBJDgnT6nfHXm6y2DjLGR"


@dataclass(frozen=True)
class SweepRun:
    """One pipeline in the sweep: a single sector × year combination."""

    sector: str
    year: int
    geography: str
    min_multiples: int = 1

    @property
    def label(self) -> str:
        """Human-readable identifier for log lines."""
        return f"{self.sector}/{self.year}"


def load_sweep_config(config_path: Path) -> tuple[list[SweepRun], dict[str, Any]]:
    """Load a TOML sweep config and expand it into SweepRun objects.

    Returns ``(runs, sweep_meta)`` where ``sweep_meta`` holds top-level sweep settings.
    """
    with config_path.open("rb") as fh:
        config = tomllib.load(fh)

    sweep_meta = config.get("sweep", {})
    geography = str(sweep_meta.get("geography", "United States"))
    start_year = int(sweep_meta.get("start_year", 2016))
    end_year = int(sweep_meta.get("end_year", 2026))
    min_multiples = int(sweep_meta.get("min_multiples", 1))

    sectors = [str(s["name"]) for s in config.get("sectors", [])]
    if not sectors:
        raise ValueError("sweep config must define at least one [[sectors]] entry")

    runs: list[SweepRun] = []
    for sector in sectors:
        for year in range(start_year, end_year + 1):
            runs.append(
                SweepRun(
                    sector=sector,
                    year=year,
                    geography=geography,
                    min_multiples=min_multiples,
                )
            )
    return runs, sweep_meta


def _execute_pipeline(
    sweep_run: SweepRun,
    base_output_dir: Path,
    runner: Any,
    timeout: int,
) -> tuple[SweepRun, bool, str]:
    """Run one sector × year pipeline. Returns ``(run, success, message)``."""
    slug = sweep_run.sector.lower().replace(" ", "-")
    output_dir = base_output_dir / slug / str(sweep_run.year)
    params = ResearchParams(
        sector=sweep_run.sector,
        geography=sweep_run.geography,
        start_date=f"{sweep_run.year}-01-01",
        end_date=f"{sweep_run.year}-12-31",
        min_multiples=sweep_run.min_multiples,
    )
    try:
        paths = run_pipeline(params, output_dir, runner=runner, timeout=timeout)
        return sweep_run, True, f"→ {paths.final_markdown}"
    except Exception as exc:  # noqa: BLE001
        return sweep_run, False, str(exc)


def sweep_main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ptbot-sweep command."""
    parser = argparse.ArgumentParser(
        description="Run a multi-sector, multi-year PTBot sweep.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", required=True, help="Path to sweep TOML config file")
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Dispatch research agents to Oz cloud (requires WARP_API_KEY)",
    )
    parser.add_argument(
        "--environment",
        default=_DEFAULT_ENV_ID,
        help="Oz environment ID for cloud agents",
    )
    parser.add_argument(
        "--output-dir",
        default="./sweep-output",
        help="Base directory for pipeline output",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-agent timeout in seconds",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum number of pipelines running in parallel",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without executing",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[sweep] error: config file not found: {config_path}", file=sys.stderr)
        return 1

    runs, _sweep_meta = load_sweep_config(config_path)
    total = len(runs)
    agents_per_pipeline = 8  # 4 Pass1 scouts + 3 Pass2 deep-dives + 1 QC

    if args.dry_run:
        print(f"[sweep] dry-run: {total} pipelines × {agents_per_pipeline} agents = {total * agents_per_pipeline} total agent calls")
        for run in runs:
            print(f"  {run.label}  ({run.geography}, {run.sector} {run.year}-01-01 → {run.year}-12-31)")
        return 0

    # Build runner
    runner: Any
    if args.cloud:
        runner = make_cloud_runner(environment_id=args.environment)
        mode = f"cloud (env={args.environment})"
    else:
        runner = None  # orchestrator falls back to attack.market local runner
        mode = "local (attack.market)"

    base_output_dir = Path(args.output_dir)
    base_output_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[sweep] starting: {total} pipelines, concurrency={args.concurrency}, "
        f"mode={mode}, timeout={args.timeout}s"
    )

    succeeded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        future_to_run = {
            pool.submit(_execute_pipeline, run, base_output_dir, runner, args.timeout): run
            for run in runs
        }
        for future in as_completed(future_to_run):
            sweep_run, success, message = future.result()
            if success:
                succeeded += 1
                print(f"[sweep] ✓ {sweep_run.label}: {message}")
            else:
                failed += 1
                print(f"[sweep] ✗ {sweep_run.label}: {message}", file=sys.stderr)

    total_agents = total * agents_per_pipeline
    print(
        f"[sweep] complete: {succeeded}/{total} pipelines succeeded, "
        f"{total_agents} agents dispatched, output in {args.output_dir}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(sweep_main())
