"""Tests for PTBot prompt generation."""

from ptbot.models import DealCandidate, ResearchParams
from ptbot.prompt_builder import (
    build_config,
    build_pass1_tasks,
    build_pass2_tasks,
    build_qc_prompt,
    horizon_instruction,
    source_hints_for_geography,
)


def test_orlando_prompts_include_local_sources() -> None:
    """Orlando geography should inject Orlando-specific sources."""
    params = ResearchParams(
        sector="AI",
        geography="Orlando, FL",
        start_date="2025-01-01",
        end_date="2026-05-01",
    )

    prompts = "\n".join(task.prompt for task in build_pass1_tasks(params))

    assert "Orlando Business Journal" in prompts
    assert "SCOUT_ID: press_news" in prompts
    assert "Chunk the search by calendar quarter" in prompts
    assert "Do not treat goodwill %" in prompts
    assert "prefer target headquarters/location" in prompts


def test_short_horizon_uses_direct_search_instruction() -> None:
    """Short windows should not trigger quarterly chunking."""
    instruction = horizon_instruction("2026-04-01", "2026-05-01")

    assert "Search the full window directly" in instruction


def test_pass2_prompts_include_qualified_manifest() -> None:
    """Deep-dive agents should receive the qualified deal manifest."""
    params = ResearchParams(
        sector="AI",
        geography="US",
        start_date="2026-01-01",
        end_date="2026-05-01",
    )
    deal = DealCandidate(
        target="Dexibit",
        acquirer="accesso",
        multiples_disclosed=True,
        multiples=("5.1x EV/ARR",),
        source_urls=("https://example.com",),
    )

    tasks = build_pass2_tasks(params, [deal])

    assert len(tasks) == 3
    assert all("Dexibit" in task.prompt for task in tasks)
    assert all(task.prompt.startswith("DEEP_DIVE_ID:") for task in tasks)
    assert all("Deduplicate repeated target/acquirer variants" in task.prompt for task in tasks)


def test_source_hints_cover_major_geographies() -> None:
    """Known geographies should return tailored source hints."""
    assert "Crain's Chicago Business" in source_hints_for_geography("Chicago")
    assert "Boston Business Journal" in source_hints_for_geography("Boston")
    assert "local business journals" in source_hints_for_geography("Remote")


def test_qc_prompt_and_config_include_scope() -> None:
    """QC prompt and config preview should include the requested scope."""
    params = ResearchParams(
        sector="AI",
        geography="Orlando, FL",
        start_date="2026-01-01",
        end_date="2026-05-01",
    )

    prompt = build_qc_prompt(params, "compiled")
    config = build_config(params)

    assert "Orlando, FL" in prompt
    assert "Goodwill %" in prompt
    assert "Exclude deals without standard multiples" in prompt
    assert config["params"]["geography"] == "Orlando, FL"  # type: ignore[index]
