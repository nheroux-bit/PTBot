"""Sweep runner: automatically populates the deal database across markets and years."""

from __future__ import annotations

import re
import sys
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from . import db as _db
from . import db_sync as _db_sync
from .models import ResearchParams
from .orchestrator import Runner, run_pipeline
from .runners import make_cloud_runner

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
    # Cloud execution
    cloud_environment: str | None = Field(default=None)
    # S3-backed DB persistence for cloud deployments (requires AWS CLI)
    db_sync_s3_uri: str | None = Field(default=None)
    # Safeguard: maximum number of active cloud runs allowed before dispatch is blocked
    max_active_cloud_runs: int = Field(default=10, ge=1)


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


def _watchdog_thread(
    db_path: Path,
    timeout_secs: int,
    stop_event: threading.Event,
    poll_interval: float = 60.0,
) -> None:
    """Background daemon: kill cloud runs that have been running too long.

    Polls every *poll_interval* seconds (default 60; pass a small value in
    tests).  Any run in the registry whose ``dispatched_at`` is older than
    ``timeout_secs * 1.5`` without reaching a terminal state is force-killed
    via ``kill_cloud_run()`` and marked revoked in the registry.  Closes the
    2026-05-27 firedrill failure mode where agents ran past their configured
    timeout and became unresponsive.
    """
    from .runners import kill_cloud_run

    deadline_factor = 1.5
    while not stop_event.wait(poll_interval):  # wakes immediately on stop
        try:
            conn = _db.open_db(db_path)
            try:
                active = _db.list_cloud_runs(conn, active_only=True)
                now_ts = time.time()
                for run in active:
                    try:
                        dispatched = datetime.fromisoformat(
                            run["dispatched_at"].replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        continue
                    elapsed = now_ts - dispatched
                    if elapsed > timeout_secs * deadline_factor:
                        rid = run["oz_run_id"]
                        print(
                            f"[sweep:watchdog] overdue ({elapsed:.0f}s > "
                            f"{timeout_secs * deadline_factor:.0f}s) — killing {rid[:12]}...",
                            file=sys.stderr,
                        )
                        ok, kill_msg = kill_cloud_run(rid, run.get("run_url", ""))
                        if not ok:
                            print(
                                f"[sweep:watchdog] oz kill failed for {rid[:12]}...: "
                                f"{kill_msg.splitlines()[0][:80]}",
                                file=sys.stderr,
                            )
                        _db.mark_cloud_run_revoked(conn, rid)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — watchdog must never crash the sweep
            print(f"[sweep:watchdog] error: {exc}", file=sys.stderr)


def run_sweep(
    config: SweepConfig,
    *,
    runner: Runner | None = None,
    dry_run: bool = False,
    db_path_override: Path | None = None,
    cloud: bool = False,
    cloud_environment: str | None = None,
    max_active_cloud_runs: int | None = None,
) -> int:
    """Run the sweep across all (market × window) combinations.

    Combinations already in the database are skipped.  When *max_workers* > 1
    in the config, pending combinations run in parallel using a thread pool —
    each pipeline is I/O-bound (waiting on Oz agents) so threading scales well.
    When *dry_run* is True, planned runs are printed but no agents are invoked.

    When *cloud* is True, ``oz agent run-cloud`` is used for every pipeline
    task instead of the default local runner.  The optional *cloud_environment*
    argument (or ``config.sweep.cloud_environment``) selects the Oz environment.

    **WIP cap (safeguard #1):** When *cloud* is True, the registry is checked
    before any dispatch.  If the number of currently active cloud runs meets or
    exceeds *max_active_cloud_runs* (or ``config.sweep.max_active_cloud_runs``
    when that argument is None), the sweep aborts immediately.  This prevents
    a new sweep from stacking on top of a runaway prior run.

    **Timeout watchdog (safeguard #2):** When *cloud* is True (and not
    *dry_run*), a background daemon thread polls the registry every 60 s and
    force-kills any run that has exceeded ``config.sweep.timeout * 1.5``
    without reaching a terminal state.

    When ``config.sweep.db_sync_s3_uri`` is set, the database is downloaded
    from S3 before skip detection and uploaded back to S3 after execution so
    that ephemeral cloud environments retain deal history across runs.
    """
    db_path = db_path_override or Path(config.sweep.db_path).expanduser()
    output_base = Path(config.sweep.output_base_dir).expanduser()
    windows = generate_annual_windows(config.sweep.years_back)
    max_workers = config.sweep.max_workers
    total = len(config.markets) * len(windows)
    wip_cap = (
        max_active_cloud_runs
        if max_active_cloud_runs is not None
        else config.sweep.max_active_cloud_runs
    )

    # Resolve the runner: explicit injection > cloud flag > default local.
    if runner is None and cloud:
        env = cloud_environment or config.sweep.cloud_environment
        # cloud-control-001: pass db_path + parent so every oz dispatch is registered
        # in the persistent control plane (survives parent death / firedrill).
        parent_ctx = f"sweep:{slug(str(db_path))}"
        runner = make_cloud_runner(
            environment=env,
            registry_db_path=db_path,
            parent_context=parent_ctx,
        )
    # else: run_pipeline() resolves the default runner lazily when runner is None.

    # Pull DB from S3 before skip detection so existing runs are visible.
    s3_uri = config.sweep.db_sync_s3_uri
    if s3_uri and not dry_run:
        _db_sync.pull_db(s3_uri, db_path)

    # --- WIP cap check (cloud only, before any dispatch) ---
    if cloud and not dry_run:
        cap_conn = _db.open_db(db_path)
        try:
            active_runs = _db.list_cloud_runs(cap_conn, active_only=True)
            active_count = len(active_runs)
            if active_count >= wip_cap:
                ids_preview = ", ".join(r["oz_run_id"][:12] + "..." for r in active_runs[:5])
                extra = f" (+{active_count - 5} more)" if active_count > 5 else ""
                raise RuntimeError(
                    f"[sweep] WIP cap reached: {active_count} active cloud run(s) ≥ "
                    f"max_active={wip_cap}. Active: {ids_preview}{extra}\n"
                    "Use `ptbot cloud kill-all` to clear them or raise --max-active."
                )
        finally:
            cap_conn.close()

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
        return 0

    # --- Phase 2: parallel execution + watchdog ---
    stop_watchdog = threading.Event()
    if cloud:  # launch watchdog daemon for all cloud sweeps
        wdog = threading.Thread(
            target=_watchdog_thread,
            args=(db_path, config.sweep.timeout, stop_watchdog),
            daemon=True,
            name="sweep-watchdog",
        )
        wdog.start()
    else:
        wdog = None

    completed = failed = 0
    try:
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
    finally:
        stop_watchdog.set()  # always stop the watchdog, even on error / Ctrl-C
        if wdog is not None:
            wdog.join(timeout=5)

    summary = f"[sweep] complete — {completed} run(s), {skipped} skipped"
    if failed:
        summary += f", {failed} failed (see stderr)"
    print(summary)

    # Push DB to S3 after execution so future runs inherit the new rows.
    if s3_uri:
        _db_sync.push_db(db_path, s3_uri)

    return failed
