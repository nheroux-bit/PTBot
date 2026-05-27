"""Tests for ptbot.sweep."""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ptbot.sweep import (
    MarketTarget,
    SweepConfig,
    SweepSettings,
    generate_annual_windows,
    load_config,
    run_sweep,
    slug,
)

S3_URI = "s3://my-bucket/ptbot/ptbot.db"

# ---------------------------------------------------------------------------
# slug
# ---------------------------------------------------------------------------


def test_slug_lowercases_and_hyphenates() -> None:
    assert slug("Vertical SaaS") == "vertical-saas"


def test_slug_strips_leading_trailing_hyphens() -> None:
    assert slug("  HealthTech  ") == "healthtech"


def test_slug_collapses_non_alphanumeric() -> None:
    assert slug("FinTech & Payments!") == "fintech-payments"


# ---------------------------------------------------------------------------
# generate_annual_windows
# ---------------------------------------------------------------------------


def _patch_today(mock_dt: MagicMock, today: date) -> None:
    """Configure a patched datetime so .now(...).date() returns *today*."""
    mock_dt.now.return_value.date.return_value = today


def test_generate_annual_windows_count() -> None:
    """years_back=3 should produce 3 complete years + 1 partial = 4 windows."""
    with patch("ptbot.sweep.datetime") as mock_dt:
        _patch_today(mock_dt, date(2026, 5, 26))
        windows = generate_annual_windows(3)
    assert len(windows) == 4


def test_generate_annual_windows_oldest_first() -> None:
    """Windows should be ordered from oldest to newest."""
    with patch("ptbot.sweep.datetime") as mock_dt:
        _patch_today(mock_dt, date(2026, 5, 26))
        windows = generate_annual_windows(3)
    assert windows[0][0] < windows[1][0] < windows[2][0]


def test_generate_annual_windows_complete_years_end_dec31() -> None:
    """All complete-year windows should end on December 31."""
    with patch("ptbot.sweep.datetime") as mock_dt:
        _patch_today(mock_dt, date(2026, 5, 26))
        windows = generate_annual_windows(3)
    for _start, end in windows[:-1]:
        assert end.endswith("-12-31"), f"Expected Dec 31 end, got {end}"


def test_generate_annual_windows_partial_current_year_ends_today() -> None:
    """The last window (current year) should end on today's date."""
    today = date(2026, 5, 26)
    with patch("ptbot.sweep.datetime") as mock_dt:
        _patch_today(mock_dt, today)
        windows = generate_annual_windows(3)
    assert windows[-1][1] == today.isoformat()


