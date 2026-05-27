"""Self-contained Oz agent runners for PTBot.

Provides local and cloud variants of the runner interface so PTBot works
in cloud environments where the attack.market skill may not be installed.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from .models import estimate_cost

# ---------------------------------------------------------------------------
# NDJSON output parsing (shared by local and cloud runners)
# ---------------------------------------------------------------------------


def _parse_oz_output(stdout: str) -> tuple[str, str, str]:
    """Parse NDJSON streamed output from ``oz agent run`` / ``oz agent run-cloud``.

    Returns ``(text_output, run_id, run_url)``.

    Each line is one of:
      {"type":"system","event_type":"run_started","run_id":"...","run_url":"..."}
      {"type":"agent","text":"..."}
      {"type":"system","event_type":"run_completed",...}
    Non-JSON lines are treated as plain agent text.
    """
    text_parts: list[str] = []
    run_id = ""
    run_url = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            text_parts.append(line)
            continue
        if msg.get("type") == "agent":
            text_parts.append(msg.get("text", ""))
        elif msg.get("type") == "system" and msg.get("event_type") == "run_started":
            run_id = msg.get("run_id", "")
            run_url = msg.get("run_url", "")
    return "".join(text_parts).strip(), run_id, run_url


# ---------------------------------------------------------------------------
# Local runner  (oz agent run)
# ---------------------------------------------------------------------------


def run_local_agent(prompt: str, timeout: int = 900) -> dict[str, Any]:
    """Run a local Oz agent and return a normalised result dict.

    Calls ``oz agent run`` as a subprocess, streams NDJSON output, and
    returns a dict compatible with ``orchestrator.normalize_result()``.
    """
    cmd = ["oz", "agent", "run", "--prompt", prompt, "--output-format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        cost = estimate_cost(prompt, "")
        return {
            "state": "TIMED_OUT",
            "output": "",
            "run_id": "",
            "run_url": "",
            "error": f"Exceeded {timeout}s",
            "cost": cost.model_dump(mode="json"),
        }
    output, run_id, run_url = _parse_oz_output(result.stdout)
    state = "SUCCEEDED" if result.returncode == 0 and output else "FAILED"
    cost = estimate_cost(prompt, output)  # vBRIEF ca-1 instrumentation
    return {
        "state": state,
        "output": output,
        "run_id": run_id,
        "run_url": run_url,
        "exit_code": result.returncode,
        "cost": cost.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Cloud runner  (oz agent run-cloud)
# ---------------------------------------------------------------------------


def run_cloud_agent(
    prompt: str,
    timeout: int = 900,
    *,
    environment: str | None = None,
) -> dict[str, Any]:
    """Dispatch a cloud Oz agent and return a normalised result dict.

    Calls ``oz agent run-cloud`` as a subprocess. The optional *environment*
    argument maps to the ``-e / --environment`` flag that selects which Oz
    cloud environment the agent runs in.
    """
    cmd = [
        "oz",
        "agent",
        "run-cloud",
        "--prompt",
        prompt,
        "--output-format",
        "json",
    ]
    if environment:
        cmd += ["--environment", environment]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        cost = estimate_cost(prompt, "")
        return {
            "state": "TIMED_OUT",
            "output": "",
            "run_id": "",
            "run_url": "",
            "error": f"Exceeded {timeout}s",
            "cost": cost.model_dump(mode="json"),
        }
    output, run_id, run_url = _parse_oz_output(result.stdout)
    state = "SUCCEEDED" if result.returncode == 0 and output else "FAILED"
    cost = estimate_cost(prompt, output)  # vBRIEF ca-1 instrumentation (cloud path)
    return {
        "state": state,
        "output": output,
        "run_id": run_id,
        "run_url": run_url,
        "exit_code": result.returncode,
        "cost": cost.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Factory for sweep injection
# ---------------------------------------------------------------------------

# The Runner type matches orchestrator.Runner: Callable[[str, int], dict].
Runner = Callable[[str, int], dict[str, Any]]


def make_cloud_runner(environment: str | None = None) -> Runner:
    """Return a Runner closure that dispatches to ``oz agent run-cloud``.

    Pass the returned callable as the *runner* argument to ``run_pipeline()``
    or ``run_sweep()`` to use cloud agents for all pipeline tasks.

    Args:
        environment: Optional Oz environment ID (``-e / --environment``).
    """

    def _runner(prompt: str, timeout: int) -> dict[str, Any]:
        return run_cloud_agent(prompt, timeout, environment=environment)

    return _runner
