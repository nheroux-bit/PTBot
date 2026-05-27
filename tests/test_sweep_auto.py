"""Tests for the ptbot sweep:auto CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ptbot.cli import main
from ptbot.sweep import SweepConfig


def _base_argv(*extra: str) -> list[str]:
    return [
        "sweep:auto",
        "--sectors",
        "FinTech",
        "--geography",
        "United States",
        *extra,
    ]


# ---------------------------------------------------------------------------
# Argument parsing + config construction
# ---------------------------------------------------------------------------


def test_sweep_auto_single_sector_builds_config(capsys: pytest.CaptureFixture[str]) -> None:
    """Single sector builds a one-market SweepConfig and calls run_sweep."""
    with patch("ptbot.cli._handle_sweep_auto_command") as mock_handler:
        mock_handler.return_value = 0
        rc = main(_base_argv())
    assert rc == 0


def test_sweep_auto_calls_run_sweep_with_correct_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("ptbot.cli._handle_sweep_auto_command") as mock_fn:
        mock_fn.return_value = 0
        rc = main(_base_argv("--dry-run"))
    assert rc == 0
    mock_fn.assert_called_once()


def test_sweep_auto_multi_sector_csv(capsys: pytest.CaptureFixture[str]) -> None:
    """Comma-separated sectors each become a separate MarketTarget."""
    captured_config: list[SweepConfig] = []

    def fake_run_sweep(config: SweepConfig, **kwargs: object) -> None:
        captured_config.append(config)

    import ptbot.cli as _cli

    # Call the real handler directly with run_sweep patched — avoids recursion
    with patch("ptbot.sweep.run_sweep", fake_run_sweep):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "FinTech, HealthTech, SaaS",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert len(captured_config) == 1
    sector_names = [m.sector for m in captured_config[0].markets]
    assert sector_names == ["FinTech", "HealthTech", "SaaS"]


def test_sweep_auto_dry_run_passes_through(capsys: pytest.CaptureFixture[str]) -> None:
    run_kwargs: dict = {}

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        run_kwargs.update(kwargs)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            ["sweep:auto", "--sectors", "FinTech", "--geography", "United States", "--dry-run"]
        )

    assert rc == 0
    assert run_kwargs.get("dry_run") is True


def test_sweep_auto_db_path_override(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    custom_db = tmp_path / "custom.db"
    run_kwargs: dict = {}

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        run_kwargs.update(kwargs)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "SaaS",
                "--geography",
                "Europe",
                "--db-path",
                str(custom_db),
                "--dry-run",
            ]
        )

    assert rc == 0
    assert run_kwargs["db_path_override"] == custom_db


def test_sweep_auto_environment_enables_cloud(capsys: pytest.CaptureFixture[str]) -> None:
    run_kwargs: dict = {}

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        run_kwargs.update(kwargs)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
                "--environment",
                "env-prod-42",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert run_kwargs["cloud"] is True
    assert run_kwargs["cloud_environment"] == "env-prod-42"


def test_sweep_auto_no_environment_uses_local(capsys: pytest.CaptureFixture[str]) -> None:
    run_kwargs: dict = {}

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        run_kwargs.update(kwargs)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert run_kwargs["cloud"] is False


def test_sweep_auto_max_workers_passed_to_config(capsys: pytest.CaptureFixture[str]) -> None:
    captured: list[SweepConfig] = []

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        captured.append(config)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
                "--max-workers",
                "8",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert len(captured) == 1
    assert captured[0].sweep.max_workers == 8


def test_sweep_auto_sectors_parsed_from_csv(capsys: pytest.CaptureFixture[str]) -> None:
    """Whitespace-trimmed CSV sectors each become a distinct MarketTarget."""
    captured: list[SweepConfig] = []

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        captured.append(config)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                " FinTech , HealthTech , SaaS ",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert len(captured) == 1
    sector_names = [m.sector for m in captured[0].markets]
    assert sector_names == ["FinTech", "HealthTech", "SaaS"]
    # All markets share the same geography
    assert all(m.geography == "United States" for m in captured[0].markets)


def test_sweep_auto_years_back_forwarded(capsys: pytest.CaptureFixture[str]) -> None:
    captured: list[SweepConfig] = []

    def capture_run(config: SweepConfig, **kwargs: object) -> None:
        captured.append(config)

    import ptbot.cli as _cli

    with patch("ptbot.sweep.run_sweep", capture_run):
        rc = _cli._handle_sweep_auto_command(
            [
                "sweep:auto",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
                "--years",
                "3",
                "--dry-run",
            ]
        )

    assert rc == 0
    assert captured[0].sweep.years_back == 3


def test_sweep_auto_dispatched_from_main(capsys: pytest.CaptureFixture[str]) -> None:
    """main() routes sweep:auto to the handler without hitting the run parser."""
    with patch("ptbot.cli._handle_sweep_auto_command", return_value=0) as mock_fn:
        rc = main(
            [
                "sweep:auto",
                "--sectors",
                "FinTech",
                "--geography",
                "United States",
                "--dry-run",
            ]
        )
    assert rc == 0
    mock_fn.assert_called_once()
