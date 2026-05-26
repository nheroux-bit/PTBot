"""Tests for PTBot cloud runner and sweep orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ptbot.cloud_runner import (
    TERMINAL_STATES,
    _extract_agent_output,
    _get_run_state,
    _spawn_cloud_agent,
    make_cloud_runner,
)
from ptbot.sweep import SweepRun, _execute_pipeline, load_sweep_config, sweep_main


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _fake_oz_output(run_id: str) -> str:
    """Produce the text output that oz-preview emits when spawning a cloud agent."""
    return (
        f"Spawned ambient agent with run ID: {run_id}\n"
        f"View run: https://oz.warp.dev/runs/{run_id}\n"
        "Agent state: InProgress\n"
    )


@pytest.fixture()
def toml_path(tmp_path: Path) -> Path:
    """Write the new-sectors sweep config to a temp file."""
    toml = tmp_path / "sweep.toml"
    toml.write_text(
        """\
[sweep]
geography     = "United States"
start_year    = 2016
end_year      = 2026
min_multiples = 1
output_dir    = "./sweep-output"

[[sectors]]
name = "Cybersecurity"

[[sectors]]
name = "EdTech"

[[sectors]]
name = "InsurTech"

[[sectors]]
name = "HR Tech"

[[sectors]]
name = "PropTech"
""",
        encoding="utf-8",
    )
    return toml


# ---------------------------------------------------------------------------
# _spawn_cloud_agent
# ---------------------------------------------------------------------------


def test_spawn_extracts_run_id_from_text(mocker: Any) -> None:
    """Run ID should be parsed from the human-readable oz-preview output."""
    expected_id = "019e664f-52cf-702d-b5aa-953de5a227f8"
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=_fake_oz_output(expected_id), stderr=""),
    )

    run_id = _spawn_cloud_agent("hello", "env-id")

    assert run_id == expected_id


def test_spawn_raises_on_non_zero_exit(mocker: Any) -> None:
    """Non-zero exit code from oz-preview should raise RuntimeError."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="", stderr="unauthorized"),
    )

    with pytest.raises(RuntimeError, match="spawn failed"):
        _spawn_cloud_agent("p", "e")


def test_spawn_raises_when_run_id_absent(mocker: Any) -> None:
    """Output without a run ID pattern should raise RuntimeError."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="No useful output", stderr=""),
    )

    with pytest.raises(RuntimeError, match="no run ID found"):
        _spawn_cloud_agent("p", "e")


# ---------------------------------------------------------------------------
# _get_run_state
# ---------------------------------------------------------------------------


def test_get_run_state_parses_json(mocker: Any) -> None:
    """State should be extracted from the JSON status response."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(
            returncode=0,
            stdout=json.dumps({"state": "SUCCEEDED"}),
        ),
    )

    state = _get_run_state("run-id")

    assert state == "SUCCEEDED"


def test_get_run_state_raises_on_error(mocker: Any) -> None:
    """Non-zero exit code from oz-preview run get should raise."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=1, stderr="not found"),
    )

    with pytest.raises(RuntimeError, match="state poll failed"):
        _get_run_state("bad-id")


def test_get_run_state_raises_on_bad_json(mocker: Any) -> None:
    """Non-JSON state response should raise RuntimeError."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="not json"),
    )

    with pytest.raises(RuntimeError, match="non-JSON"):
        _get_run_state("run-id")


# ---------------------------------------------------------------------------
# _extract_agent_output
# ---------------------------------------------------------------------------


def test_extract_agent_output_returns_last_assistant_text(mocker: Any) -> None:
    """The last assistant text block in the conversation should be returned."""
    convo = {
        "steps": [
            {
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "Go"}]},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": '[{"target":"X","acquirer":"Y"}]'}],
                    },
                ]
            }
        ]
    }
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=json.dumps(convo)),
    )

    output = _extract_agent_output("run-id")

    assert '"target"' in output


def test_extract_agent_output_returns_empty_on_failure(mocker: Any) -> None:
    """Non-zero exit from oz-preview should return empty string."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=1, stdout=""),
    )

    assert _extract_agent_output("run-id") == ""


def test_extract_agent_output_returns_empty_on_bad_json(mocker: Any) -> None:
    """Malformed conversation JSON should return empty string."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="not json"),
    )

    assert _extract_agent_output("run-id") == ""


def test_extract_agent_output_returns_empty_when_no_assistant(mocker: Any) -> None:
    """A conversation with only user messages should return empty string."""
    convo = {
        "steps": [
            {"messages": [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]}
        ]
    }
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=json.dumps(convo)),
    )

    assert _extract_agent_output("run-id") == ""


# ---------------------------------------------------------------------------
# make_cloud_runner
# ---------------------------------------------------------------------------


