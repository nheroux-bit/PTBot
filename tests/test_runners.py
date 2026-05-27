"""Tests for ptbot.runners — local and cloud Oz agent runners."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ptbot.runners import (
    _parse_oz_output,
    make_cloud_runner,
    run_cloud_agent,
    run_local_agent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


def _ndjson(*lines: dict[str, Any]) -> str:
    return "\n".join(json.dumps(line) for line in lines) + "\n"


# ---------------------------------------------------------------------------
# _parse_oz_output
# ---------------------------------------------------------------------------


def test_parse_oz_output_extracts_agent_text() -> None:
    stdout = _ndjson(
        {"type": "system", "event_type": "run_started", "run_id": "r1", "run_url": "https://u"},
        {"type": "agent", "text": "Hello "},
        {"type": "agent", "text": "world"},
        {"type": "system", "event_type": "run_completed"},
    )
    text, run_id, run_url = _parse_oz_output(stdout)
    assert text == "Hello world"
    assert run_id == "r1"
    assert run_url == "https://u"


def test_parse_oz_output_plain_text_line_is_treated_as_agent_text() -> None:
    text, _, _ = _parse_oz_output("plain line\n")
    assert text == "plain line"


def test_parse_oz_output_empty_stdout() -> None:
    text, run_id, run_url = _parse_oz_output("")
    assert text == ""
    assert run_id == ""
    assert run_url == ""


def test_parse_oz_output_strips_whitespace() -> None:
    stdout = _ndjson({"type": "agent", "text": "  result  "})
    text, _, _ = _parse_oz_output(stdout)
    assert text == "result"


# ---------------------------------------------------------------------------
# run_local_agent
# ---------------------------------------------------------------------------


def test_run_local_agent_succeeded() -> None:
    stdout = _ndjson(
        {"type": "system", "event_type": "run_started", "run_id": "rid", "run_url": "url"},
        {"type": "agent", "text": "output text"},
    )
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)) as mock_run:
        result = run_local_agent("my prompt", timeout=60)

    cmd = mock_run.call_args[0][0]
    assert cmd[:4] == ["oz", "agent", "run", "--prompt"]
    assert cmd[4] == "my prompt"
    assert "--output-format" in cmd
    assert result["state"] == "SUCCEEDED"
    assert result["output"] == "output text"
    assert result["run_id"] == "rid"


def test_run_local_agent_failed_on_nonzero_exit() -> None:
    stdout = _ndjson({"type": "agent", "text": "partial"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout, returncode=1)):
        result = run_local_agent("prompt")
    assert result["state"] == "FAILED"


def test_run_local_agent_failed_on_empty_output() -> None:
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc("")):
        result = run_local_agent("prompt")
    assert result["state"] == "FAILED"


def test_run_local_agent_timeout() -> None:
    with patch(
        "ptbot.runners.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="oz", timeout=1),
    ):
        result = run_local_agent("prompt", timeout=1)
    assert result["state"] == "TIMED_OUT"
    assert "1s" in result["error"]


# ---------------------------------------------------------------------------
# run_cloud_agent
# ---------------------------------------------------------------------------


def test_run_cloud_agent_succeeded_no_environment() -> None:
    stdout = _ndjson({"type": "agent", "text": "cloud output"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)) as mock_run:
        result = run_cloud_agent("prompt", 30)

    cmd = mock_run.call_args[0][0]
    assert cmd[:5] == ["oz", "agent", "run-cloud", "--prompt", "prompt"]
    assert "--environment" not in cmd
    assert result["state"] == "SUCCEEDED"
    assert result["output"] == "cloud output"


def test_run_cloud_agent_includes_environment_flag() -> None:
    stdout = _ndjson({"type": "agent", "text": "ok"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)) as mock_run:
        run_cloud_agent("p", 30, environment="env-abc")

    cmd = mock_run.call_args[0][0]
    env_idx = cmd.index("--environment")
    assert cmd[env_idx + 1] == "env-abc"


def test_run_cloud_agent_timeout() -> None:
    with patch(
        "ptbot.runners.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="oz", timeout=5),
    ):
        result = run_cloud_agent("p", timeout=5)
    assert result["state"] == "TIMED_OUT"
    assert "5s" in result["error"]


def test_run_cloud_agent_failed_on_nonzero_exit() -> None:
    stdout = _ndjson({"type": "agent", "text": "err"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout, returncode=1)):
        result = run_cloud_agent("p")
    assert result["state"] == "FAILED"


# ---------------------------------------------------------------------------
# make_cloud_runner
# ---------------------------------------------------------------------------


def test_make_cloud_runner_returns_callable() -> None:
    runner = make_cloud_runner()
    assert callable(runner)


def test_make_cloud_runner_passes_environment_to_cloud_agent() -> None:
    stdout = _ndjson({"type": "agent", "text": "hi"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)) as mock_run:
        runner = make_cloud_runner(environment="my-env")
        runner("prompt", 60)

    cmd = mock_run.call_args[0][0]
    assert "--environment" in cmd
    assert cmd[cmd.index("--environment") + 1] == "my-env"


def test_make_cloud_runner_no_environment_omits_flag() -> None:
    stdout = _ndjson({"type": "agent", "text": "hi"})
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)) as mock_run:
        runner = make_cloud_runner()
        runner("prompt", 60)

    cmd = mock_run.call_args[0][0]
    assert "--environment" not in cmd


def test_make_cloud_runner_result_is_normalizable() -> None:
    """Runner output should be consumable by orchestrator.normalize_result."""
    from ptbot.orchestrator import normalize_result

    stdout = _ndjson(
        {"type": "system", "event_type": "run_started", "run_id": "r", "run_url": "u"},
        {"type": "agent", "text": "answer"},
    )
    with patch("ptbot.runners.subprocess.run", return_value=_make_proc(stdout)):
        runner = make_cloud_runner()
        raw = runner("p", 30)

    result = normalize_result(raw)
    assert result.state == "SUCCEEDED"
    assert result.output == "answer"


# ---------------------------------------------------------------------------
# Streaming cloud runner with early registry registration (cloud-control-001)
# ---------------------------------------------------------------------------


def test_run_cloud_agent_with_registry_db_path_registers_early(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Streaming path with registry_db_path must register early on run_started event."""
    from ptbot import db as _db

    registry_db = tmp_path / "reg.db"
    conn = _db.open_db(registry_db)
    conn.close()

    # Simulate NDJSON that delivers run_started very early
    ndjson = (
        '{"type":"system","event_type":"run_started","run_id":"oz-early-123","run_url":"https://u"}\n'
        '{"type":"agent","text":"some output"}\n'
    )

    class FakeProc:
        def __init__(self) -> None:
            self._lines = ndjson.splitlines(keepends=True)
            self.returncode = 0
            self.stdout = self

        def poll(self) -> int | None:
            return 0 if not self._lines else None

        def readline(self) -> str:
            return self._lines.pop(0) if self._lines else ""

        def read(self) -> str:
            return ""

    monkeypatch.setattr("ptbot.runners.subprocess.Popen", lambda *a, **k: FakeProc())

    captured: list[dict] = []

    orig_register = _db.register_cloud_dispatch
    orig_update = _db.update_cloud_run

    def spy_register(c, run_id, **kwargs):  # type: ignore[no-untyped-def]
        captured.append({"run_id": run_id, "kwargs": kwargs})
        return orig_register(c, run_id, **kwargs)

    def spy_update(c, run_id, status):  # type: ignore[no-untyped-def]
        captured.append({"update": (run_id, status)})
        return orig_update(c, run_id, status)

    monkeypatch.setattr(_db, "register_cloud_dispatch", spy_register)
    monkeypatch.setattr(_db, "update_cloud_run", spy_update)

    result = run_cloud_agent(
        "prompt with registry",
        timeout=5,
        registry_db_path=registry_db,
        parent_context="sweep:test:2026",
        environment="env-xyz",
    )

    assert result["run_id"] == "oz-early-123"
    assert any(c.get("run_id") == "oz-early-123" for c in captured)
