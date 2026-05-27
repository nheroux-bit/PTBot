"""Self-contained Oz agent runners for PTBot.

Provides local and cloud variants of the runner interface so PTBot works
in cloud environments where the attack.market skill may not be installed.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
        return {
            "state": "TIMED_OUT",
            "output": "",
            "run_id": "",
            "run_url": "",
            "error": f"Exceeded {timeout}s",
        }
    output, run_id, run_url = _parse_oz_output(result.stdout)
    state = "SUCCEEDED" if result.returncode == 0 and output else "FAILED"
    return {
        "state": state,
        "output": output,
        "run_id": run_id,
        "run_url": run_url,
        "exit_code": result.returncode,
    }


# ---------------------------------------------------------------------------
# Cloud runner  (oz agent run-cloud) + control plane registration
# ---------------------------------------------------------------------------


def _extract_run_started(stdout: str) -> tuple[str, str]:
    """Return (run_id, run_url) from the first run_started event seen (or empty)."""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "system" and msg.get("event_type") == "run_started":
            return msg.get("run_id", ""), msg.get("run_url", "")
    return "", ""


def run_cloud_agent(
    prompt: str,
    timeout: int = 900,
    *,
    environment: str | None = None,
    registry_db_path: Path | None = None,
    parent_context: str = "",
) -> dict[str, Any]:
    """Dispatch a cloud Oz agent and return a normalised result dict.

    Calls ``oz agent run-cloud`` as a subprocess. The optional *environment*
    argument maps to the ``-e / --environment`` flag.

    When *registry_db_path* is provided, the dispatch is registered in the
    cloud control plane (cloud-control-001) as soon as the oz "run_started"
    NDJSON event is observed. This is the critical path for surviving parent
    process death (firedrill root cause). Registration is early and idempotent.

    *parent_context* (e.g. "sweep:fintech:2025") is stored for observability.
    Cost estimate (when cost-accounting present in result) is also recorded.
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

    # Fast path when no registry requested (keeps all existing tests + non-cloud
    # usages using the original simple subprocess.run; no behavior change).
    if registry_db_path is None:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "state": "TIMED_OUT",
                "output": "",
                "run_id": "",
                "run_url": "",
                "error": f"Exceeded {timeout}s",
            }
        output, run_id, run_url = _parse_oz_output(result.stdout)
        state = "SUCCEEDED" if result.returncode == 0 and output else "FAILED"
        return {
            "state": state,
            "output": output,
            "run_id": run_id,
            "run_url": run_url,
            "exit_code": result.returncode,
        }

    # Live streaming path for early registration (safety-critical, only when
    # registry_db_path provided by sweep/dashboard with real DB).
    # We must observe the oz_run_id *before* the parent can die.
    stdout_lines: list[str] = []
    oz_run_id = ""
    oz_run_url = ""
    state = "FAILED"
    exit_code = -1
    error: str | None = None
    output = ""
    start = time.time()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None

        while True:
            if proc.poll() is not None:
                break
            line = proc.stdout.readline()
            if line:
                stdout_lines.append(line)
                # Early detection + register as soon as oz hands us the id
                if not oz_run_id:
                    rid, rurl = _extract_run_started(line)
                    if rid:
                        oz_run_id = rid
                        oz_run_url = rurl
                        try:
                            from . import (
                                db as _db,  # local import to avoid hard dep for non-registry users
                            )

                            conn = _db.open_db(registry_db_path)
                            excerpt = prompt[:200] + ("..." if len(prompt) > 200 else "")
                            _db.register_cloud_dispatch(
                                conn,
                                oz_run_id,
                                parent=parent_context or "cloud-dispatch",
                                environment=environment,
                                cost_estimate_usd=None,  # populated on completion if cost present
                                run_url=oz_run_url,
                                prompt_excerpt=excerpt,
                            )
                            # Mark running now that we have confirmation it launched
                            _db.update_cloud_run(conn, oz_run_id, status="running")
                            conn.close()
                        except (
                            Exception
                        ) as reg_exc:  # noqa: BLE001 - registry must never kill the dispatch
                            # Log to stderr but do not fail the agent run (fail-open for liveness)
                            print(
                                f"[cloud-control] registry registration warning: {reg_exc}",
                                file=__import__("sys").stderr,
                            )  # pragma: no cover
            elapsed = time.time() - start
            if elapsed > timeout:
                proc.kill()
                error = f"Exceeded {timeout}s"
                state = "TIMED_OUT"
                exit_code = proc.returncode if proc.returncode is not None else -1
                break
            # tiny sleep to avoid busy loop on no output
            if not line:
                time.sleep(0.02)

        # Drain any remaining
        remaining = proc.stdout.read() or ""
        if remaining:
            stdout_lines.append(remaining)

        exit_code = proc.returncode if proc.returncode is not None else -1
        full_stdout = "".join(stdout_lines)
        output, parsed_id, parsed_url = _parse_oz_output(full_stdout)
        if parsed_id and not oz_run_id:
            oz_run_id = parsed_id
            oz_run_url = parsed_url
        if state != "TIMED_OUT":
            state = "SUCCEEDED" if exit_code == 0 and output else "FAILED"

        # Final registration / update (covers cases with no early event + post-completion cost)
        if oz_run_id:
            try:
                from . import db as _db

                conn = _db.open_db(registry_db_path)
                excerpt = prompt[:200] + ("..." if len(prompt) > 200 else "")
                # Ensure registered even if no early event (defensive)
                _db.register_cloud_dispatch(
                    conn,
                    oz_run_id,
                    parent=parent_context or "cloud-dispatch",
                    environment=environment,
                    run_url=oz_run_url or parsed_url,
                    prompt_excerpt=excerpt,
                )
                final_status = (
                    "succeeded"
                    if state == "SUCCEEDED"
                    else ("timed_out" if state == "TIMED_OUT" else "failed")
                )
                # If cost present in a future extended result, it would be here; for now None
                _db.update_cloud_run(
                    conn,
                    oz_run_id,
                    status=final_status,
                    exit_code=exit_code,
                    error=error,
                )
                conn.close()
            except Exception as reg_exc:  # noqa: BLE001
                print(
                    f"[cloud-control] final registry update warning: {reg_exc}",
                    file=__import__("sys").stderr,
                )  # pragma: no cover

        return {
            "state": state,
            "output": output,
            "run_id": oz_run_id,
            "run_url": oz_run_url,
            "exit_code": exit_code,
            "error": error,
        }

    except Exception as exc:  # noqa: BLE001 - boundary
        # Note: manual timeout handling (time.time() loop) means
        # subprocess.TimeoutExpired is never raised here (dead branch per Greptile review).
        state = "FAILED"
        error = str(exc)

    # Fallback path (should rarely hit)
    full_stdout = "".join(stdout_lines)
    output, rid, rurl = _parse_oz_output(full_stdout)
    if rid and not oz_run_id:
        oz_run_id = rid
        oz_run_url = rurl
    if oz_run_id:
        try:
            from . import db as _db

            conn = _db.open_db(registry_db_path)
            _db.register_cloud_dispatch(
                conn,
                oz_run_id,
                parent=parent_context or "cloud-dispatch",
                environment=environment,
                run_url=oz_run_url,
                prompt_excerpt=prompt[:200],
            )
            _db.update_cloud_run(
                conn, oz_run_id, status=state.lower(), exit_code=exit_code, error=error
            )
            conn.close()
        except Exception:
            pass  # pragma: no cover

    return {
        "state": state,
        "output": output,
        "run_id": oz_run_id,
        "run_url": oz_run_url,
        "exit_code": exit_code,
        "error": error,
    }


