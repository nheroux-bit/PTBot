"""Cloud runner for PTBot using the Oz CLI (oz-preview)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "ERRORED"})
Runner = Callable[[str, int], dict[str, Any]]

# oz-preview agent run-cloud prints human-readable text, not JSON.
# Pattern: "Spawned ambient agent with run ID: <uuid>"
_RUN_ID_RE = re.compile(r"run ID:\s+([0-9a-f-]{36})", re.IGNORECASE)


def _spawn_cloud_agent(prompt: str, environment_id: str) -> str:
    """Spawn an Oz cloud agent and return its run ID.

    ``oz-preview agent run-cloud`` prints human-readable text regardless of
    ``--output-format``; we extract the run ID via regex.
    """
    result = subprocess.run(
        [
            "oz-preview",
            "agent",
            "run-cloud",
            "--prompt",
            prompt,
            "--environment",
            environment_id,
            "--no-snapshot",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"spawn failed (exit {result.returncode}): {result.stderr.strip()}")
    match = _RUN_ID_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"no run ID found in spawn output: {result.stdout[:300]!r}")
    return match.group(1)


def _get_run_state(run_id: str) -> str:
    """Return the current state string for a cloud agent run."""
    result = subprocess.run(
        ["oz-preview", "run", "get", run_id, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"state poll failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"state poll returned non-JSON: {result.stdout[:200]}") from exc
    return str(data.get("state", "UNKNOWN"))


def _extract_agent_output(run_id: str) -> str:
    """Extract the final assistant text output from a completed run's conversation."""
    result = subprocess.run(
        [
            "oz-preview",
            "run",
            "get",
            run_id,
            "--conversation",
            "--output-format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""

    # Walk conversation steps → messages → content items to find last assistant text.
    last_text = ""
    for step in data.get("steps", []):
        for msg in step.get("messages", []):
            if msg.get("role") != "assistant":
                continue
            for item in msg.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        last_text = text
    return last_text


def make_cloud_runner(
    environment_id: str,
    poll_interval: float = 20.0,
) -> Runner:
    """Return a runner that dispatches each prompt to an Oz cloud agent and waits.

    The returned callable has signature ``runner(prompt: str, timeout: int) -> dict``
    and is compatible with ``orchestrator.run_tasks`` / ``normalize_result``.
    """

    def runner(prompt: str, timeout: int) -> dict[str, Any]:
        # --- Spawn ---
        try:
            run_id = _spawn_cloud_agent(prompt, environment_id)
        except Exception as exc:  # noqa: BLE001
            return {"state": "FAILED", "output": "", "run_id": "", "run_url": "", "error": str(exc)}

        run_url = f"https://app.warp.dev/agent/{run_id}"

        # --- Poll until terminal state or timeout ---
        deadline = time.monotonic() + timeout
        state = "INPROGRESS"
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            try:
                state = _get_run_state(run_id)
            except Exception:  # noqa: BLE001
                continue  # transient poll failure — keep waiting
            if state in TERMINAL_STATES:
                break

        if state not in TERMINAL_STATES:
            return {
                "state": "FAILED",
                "output": "",
                "run_id": run_id,
                "run_url": run_url,
                "error": f"timed out after {timeout}s (last state: {state})",
            }

        # --- Extract output ---
        output = _extract_agent_output(run_id)
        return {
            "state": state,
            "output": output,
            "run_id": run_id,
            "run_url": run_url,
            "error": None if state == "SUCCEEDED" else state,
        }

    return runner
