"""Tests for cloud agent safeguards: kill-all, WIP cap, and timeout watchdog."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ptbot.cli import main
from ptbot.db import (
    count_active_cloud_runs,
    kill_all_active_cloud_runs,
    list_cloud_runs,
    open_db,
    register_cloud_dispatch,
    update_cloud_run,
)
from ptbot.sweep import MarketTarget, SweepConfig, SweepSettings, _watchdog_thread, run_sweep

# ---------------------------------------------------------------------------
# Shared DB fixture helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    open_db(db_path).close()
    return db_path


def _add_active_run(db_path: Path, oz_run_id: str) -> None:
    conn = open_db(db_path)
    register_cloud_dispatch(conn, oz_run_id, parent="test", run_url="https://example.com")
    conn.close()


def _add_terminal_run(db_path: Path, oz_run_id: str) -> None:
    conn = open_db(db_path)
    register_cloud_dispatch(conn, oz_run_id, parent="test")
    update_cloud_run(conn, oz_run_id, status="succeeded")
    conn.close()


# ---------------------------------------------------------------------------
# kill_all_active_cloud_runs (db.py)
# ---------------------------------------------------------------------------


def test_kill_all_empty_registry(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    conn = open_db(db_path)
    result = kill_all_active_cloud_runs(conn)
    conn.close()
    assert result == []


def test_kill_all_marks_active_runs_revoked(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "run-aaa")
    _add_active_run(db_path, "run-bbb")
    _add_terminal_run(db_path, "run-ccc")  # terminal — should not be touched

    conn = open_db(db_path)
    revoked = kill_all_active_cloud_runs(conn)
    conn.close()

    assert len(revoked) == 2
    assert {r["oz_run_id"] for r in revoked} == {"run-aaa", "run-bbb"}

    # Verify registry state
    conn = open_db(db_path)
    still_active = list_cloud_runs(conn, active_only=True)
    conn.close()
    assert still_active == []


def test_count_active_cloud_runs(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    conn = open_db(db_path)
    assert count_active_cloud_runs(conn) == 0
    conn.close()

    _add_active_run(db_path, "run-1")
    _add_active_run(db_path, "run-2")
    _add_terminal_run(db_path, "run-3")

    conn = open_db(db_path)
    assert count_active_cloud_runs(conn) == 2
    conn.close()


# ---------------------------------------------------------------------------
# ptbot cloud kill-all CLI
# ---------------------------------------------------------------------------


def test_cli_kill_all_dry_run_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = _make_db(tmp_path)
    rc = main(["cloud", "--db-path", str(db_path), "kill-all", "--dry-run"])
    assert rc == 0
    assert "no active" in capsys.readouterr().out.lower()


def test_cli_kill_all_dry_run_shows_active(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "run-abc123")
    rc = main(["cloud", "--db-path", str(db_path), "kill-all", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Would kill 1" in out
    assert "run-abc123" in out


def test_cli_kill_all_calls_kill_cloud_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "run-xyz")

    with patch("ptbot.runners.kill_cloud_run", return_value=(True, "killed")) as mock_kill:
        rc = main(["cloud", "--db-path", str(db_path), "kill-all"])

    assert rc == 0
    mock_kill.assert_called_once()
    out = capsys.readouterr().out
    assert "kill-all complete" in out


def test_cli_kill_all_handles_oz_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """kill-all should still mark runs revoked even if oz CLI fails."""
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "run-fail")

    with patch("ptbot.runners.kill_cloud_run", return_value=(False, "oz not found")):
        rc = main(["cloud", "--db-path", str(db_path), "kill-all"])

    assert rc == 0
    # Registry must be clean regardless
    conn = open_db(db_path)
    assert count_active_cloud_runs(conn) == 0
    conn.close()


# ---------------------------------------------------------------------------
# WIP cap (run_sweep)
# ---------------------------------------------------------------------------


def _minimal_config(db_path: Path, *, max_active: int = 10) -> SweepConfig:
    return SweepConfig(
        sweep=SweepSettings(
            years_back=1,
            db_path=str(db_path),
            max_active_cloud_runs=max_active,
        ),
        markets=[MarketTarget(sector="TestSector", geography="United States")],
    )


def test_wip_cap_blocks_when_at_limit(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    # Seed exactly max_active active runs
    for i in range(3):
        _add_active_run(db_path, f"existing-run-{i}")

    config = _minimal_config(db_path, max_active=3)

    with pytest.raises(RuntimeError, match="WIP cap reached"):
        run_sweep(config, cloud=True)


def test_wip_cap_passes_when_under_limit(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "one-existing")

    config = _minimal_config(db_path, max_active=10)

    # Should not raise — WIP cap not hit.  run_sweep will try to run the
    # actual pipeline which we mock out so the test stays fast.
    with patch("ptbot.sweep.run_pipeline") as mock_pipeline:
        mock_pipeline.return_value = None
        # run_sweep tries to call make_cloud_runner — skip by injecting a no-op runner
        run_sweep(config, cloud=True, runner=lambda p, t: {"state": "SUCCEEDED", "output": "x"})


def test_wip_cap_override_via_argument(tmp_path: Path) -> None:
    """max_active_cloud_runs kwarg overrides config value."""
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "run-a")
    _add_active_run(db_path, "run-b")

    config = _minimal_config(db_path, max_active=10)  # config says 10

    # But we pass max_active=2 override → 2 active >= 2 → raises
    with pytest.raises(RuntimeError, match="WIP cap reached"):
        run_sweep(config, cloud=True, max_active_cloud_runs=2)


# ---------------------------------------------------------------------------
# Timeout watchdog thread
# ---------------------------------------------------------------------------


def test_watchdog_kills_overdue_run(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)

    # Seed a run with a dispatched_at far in the past so it's overdue immediately
    conn = open_db(db_path)
    register_cloud_dispatch(conn, "overdue-run", parent="test")
    # Backdate dispatched_at to 3 hours ago
    from datetime import UTC, datetime, timedelta

    old_ts = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    conn.execute("UPDATE cloud_runs SET dispatched_at=? WHERE oz_run_id=?", (old_ts, "overdue-run"))
    conn.commit()
    conn.close()

    stop = threading.Event()
    killed_ids: list[str] = []

    def fake_kill(run_id: str, run_url: str = "") -> tuple[bool, str]:
        killed_ids.append(run_id)
        return True, f"killed {run_id}"

    with patch("ptbot.runners.kill_cloud_run", fake_kill):
        # poll_interval=0.01 so the watchdog executes without sleeping 60 s
        t = threading.Thread(
            target=_watchdog_thread,
            args=(db_path, 1, stop, 0.01),  # timeout=1s, poll every 10ms
            daemon=True,
        )
        t.start()
        time.sleep(0.1)  # let the thread complete at least one poll
        stop.set()
        t.join(timeout=2)

    assert "overdue-run" in killed_ids

    # Registry should be marked revoked
    conn = open_db(db_path)
    assert count_active_cloud_runs(conn) == 0
    conn.close()


def test_watchdog_does_not_kill_fresh_run(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    _add_active_run(db_path, "fresh-run")  # dispatched_at = now

    stop = threading.Event()
    killed_ids: list[str] = []

    def fake_kill(run_id: str, run_url: str = "") -> tuple[bool, str]:
        killed_ids.append(run_id)
        return True, f"killed {run_id}"

    with patch("ptbot.runners.kill_cloud_run", fake_kill):
        # poll_interval=0.01; timeout=3600s so no run will be overdue
        t = threading.Thread(
            target=_watchdog_thread,
            args=(db_path, 3600, stop, 0.01),
            daemon=True,
        )
        t.start()
        time.sleep(0.1)
        stop.set()
        t.join(timeout=2)

    # Fresh run should NOT be killed (not overdue)
    assert "fresh-run" not in killed_ids