def kill_cloud_run(oz_run_id: str, run_url: str = "") -> tuple[bool, str]:
    """Best-effort revocation of a cloud Oz run (cloud-control-001).

    Tries several plausible `oz` CLI kill/revoke surfaces (the exact command
    is still stabilizing post-firedrill). Returns (success, human_message).

    On complete failure, the message includes the run_url so the operator
    can finish revocation in the Oz web UI. The registry is updated by the
    caller (CLI or dashboard) after this returns.

    Never raises; safe for use in status/kill UIs.
    """
    if not oz_run_id or oz_run_id.startswith(("pending-", "launch-failed-")):
        return False, f"No killable oz run_id (launch did not produce a run id). {run_url}"

    candidates = [
        ["oz", "agent", "kill", oz_run_id],
        ["oz", "agent", "kill", "--run-id", oz_run_id],
        ["oz", "agent", "revoke", oz_run_id],
        ["oz", "cloud", "kill", oz_run_id],
        ["oz", "run", "kill", oz_run_id],
    ]
    for cmd in candidates:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                msg = proc.stdout.strip() or proc.stderr.strip()
                return True, f"Revoked via '{' '.join(cmd)}': {msg}".strip()
        except FileNotFoundError:
            return False, "oz CLI not found in PATH. Use the Oz dashboard or ensure oz is on PATH."
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    hint = f" run_url={run_url}" if run_url else ""
    return False, (
        f"Automatic revocation via oz CLI failed for {oz_run_id}. "
        f"Terminate manually in the Oz dashboard.{hint}"
    )


# ---------------------------------------------------------------------------
# Factory for sweep injection
# ---------------------------------------------------------------------------

# The Runner type matches orchestrator.Runner: Callable[[str, int], dict].
Runner = Callable[[str, int], dict[str, Any]]


def make_cloud_runner(
    environment: str | None = None,
    *,
    registry_db_path: Path | None = None,
    parent_context: str = "",
) -> Runner:
    """Return a Runner closure that dispatches to ``oz agent run-cloud``.

    Pass the returned callable as the *runner* argument to ``run_pipeline()``
    or ``run_sweep()`` to use cloud agents for all pipeline tasks.

    Registry + parent context (cloud-control-001) are captured in the closure
    so every dispatch from this runner instance is registered in the control
    plane (for kill/status even after parent death). Callers in sweep.py
    and tests are expected to pass registry_db_path when available.

    Args:
        environment: Optional Oz environment ID (``-e / --environment``).
        registry_db_path: If provided, every cloud dispatch is registered
            immediately on run_started for the control plane.
        parent_context: Human-readable parent (e.g. "sweep:fintech-us:2025")
            stored in the registry for filtering/visibility.
    """

    def _runner(prompt: str, timeout: int) -> dict[str, Any]:
        return run_cloud_agent(
            prompt,
            timeout,
            environment=environment,
            registry_db_path=registry_db_path,
            parent_context=parent_context,
        )

    return _runner
