"""Tests for ptbot.sweep_cli (the ptbot-sweep entrypoint)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ptbot.sweep_cli import build_parser, main


def test_build_parser_has_expected_arguments() -> None:
    parser = build_parser()
    actions = {a.dest: a for a in parser._actions}

    assert "config" in actions
    assert actions["config"].required is True

    assert "db_path" in actions
    assert "dry_run" in actions
    assert "cloud" in actions
    assert "environment" in actions


def test_main_success_calls_run_sweep_with_overrides(tmp_path: Path) -> None:
    cfg = tmp_path / "sweep.toml"
    cfg.write_text(
        "[sweep]\nyears_back = 1\n\n[[markets]]\nsector = 'X'\ngeography = 'Y'\n", encoding="utf-8"
    )

    with (
        patch("ptbot.sweep_cli.load_config") as mock_load,
        patch("ptbot.sweep_cli.run_sweep", return_value=0) as mock_run,
    ):
        mock_load.return_value = MagicMock()
        exit_code = main(
            [
                "--config",
                str(cfg),
                "--db-path",
                "/tmp/custom.db",
            ]
        )

    assert exit_code == 0
    mock_load.assert_called_once()
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["db_path_override"] == Path("/tmp/custom.db")
    assert call_kwargs["dry_run"] is False
    assert call_kwargs["cloud"] is False


def test_main_dry_run_flag_forwarded(tmp_path: Path) -> None:
    cfg = tmp_path / "sweep.toml"
    cfg.write_text("[[markets]]\nsector='A'\ngeography='B'\n", encoding="utf-8")

    with (
        patch("ptbot.sweep_cli.load_config", return_value=MagicMock()),
        patch("ptbot.sweep_cli.run_sweep", return_value=0) as mock_run,
    ):
        exit_code = main(["--config", str(cfg), "--dry-run"])

    assert exit_code == 0
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["dry_run"] is True


def test_main_cloud_and_environment_flags(tmp_path: Path) -> None:
    cfg = tmp_path / "sweep.toml"
    cfg.write_text("[[markets]]\nsector='A'\ngeography='B'\n", encoding="utf-8")

    with (
        patch("ptbot.sweep_cli.load_config", return_value=MagicMock()),
        patch("ptbot.sweep_cli.run_sweep", return_value=0) as mock_run,
    ):
        exit_code = main(
            [
                "--config",
                str(cfg),
                "--cloud",
                "--environment",
                "env-prod-7",
            ]
        )

    assert exit_code == 0
    kwargs = mock_run.call_args.kwargs
    assert kwargs["cloud"] is True
    assert kwargs["cloud_environment"] == "env-prod-7"


def test_main_missing_config_file_exits_nonzero_and_prints_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--config", "/definitely/not/here.toml"])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "not/here.toml" in captured.err


def test_main_uses_sys_argv_when_none_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "sweep.toml"
    cfg.write_text("[[markets]]\nsector='A'\ngeography='B'\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["ptbot-sweep", "--config", str(cfg), "--dry-run"])

    with (
        patch("ptbot.sweep_cli.load_config", return_value=MagicMock()),
        patch("ptbot.sweep_cli.run_sweep", return_value=0) as mock_run,
    ):
        exit_code = main()

    assert exit_code == 0
    assert mock_run.call_args.kwargs["dry_run"] is True


def test_main_returns_zero_on_success(tmp_path: Path) -> None:
    cfg = tmp_path / "sweep.toml"
    cfg.write_text("[[markets]]\nsector='A'\ngeography='B'\n", encoding="utf-8")

    with (
        patch("ptbot.sweep_cli.load_config", return_value=MagicMock()),
        patch("ptbot.sweep_cli.run_sweep", return_value=0),
    ):
        assert main(["--config", str(cfg)]) == 0
