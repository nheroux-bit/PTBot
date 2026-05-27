"""Tests for PTBot orchestration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ptbot.models import AgentRunResult, AgentTask, DealCandidate, ResearchParams
from ptbot.orchestrator import (
    compile_agent_outputs,
    dedupe_deals,
    extract_json_array,
    filter_qualified_deals,
    load_attack_market_runner,
    normalize_result,
    run_pipeline,
    run_tasks,
)


def test_extract_json_array_from_fenced_output() -> None:
    """Agent JSON inside markdown fences should be parsed."""
    output = 'Here:\n```json\n[{"target":"A","acquirer":"B"}]\n```'

    parsed = extract_json_array(output)

    assert parsed == [{"target": "A", "acquirer": "B"}]


def test_dedupe_merges_multiples_and_sources() -> None:
    """Duplicate target/acquirer pairs should merge useful details."""
    first = DealCandidate(
        target="Dexibit",
        acquirer="accesso",
        multiples_disclosed=True,
        multiples=("5.1x EV/ARR",),
        source_urls=("https://a.example",),
    )
    second = DealCandidate(
        target="Dexibit",
        acquirer="accesso",
        computed_multiples_available=True,
        multiples=("7.1x EV/Revenue",),
        source_urls=("https://b.example",),
    )

    deduped = dedupe_deals([first, second])

    assert len(deduped) == 1
    assert deduped[0].multiples == ("5.1x EV/ARR", "7.1x EV/Revenue")
    assert deduped[0].source_urls == ("https://a.example", "https://b.example")


def test_dedupe_merges_parenthetical_and_legal_suffix_variants() -> None:
    """Duplicate names with location/legal suffix variants should merge."""
    first = DealCandidate(
        target="Performant Healthcare, Inc.",
        acquirer="Machinify (New Mountain Capital portfolio co.)",
        multiples=("4.4x EV/Revenue",),
    )
    second = DealCandidate(
        target="Performant Healthcare, Inc. (Plantation, FL)",
        acquirer="Machinify",
        multiples=("27.0x EV/EBITDA",),
    )

    deduped = dedupe_deals([first, second])

    assert len(deduped) == 1
    assert deduped[0].multiples == ("4.4x EV/Revenue", "27.0x EV/EBITDA")


def test_filter_qualified_deals_removes_deals_without_multiples() -> None:
    """Deals without disclosed or computable multiples are excluded."""
    qualified = DealCandidate(
        target="A",
        acquirer="B",
        multiples_disclosed=True,
        multiples=("5.0x EV/Revenue",),
        source_urls=("https://example.com",),
    )
    excluded = DealCandidate(target="C", acquirer="D")

    result = filter_qualified_deals([qualified, excluded], min_multiples=1)

    assert result == [qualified]


def test_filter_qualified_deals_rejects_non_standard_multiples() -> None:
    """Goodwill, patent, backlog, and note fields should not qualify a deal."""
    deals = [
        DealCandidate(
            target="Urbint",
            acquirer="Itron",
            computed_multiples_available=True,
            multiples=("goodwill_pct_of_purchase_price: 77%",),
        ),
        DealCandidate(
            target="XTEND",
            acquirer="JFB",
            computed_multiples_available=True,
            multiples=("EV/Backlog: 21x",),
        ),
        DealCandidate(
            target="Origin AI",
            acquirer="ADT",
            computed_multiples_available=True,
            multiples=("note: 200+ patent portfolio acquired",),
        ),
    ]

    assert filter_qualified_deals(deals, min_multiples=1) == []


def test_normalize_result_fills_defaults() -> None:
    """Raw runner results should normalize into validated agent results."""
    result = normalize_result({"state": "FAILED", "error": "boom"})

    assert result.state == "FAILED"
    assert result.output == ""
    assert result.error == "boom"


def test_run_tasks_converts_runner_exception_to_failed_result() -> None:
    """Runner exceptions should become failed task results, not crash the pool."""
    task = AgentTask(id="x", label="X", prompt="prompt")

    def broken_runner(prompt: str, timeout: int) -> dict[str, Any]:
        raise RuntimeError("agent failed")

    result = run_tasks([task], broken_runner, timeout=1)

    assert result["x"].state == "FAILED"
    assert result["x"].error == "agent failed"


def test_compile_agent_outputs_includes_failed_sections() -> None:
    """Compiled output should preserve failed-agent status for QC."""
    task = AgentTask(id="x", label="X", prompt="prompt")
    compiled = compile_agent_outputs(
        "Title", [task], {"x": AgentRunResult(state="FAILED", output="", error="timeout")}
    )

    assert "Status: FAILED" in compiled
    assert "timeout" in compiled


def test_load_attack_market_runner_missing_path(tmp_path: Path) -> None:
    """Missing attack.market orchestrator path should raise a clear error."""
    missing = tmp_path / "missing.py"
    with pytest.raises(FileNotFoundError, match="attack.market orchestrator not found"):
        load_attack_market_runner(missing)


def test_run_pipeline_with_fake_runner(tmp_path: Path) -> None:
    """Pipeline should write supporting outputs and final markdown using a fake runner."""
    calls: list[str] = []

    def fake_runner(prompt: str, timeout: int) -> dict[str, Any]:
        calls.append(prompt)
        if prompt.startswith("SCOUT_ID: press_news"):
            return {
                "state": "SUCCEEDED",
                "output": json.dumps(
                    [
                        {
                            "target": "Dexibit",
                            "acquirer": "accesso",
                            "date": "2026-03-30",
                            "deal_value": "$12.1M",
                            "multiples_disclosed": True,
                            "computed_multiples_available": True,
                            "multiples": ["5.1x EV/ARR"],
                            "source_urls": ["https://example.com/rns"],
                        }
                    ]
                ),
            }
        if prompt.startswith("SCOUT_ID:"):
            return {"state": "SUCCEEDED", "output": "[]"}
        if prompt.startswith("DEEP_DIVE_ID:"):
            return {"state": "SUCCEEDED", "output": "Deep dive includes Dexibit."}
        return {"state": "SUCCEEDED", "output": "# Final\n\nDexibit qualified."}

    params = ResearchParams(
        sector="AI",
        geography="Orlando, FL",
        start_date="2025-01-01",
        end_date="2026-05-01",
    )

    paths = run_pipeline(params, tmp_path, runner=fake_runner, timeout=1)

    assert paths.final_markdown.read_text(encoding="utf-8").startswith("# Final")
    assert paths.qualified_deals.exists()
    assert len(calls) == 8


# ---------------------------------------------------------------------------
# Runner selection / attack.market fallback
# ---------------------------------------------------------------------------


def test_load_attack_market_runner_raises_when_not_found(tmp_path: Path) -> None:
    from ptbot.orchestrator import load_attack_market_runner

    nonexistent = tmp_path / "does-not-exist.py"
    with pytest.raises(FileNotFoundError, match="attack.market orchestrator not found"):
        load_attack_market_runner(nonexistent)


def test_default_runner_falls_back_to_local_when_attack_market_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_load_default_runner falls back to bundled runner when attack.market is missing."""
    from ptbot import orchestrator as orch

    # Force the attack.market load to fail
    monkeypatch.setattr(
        orch,
        "load_attack_market_runner",
        lambda p=None: (_ for _ in ()).throw(FileNotFoundError("nope")),
    )

    runner = orch._load_default_runner()
    assert runner is orch._run_local_agent
