"""Sweep runner: automatically populates the deal database across markets and years."""

from __future__ import annotations

import re
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from . import db as _db
from .models import ResearchParams
from .orchestrator import Runner, run_pipeline

# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class MarketTarget(BaseModel):
    """A single (sector, geography) combination to sweep."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sector: str = Field(..., min_length=1)
    geography: str = Field(..., min_length=1)


class SweepSettings(BaseModel):
    """Global sweep parameters read from the [sweep] TOML section."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    years_back: int = Field(default=10, ge=1)
    db_path: str = Field(default="~/.ptbot/ptbot.db")
    output_base_dir: str = Field(default="./precedent-txn-output")
    min_multiples: int = Field(default=1, ge=1)
    timeout: int = Field(default=900, ge=1)
    max_workers: int = Field(default=1, ge=1)


class SweepConfig(BaseModel):
    """Top-level sweep configuration."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sweep: SweepSettings = Field(default_factory=SweepSettings)
    markets: list[MarketTarget] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_config(path: Path) -> SweepConfig:
    """Parse a TOML sweep config file and return a validated SweepConfig."""
    if not path.exists():
        raise FileNotFoundError(f"Sweep config not found: {path}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    return SweepConfig.model_validate(raw)


def slug(text: str) -> str:
    """Convert text to a lowercase, hyphen-separated directory-safe slug."""
    lowered = text.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    return hyphenated.strip("-")


def generate_annual_windows(years_back: int) -> list[tuple[str, str]]:
    """Return annual (start_date, end_date) windows, oldest first.

    Produces *years_back* complete calendar years ending last year, then appends
    the current year as a partial window ending today.

    Example with years_back=3 and today=2026-05-26:
        [("2023-01-01", "2023-12-31"),
         ("2024-01-01", "2024-12-31"),
         ("2025-01-01", "2025-12-31"),
         ("2026-01-01", "2026-05-26")]
    """
    today = datetime.now(tz=UTC).date()
    current_year = today.year
    start_year = current_year - years_back

    windows: list[tuple[str, str]] = []
    for year in range(start_year, current_year):
        windows.append((f"{year}-01-01", f"{year}-12-31"))

    # Current year — partial window ending today
    windows.append((f"{current_year}-01-01", today.isoformat()))
    return windows


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------


def _run_one(
    market: MarketTarget,
    start_date: str,
    end_date: str,
    *,
    config: SweepConfig,
    db_path: Path,
    output_base: Path,
    runner: Runner | None,
) -> bool:
    """Execute a single pipeline run. Returns True on success, False on failure."""
    label = (
        f"{market.sector} / {market.geography}"
        f" {start_date[:4]}"
        f"{'→' + end_date if end_date != start_date[:4] + '-12-31' else ''}"
    )
    print(f"[sweep] run   {label} ...")
    params = ResearchParams(
        sector=market.sector,
        geography=market.geography,
        start_date=start_date,
        end_date=end_date,
        min_multiples=config.sweep.min_multiples,
    )
    output_dir = output_base / slug(market.sector) / slug(market.geography) / start_date[:4]
    try:
        run_pipeline(
            params,
            output_dir,
            runner=runner,
            timeout=config.sweep.timeout,
            db_path=db_path,
        )
        print(f"[sweep] done  {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[sweep] FAIL  {label}: {exc}", file=sys.stderr)
        return False


def run_sweep(
    config: SweepConfig,
    *,
    runner: Runner | None = None,
    dry_run: bool = False,
    db_path_override: Path | None = None,
) -> None:
    """Run the sweep across all (market × window) combinations.

    Combinations already in the database are skipped.  When *max_workers* > 1
    in the config, pending combinations run in parallel using a thread pool —
    each pipeline is I/O-bound (waiting on Oz agents) so threading scales well.
    When *dry_run* is True, planned runs are printed but no agents are invoked.
    """
    db_path = db_path_override or Path(config.sweep.db_path).expanduser()
    output_base = Path(config.sweep.output_base_dir).expanduser()
    windows = generate_annual_windows(config.sweep.years_back)
    max_workers = config.sweep.max_workers
    total = len(config.markets) * len(windows)

    # --- Phase 1: skip detection (single-threaded, one DB connection) ---
    conn = _db.open_db(db_path)
    pending: list[tuple[MarketTarget, str, str]] = []
    skipped = 0
    for market in config.markets:
        for start_date, end_date in windows:
            if _db.query_run_exists(conn, market.sector, market.geography, start_date, end_date):
                label = (
                    f"{market.sector} / {market.geography}"
                    f" {start_date[:4]}"
                    f"{'→' + end_date if end_date != start_date[:4] + '-12-31' else ''}"
                )
                print(f"[sweep] skip  {label}")
                skipped += 1
            else:
                pending.append((market, start_date, end_date))
    conn.close()

    print(
        f"[sweep] {len(config.markets)} market(s) × {len(windows)} windows"
        f" = {total} combinations | {skipped} skipped, {len(pending)} to run"
        f" (max_workers={max_workers})"
    )

    if dry_run:
        print("[sweep] dry-run mode — no agents will be invoked")
        for market, start_date, end_date in pending:
            label = (
                f"{market.sector} / {market.geography}"
                f" {start_date[:4]}"
                f"{'→' + end_date if end_date != start_date[:4] + '-12-31' else ''}"
            )
            print(f"[sweep] would run  {label}")
        print(f"[sweep] dry-run complete — {len(pending)} would run, {skipped} skipped")
        return

    # --- Phase 2: parallel execution ---
    completed = failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _run_one,
                market,
                start_date,
                end_date,
                config=config,
                db_path=db_path,
                output_base=output_base,
                runner=runner,
            ): (market, start_date, end_date)
            for market, start_date, end_date in pending
        }
        for future in as_completed(futures):
            if future.result():
                completed += 1
            else:
                failed += 1

    summary = f"[sweep] complete — {completed} run(s), {skipped} skipped"
    if failed:
        summary += f", {failed} failed (see stderr)"
    print(summary)