def test_make_cloud_runner_returns_succeeded(mocker: Any) -> None:
    """Runner should return SUCCEEDED and agent output on successful cloud run."""
    run_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    spawn_mock = MagicMock(returncode=0, stdout=_fake_oz_output(run_id), stderr="")
    state_mock = MagicMock(returncode=0, stdout=json.dumps({"state": "SUCCEEDED"}))
    convo = {
        "steps": [
            {
                "messages": [
                    {"role": "assistant", "content": [{"type": "text", "text": "[]"}]}
                ]
            }
        ]
    }
    convo_mock = MagicMock(returncode=0, stdout=json.dumps(convo))

    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        side_effect=[spawn_mock, state_mock, convo_mock],
    )
    mocker.patch("ptbot.cloud_runner.time.sleep")
    mocker.patch("ptbot.cloud_runner.time.monotonic", side_effect=[0.0, 0.0, 9999.0])

    runner = make_cloud_runner("env-id", poll_interval=0.0)
    result = runner("Test prompt", timeout=60)

    assert result["state"] == "SUCCEEDED"
    assert result["run_id"] == run_id


def test_make_cloud_runner_returns_failed_on_spawn_error(mocker: Any) -> None:
    """Spawn failure should produce a FAILED result without crashing."""
    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="", stderr="permission denied"),
    )

    runner = make_cloud_runner("env-id")
    result = runner("prompt", timeout=10)

    assert result["state"] == "FAILED"
    assert "error" in result


def test_make_cloud_runner_times_out(mocker: Any) -> None:
    """Runner should return FAILED when the deadline expires before SUCCEEDED."""
    run_id = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    spawn_mock = MagicMock(returncode=0, stdout=_fake_oz_output(run_id), stderr="")
    state_mock = MagicMock(returncode=0, stdout=json.dumps({"state": "IN_PROGRESS"}))

    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        side_effect=[spawn_mock, state_mock],
    )
    mocker.patch("ptbot.cloud_runner.time.sleep")
    # deadline immediately exceeded after first poll
    mocker.patch("ptbot.cloud_runner.time.monotonic", side_effect=[0.0, 9999.0, 9999.0])

    runner = make_cloud_runner("env-id", poll_interval=0.0)
    result = runner("prompt", timeout=1)

    assert result["state"] == "FAILED"
    assert "timed out" in str(result.get("error", ""))


def test_make_cloud_runner_handles_transient_poll_error(mocker: Any) -> None:
    """Transient poll failure should be retried; success on second poll."""
    run_id = "cccccccc-dddd-eeee-ffff-000000000000"
    spawn_mock = MagicMock(returncode=0, stdout=_fake_oz_output(run_id), stderr="")
    bad_poll = MagicMock(returncode=1, stderr="network error")
    good_poll = MagicMock(returncode=0, stdout=json.dumps({"state": "SUCCEEDED"}))
    convo = {
        "steps": [
            {"messages": [{"role": "assistant", "content": [{"type": "text", "text": "done"}]}]}
        ]
    }
    convo_mock = MagicMock(returncode=0, stdout=json.dumps(convo))

    mocker.patch(
        "ptbot.cloud_runner.subprocess.run",
        side_effect=[spawn_mock, bad_poll, good_poll, convo_mock],
    )
    mocker.patch("ptbot.cloud_runner.time.sleep")
    mocker.patch(
        "ptbot.cloud_runner.time.monotonic", side_effect=[0.0, 0.0, 0.0, 0.0, 9999.0]
    )

    runner = make_cloud_runner("env-id", poll_interval=0.0)
    result = runner("prompt", timeout=3600)

    assert result["state"] == "SUCCEEDED"


# ---------------------------------------------------------------------------
# load_sweep_config
# ---------------------------------------------------------------------------


def test_load_sweep_config_returns_55_runs(toml_path: Path) -> None:
    """5 sectors × 11 years = 55 SweepRun objects."""
    runs, meta = load_sweep_config(toml_path)

    assert len(runs) == 55


def test_load_sweep_config_sectors(toml_path: Path) -> None:
    """All 5 sector names should appear in the run list."""
    runs, _ = load_sweep_config(toml_path)

    sector_names = {r.sector for r in runs}
    assert "Cybersecurity" in sector_names
    assert "EdTech" in sector_names
    assert "InsurTech" in sector_names
    assert "HR Tech" in sector_names
    assert "PropTech" in sector_names


def test_load_sweep_config_year_range(toml_path: Path) -> None:
    """Each sector should have runs for years 2016 through 2026 inclusive."""
    runs, _ = load_sweep_config(toml_path)

    years = {r.year for r in runs if r.sector == "Cybersecurity"}
    assert years == set(range(2016, 2027))


def test_load_sweep_config_meta(toml_path: Path) -> None:
    """Sweep metadata should contain expected keys."""
    _, meta = load_sweep_config(toml_path)

    assert meta.get("geography") == "United States"
    assert meta.get("start_year") == 2016
    assert meta.get("end_year") == 2026


