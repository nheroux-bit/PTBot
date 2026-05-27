"""Tests for PTBot cost accounting (cost-accounting-001).

Covers models, estimation, runner instrumentation, orchestrator aggregation + warnings,
db schema migration + helpers, CLI flag, sweep budget config + tracking.
Target: >=85% coverage on new cost logic (models, runners cost paths, db cost, orch cost).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ptbot import cli, sweep
from ptbot.db import (
    get_industry_cost_summary,
    get_run_cost,
    insert_run,
    new_run_id,
    open_db,
    update_run_cost,
)
from ptbot.models import (
    CostBreakdown,
    ResearchParams,
    TokenUsage,
    estimate_cost,
)
from ptbot.orchestrator import _aggregate_costs, run_pipeline
from ptbot.runners import run_cloud_agent, run_local_agent

# ---------------------------------------------------------------------------
# Models + estimation (ca-1)
# ---------------------------------------------------------------------------


def test_token_usage_and_costbreakdown_validate() -> None:
    usage = TokenUsage(input_tokens=1200, output_tokens=650)
    cb = CostBreakdown(
        model="oz-default",
        usage=usage,
        estimated_cost_usd=0.042,
        input_cost_usd=0.003,
        output_cost_usd=0.039,
    )
    assert cb.usage.input_tokens == 1200
    assert cb.estimated_cost_usd > 0


def test_estimate_cost_heuristic_and_price_table() -> None:
    cb = estimate_cost("hello world " * 100, "result text " * 50)
    assert cb.model == "oz-default"
    assert cb.usage.input_tokens >= 1
    assert cb.usage.output_tokens >= 1
    assert 0 < cb.estimated_cost_usd < 1.0  # small prompt
    # table lookup (direct import to avoid runtime hack)
    from ptbot import models as _m

    assert "oz-default" in _m.PRICE_TABLE


def test_estimate_cost_fallback_on_empty() -> None:
    cb = estimate_cost("", "")
    assert cb.usage.input_tokens == 1
    assert cb.usage.output_tokens == 1


# ---------------------------------------------------------------------------
# Runner instrumentation (ca-1) - both local and cloud paths
# ---------------------------------------------------------------------------


@patch("ptbot.runners.subprocess.run")
def test_local_runner_attaches_cost(mock_run: Any) -> None:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"type": "agent", "text": "some output"}) + "\n"
    res = run_local_agent("a prompt here for tokens")
    assert "cost" in res
    assert res["cost"]["estimated_cost_usd"] >= 0
    assert res["cost"]["usage"]["input_tokens"] > 0


@patch("ptbot.runners.subprocess.run")
def test_cloud_runner_attaches_cost(mock_run: Any) -> None:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"type": "agent", "text": "cloud output"}) + "\n"
    res = run_cloud_agent("prompt for cloud cost")
    assert "cost" in res
    assert res["cost"]["model"] == "oz-default"


@patch("ptbot.runners.subprocess.run")
def test_runner_timeout_includes_cost(mock_run: Any) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=1)
    res = run_local_agent("timeout prompt", timeout=1)
    assert res["state"] == "TIMED_OUT"
    assert "cost" in res
    assert res["cost"]["estimated_cost_usd"] >= 0


# ---------------------------------------------------------------------------
# DB cost persistence + helpers (ca-2)
# ---------------------------------------------------------------------------


_PARAMS = ResearchParams(
    sector="TestSector", geography="US", start_date="2025-01-01", end_date="2025-12-31"
)


def test_open_db_migrates_cost_columns(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = open_db(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert "input_tokens" in cols
    assert "estimated_cost_usd" in cols
    assert "cost_model" in cols
    conn.close()


def test_insert_run_with_and_without_cost(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "c.db")
    rid1 = new_run_id()
    insert_run(conn, rid1, _PARAMS)  # no cost -> zeros
    rid2 = new_run_id()
    cost = estimate_cost("p" * 400, "o" * 200)
    insert_run(conn, rid2, _PARAMS, cost=cost)
    rows = conn.execute("SELECT run_id, estimated_cost_usd FROM runs ORDER BY timestamp").fetchall()
    assert rows[0][1] == 0.0
    assert rows[1][1] > 0.0
    conn.close()


def test_update_run_cost_and_get(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "c.db")
    rid = new_run_id()
    insert_run(conn, rid, _PARAMS)
    cost = estimate_cost("input " * 300, "output " * 100)
    update_run_cost(conn, rid, cost)
    fetched = get_run_cost(conn, rid)
    assert fetched is not None
    assert fetched["estimated_cost_usd"] == cost.estimated_cost_usd
    conn.close()


def test_industry_cost_summary_includes_budget_target(tmp_path: Path) -> None:
    conn = open_db(tmp_path / "c.db")
    rid = new_run_id()
    cost = estimate_cost("x" * 800, "y" * 300)
    insert_run(conn, rid, _PARAMS, cost=cost)
    summ = get_industry_cost_summary(conn, "TestSector", "US")
    assert summ["sector"] == "TestSector"
    assert summ["budget_target_usd"] == 50.0
    assert summ["total_cost_usd"] > 0
    assert "remaining_budget_usd" in summ
    assert "over_budget" in summ
    conn.close()


# ---------------------------------------------------------------------------
# Orchestrator aggregation + max_cost warning (ca-1/3/6)
# ---------------------------------------------------------------------------


def test_aggregate_costs_sums_and_fallback() -> None:
    r1 = type("R", (), {"cost": estimate_cost("a" * 100, "b" * 50)})()
    r2 = type("R", (), {"cost": None, "output": "c" * 200})()  # fallback path
    agg = _aggregate_costs([r1, r2])
    assert agg.estimated_cost_usd > 0
    assert agg.usage.input_tokens > 50


@patch("ptbot.orchestrator._load_default_runner")
def test_run_pipeline_returns_cost_and_respects_max_cost_warns(
    mock_load_runner: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_cost = estimate_cost("prompt" * 50, "out" * 30)

    class FakeRes:
        def __init__(self) -> None:
            self.state = "SUCCEEDED"
            self.output = "ok"
            self.run_id = "r1"
            self.run_url = ""
            self.error = None
            self.cost = fake_cost

    def fake_runner(p: str, t: int) -> dict[str, Any]:
        return {"state": "SUCCEEDED", "output": "ok", "cost": fake_cost.model_dump(mode="json")}

    mock_load_runner.return_value = fake_runner

    out = tmp_path / "out"
    paths = run_pipeline(
        _PARAMS,
        out,
        timeout=5,
        max_cost=0.0001,  # will trigger warning
    )
    assert paths.cost is not None
    assert paths.cost.estimated_cost_usd > 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "exceeds --max-cost" in captured.out


# ---------------------------------------------------------------------------
# CLI flag (ca-3)
# ---------------------------------------------------------------------------


def test_cli_parser_has_max_cost() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--sector",
            "X",
            "--geography",
            "Y",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--max-cost",
            "12.5",
        ]
    )
    assert args.max_cost == 12.5


# ---------------------------------------------------------------------------
# Sweep budget config + tracking (ca-3)
# ---------------------------------------------------------------------------


def test_sweep_config_accepts_budget_fields(tmp_path: Path) -> None:
    toml = tmp_path / "s.toml"
    toml.write_text("""
[sweep]
max_cost_per_run = 3.5
max_cost_per_industry = 42.0

[[markets]]
sector = "Fin"
geography = "US"
""")
    cfg = sweep.load_config(toml)
    assert cfg.sweep.max_cost_per_run == 3.5
    assert cfg.sweep.max_cost_per_industry == 42.0


@patch("ptbot.sweep.run_pipeline")
def test_run_one_returns_cost_and_forwards_max_cost(mock_run: Any) -> None:
    fake_paths = type("P", (), {"cost": estimate_cost("p", "o")})()
    mock_run.return_value = fake_paths
    mkt = sweep.MarketTarget(sector="S", geography="G")
    cfg = sweep.SweepConfig(
        markets=[mkt],
        sweep=sweep.SweepSettings(max_cost_per_run=10.0),
    )
    ok, c = sweep._run_one(
        mkt,
        "2025-01-01",
        "2025-12-31",
        config=cfg,
        db_path=Path("/tmp/dummy.db"),
        output_base=Path("/tmp"),
        runner=None,
    )
    assert ok
    assert c is not None
    mock_run.assert_called_once()
    # verify max_cost passed
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("max_cost") == 10.0