def test_generate_annual_windows_date_format() -> None:
    """All dates should be YYYY-MM-DD strings."""
    with patch("ptbot.sweep.datetime") as mock_dt:
        _patch_today(mock_dt, date(2026, 5, 26))
        windows = generate_annual_windows(2)
    import re

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for start, end in windows:
        assert pattern.match(start), f"Bad start format: {start}"
        assert pattern.match(end), f"Bad end format: {end}"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def _write_toml(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_load_config_valid(tmp_path: Path) -> None:
    """A well-formed TOML file should parse into a SweepConfig."""
    cfg_file = _write_toml(
        tmp_path / "sweep.toml",
        """
        [sweep]
        years_back = 5
        db_path = "/tmp/test.db"

        [[markets]]
        sector = "HealthTech"
        geography = "United States"
        """,
    )
    config = load_config(cfg_file)
    assert config.sweep.years_back == 5
    assert config.sweep.db_path == "/tmp/test.db"
    assert len(config.markets) == 1
    assert config.markets[0].sector == "HealthTech"


def test_load_config_defaults(tmp_path: Path) -> None:
    """Missing [sweep] section should fall back to SweepSettings defaults."""
    cfg_file = _write_toml(
        tmp_path / "sweep.toml",
        """
        [[markets]]
        sector = "FinTech"
        geography = "Boston"
        """,
    )
    config = load_config(cfg_file)
    assert config.sweep.years_back == 10
    assert config.sweep.min_multiples == 1


def test_load_config_multiple_markets(tmp_path: Path) -> None:
    """Multiple [[markets]] blocks should all be parsed."""
    cfg_file = _write_toml(
        tmp_path / "sweep.toml",
        """
        [[markets]]
        sector = "A"
        geography = "US"

        [[markets]]
        sector = "B"
        geography = "UK"
        """,
    )
    config = load_config(cfg_file)
    assert len(config.markets) == 2


def test_load_config_missing_file(tmp_path: Path) -> None:
    """load_config should raise FileNotFoundError for a missing file."""
    with pytest.raises(FileNotFoundError, match="Sweep config not found"):
        load_config(tmp_path / "nonexistent.toml")


# ---------------------------------------------------------------------------
# run_sweep
# ---------------------------------------------------------------------------


def _minimal_config(db_path: str, years_back: int = 1) -> SweepConfig:
    return SweepConfig(
        sweep=SweepSettings(
            years_back=years_back,
            db_path=db_path,
            output_base_dir="/tmp/ptbot-sweep-test",
            min_multiples=1,
            timeout=1,
        ),
        markets=[MarketTarget(sector="HealthTech", geography="US")],
    )


def test_run_sweep_dry_run_never_calls_pipeline(tmp_path: Path) -> None:
    """dry_run=True should never invoke run_pipeline."""
    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    with (
        patch("ptbot.sweep.run_pipeline") as mock_pipeline,
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=True, db_path_override=db_path)

    mock_pipeline.assert_not_called()


def test_run_sweep_calls_pipeline_for_new_combination(tmp_path: Path) -> None:
    """A new (market, window) combination should trigger run_pipeline."""
    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    fake_paths = MagicMock()

    with (
        patch("ptbot.sweep.run_pipeline", return_value=fake_paths) as mock_pipeline,
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path)

    # 1 market × (1 complete year + 1 partial) = 2 calls
    assert mock_pipeline.call_count == 2


def test_run_sweep_uses_cloud_runner_when_cloud_flag_set(tmp_path: Path) -> None:
    """run_sweep(cloud=True) should inject a cloud runner into run_pipeline."""
    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    captured_runners: list = []

    def spy_pipeline(*args, runner=None, **kwargs):  # type: ignore[no-untyped-def]
        captured_runners.append(runner)
        return MagicMock()

    with (
        patch("ptbot.sweep.run_pipeline", side_effect=spy_pipeline),
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path, cloud=True)

    assert len(captured_runners) > 0
    for runner in captured_runners:
        assert runner is not None, "expected a cloud runner to be injected"
        assert callable(runner)


def test_run_sweep_cloud_environment_passed_to_runner(tmp_path: Path) -> None:
    """cloud_environment kwarg should be forwarded to make_cloud_runner."""
    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    with (
        patch("ptbot.sweep.make_cloud_runner") as mock_make_runner,
        patch("ptbot.sweep.run_pipeline", return_value=MagicMock()),
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(
            config,
            dry_run=False,
            db_path_override=db_path,
            cloud=True,
            cloud_environment="env-xyz",
        )

    from unittest.mock import ANY

    mock_make_runner.assert_called_once_with(
        environment="env-xyz",
        registry_db_path=ANY,
        parent_context=ANY,
    )


def test_run_sweep_s3_pull_called_before_skip_detection(tmp_path: Path) -> None:
    """pull_db should be called before the DB connection is opened."""
    db_path = tmp_path / "test.db"
    config = SweepConfig(
        sweep=SweepSettings(
            years_back=1,
            db_path=str(db_path),
            output_base_dir="/tmp/ptbot-sweep-test",
            min_multiples=1,
            timeout=1,
            db_sync_s3_uri=S3_URI,
        ),
        markets=[MarketTarget(sector="HealthTech", geography="US")],
    )

    call_order: list[str] = []

    def spy_pull(uri: str, path: object) -> bool:
        call_order.append("pull")
        return False

    def spy_pipeline(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_order.append("pipeline")
        return MagicMock()

    with (
        patch("ptbot.sweep._db_sync.pull_db", side_effect=spy_pull),
        patch("ptbot.sweep._db_sync.push_db"),
        patch("ptbot.sweep.run_pipeline", side_effect=spy_pipeline),
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path)

    assert call_order[0] == "pull", "pull should happen before pipeline runs"


def test_run_sweep_s3_push_called_after_execution(tmp_path: Path) -> None:
    """push_db should be called after all pipeline runs complete."""
    db_path = tmp_path / "test.db"
    config = SweepConfig(
        sweep=SweepSettings(
            years_back=1,
            db_path=str(db_path),
            output_base_dir="/tmp/ptbot-sweep-test",
            min_multiples=1,
            timeout=1,
            db_sync_s3_uri=S3_URI,
        ),
        markets=[MarketTarget(sector="HealthTech", geography="US")],
    )

    with (
        patch("ptbot.sweep._db_sync.pull_db", return_value=False),
        patch("ptbot.sweep._db_sync.push_db") as mock_push,
        patch("ptbot.sweep.run_pipeline", return_value=MagicMock()),
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path)

    mock_push.assert_called_once_with(db_path, S3_URI)


def test_run_sweep_s3_sync_not_called_without_uri(tmp_path: Path) -> None:
    """pull_db and push_db should not be called when db_sync_s3_uri is unset."""
    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    with (
        patch("ptbot.sweep._db_sync.pull_db") as mock_pull,
        patch("ptbot.sweep._db_sync.push_db") as mock_push,
        patch("ptbot.sweep.run_pipeline", return_value=MagicMock()),
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path)

    mock_pull.assert_not_called()
    mock_push.assert_not_called()


def test_run_sweep_s3_sync_not_called_in_dry_run(tmp_path: Path) -> None:
    """pull_db should not be called when dry_run=True."""
    db_path = tmp_path / "test.db"
    config = SweepConfig(
        sweep=SweepSettings(
            years_back=1,
            db_path=str(db_path),
            output_base_dir="/tmp/ptbot-sweep-test",
            min_multiples=1,
            timeout=1,
            db_sync_s3_uri=S3_URI,
        ),
        markets=[MarketTarget(sector="HealthTech", geography="US")],
    )

    with (
        patch("ptbot.sweep._db_sync.pull_db") as mock_pull,
        patch("ptbot.sweep._db_sync.push_db") as mock_push,
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=True, db_path_override=db_path)

    mock_pull.assert_not_called()
    mock_push.assert_not_called()


def test_run_sweep_skips_existing_combination(tmp_path: Path) -> None:
    """A combination already in the DB should not trigger run_pipeline."""
    from ptbot.db import insert_run, new_run_id, open_db
    from ptbot.models import ResearchParams

    db_path = tmp_path / "test.db"
    config = _minimal_config(str(db_path), years_back=1)

    # Pre-populate the DB with the 2025 annual window so it gets skipped
    conn = open_db(db_path)
    insert_run(
        conn,
        new_run_id(),
        ResearchParams(
            sector="HealthTech",
            geography="US",
            start_date="2025-01-01",
            end_date="2025-12-31",
        ),
    )
    conn.close()

    fake_paths = MagicMock()

    with (
        patch("ptbot.sweep.run_pipeline", return_value=fake_paths) as mock_pipeline,
        patch("ptbot.sweep.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.date.return_value = date(2026, 5, 26)
        run_sweep(config, dry_run=False, db_path_override=db_path)

    # 2025 skipped; only 2026 partial window should run
    assert mock_pipeline.call_count == 1