def test_load_sweep_config_raises_without_sectors(tmp_path: Path) -> None:
    """Config without [[sectors]] entries should raise ValueError."""
    toml = tmp_path / "empty.toml"
    toml.write_text("[sweep]\ngeography = 'US'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least one"):
        load_sweep_config(toml)


def test_load_sweep_config_raises_on_missing_file() -> None:
    """Attempting to load a non-existent file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_sweep_config(Path("/nonexistent/sweep.toml"))


# ---------------------------------------------------------------------------
# _execute_pipeline
# ---------------------------------------------------------------------------


def test_execute_pipeline_succeeds(tmp_path: Path) -> None:
    """A successful pipeline run should return (sweep_run, True, <message>)."""
    calls: list[str] = []

    def fake_runner(prompt: str, timeout: int) -> dict[str, Any]:
        calls.append(prompt)
        if prompt.startswith("SCOUT_ID: press_news"):
            return {
                "state": "SUCCEEDED",
                "output": json.dumps(
                    [
                        {
                            "target": "SecureCo",
                            "acquirer": "BigDefense",
                            "date": "2020-01-15",
                            "deal_value": "$100M",
                            "multiples_disclosed": True,
                            "computed_multiples_available": False,
                            "multiples": ["4.0x EV/Revenue"],
                            "source_urls": ["https://example.com"],
                        }
                    ]
                ),
            }
        if prompt.startswith("SCOUT_ID:"):
            return {"state": "SUCCEEDED", "output": "[]"}
        if prompt.startswith("DEEP_DIVE_ID:"):
            return {"state": "SUCCEEDED", "output": "Analysis of SecureCo."}
        return {"state": "SUCCEEDED", "output": "# Final Report\n\nSecureCo qualified."}

    sweep_run = SweepRun(sector="Cybersecurity", year=2020, geography="United States")
    run_obj, success, msg = _execute_pipeline(sweep_run, tmp_path, fake_runner, timeout=30)

    assert success is True
    assert run_obj is sweep_run
    assert len(calls) == 8  # 4 scouts + 3 deep-dives + 1 QC


def test_execute_pipeline_returns_false_on_exception(tmp_path: Path) -> None:
    """Runner exceptions should produce (run, False, error_msg), not crash."""

    def crashing_runner(prompt: str, timeout: int) -> dict[str, Any]:
        raise RuntimeError("network down")

    sweep_run = SweepRun(sector="EdTech", year=2021, geography="United States")
    _, success, msg = _execute_pipeline(sweep_run, tmp_path, crashing_runner, timeout=1)

    assert success is False
    assert "network down" in msg


# ---------------------------------------------------------------------------
# sweep_main (CLI)
# ---------------------------------------------------------------------------


def test_sweep_main_dry_run(toml_path: Path, capsys: Any) -> None:
    """--dry-run should print run count and return 0 without executing pipelines."""
    rc = sweep_main(["--config", str(toml_path), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "55 pipelines" in captured.out
    assert "dry-run" in captured.out


def test_sweep_main_returns_1_for_missing_config() -> None:
    """sweep_main should return 1 when the config file is absent."""
    rc = sweep_main(["--config", "/nonexistent/config.toml"])

    assert rc == 1


def test_sweep_main_runs_with_stub_runner(toml_path: Path, mocker: Any) -> None:
    """sweep_main with a stubbed _execute_pipeline should complete successfully."""
    mocker.patch(
        "ptbot.sweep._execute_pipeline",
        side_effect=lambda run, base, runner, timeout: (run, True, "ok"),
    )

    rc = sweep_main(["--config", str(toml_path)])

    assert rc == 0


def test_sweep_main_prints_complete_line(toml_path: Path, mocker: Any, capsys: Any) -> None:
    """sweep_main should always emit a '[sweep] complete:' line."""
    mocker.patch(
        "ptbot.sweep._execute_pipeline",
        side_effect=lambda run, base, runner, timeout: (run, True, "ok"),
    )

    sweep_main(["--config", str(toml_path)])

    out = capsys.readouterr().out
    assert any("[sweep] complete:" in ln for ln in out.splitlines())


def test_sweep_main_returns_1_on_any_failure(toml_path: Path, mocker: Any) -> None:
    """When any pipeline fails, sweep_main should return 1."""
    call_count = 0

    def alternating(run: Any, base: Any, runner: Any, timeout: int) -> tuple[Any, bool, str]:
        nonlocal call_count
        call_count += 1
        success = call_count % 2 == 0  # odd jobs fail
        return run, success, "error" if not success else "ok"

    mocker.patch("ptbot.sweep._execute_pipeline", side_effect=alternating)

    rc = sweep_main(["--config", str(toml_path)])

    assert rc == 1
