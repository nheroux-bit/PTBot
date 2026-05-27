"""Tests for PTBot data models."""

from __future__ import annotations

import pytest

from ptbot.models import (
    ConfidenceLevel,
    DealCandidate,
    DealQualitySignals,
    QualityBreakdown,
    ResearchParams,
)


def test_research_params_reject_invalid_date() -> None:
    """ResearchParams should reject non-ISO date strings."""
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        ResearchParams(
            sector="AI",
            geography="US",
            start_date="01/01/2026",
            end_date="2026-05-01",
        )


def test_deal_candidate_accepts_json_arrays_as_tuples() -> None:
    """Agent JSON arrays should be accepted and stored as tuples."""
    deal = DealCandidate.model_validate(
        {
            "target": "A",
            "acquirer": "B",
            "multiples": ["5x revenue"],
            "source_urls": ["https://example.com"],
        }
    )

    assert deal.multiples == ("5x revenue",)
    assert deal.source_urls == ("https://example.com",)


def test_deal_qualifies_with_standard_multiple() -> None:
    """A listed standard valuation multiple should qualify a deal."""
    deal = DealCandidate(
        target="A",
        acquirer="B",
        computed_multiples_available=True,
        multiples=("EV/Revenue: 5.0x",),
    )

    assert deal.qualifies(1)
    assert not deal.qualifies(2)


def test_deal_qualifies_with_agent_style_standard_multiple_keys() -> None:
    """Agent JSON keys like EV_Revenue_approx and premium_to_close should qualify."""
    deal = DealCandidate(
        target="A",
        acquirer="B",
        multiples=("EV_Revenue_approx: 4.4x", "premium_to_close: 15%"),
    )

    assert deal.qualifies(2)


# --- quality-signals-001 tests ---


def test_confidence_level_enum() -> None:
    assert ConfidenceLevel.HIGH.value == "HIGH"
    assert ConfidenceLevel("MEDIUM") == ConfidenceLevel.MEDIUM


def test_quality_breakdown_defaults() -> None:
    b = QualityBreakdown()
    assert b.source_attribution == ""
    assert "multiples_quality" in QualityBreakdown.model_fields


def test_deal_quality_signals_defaults_and_effective() -> None:
    q = DealQualitySignals()
    assert q.overall_confidence == ConfidenceLevel.MEDIUM
    assert q.effective_confidence == ConfidenceLevel.MEDIUM
    q.human_confidence_override = ConfidenceLevel.HIGH
    assert q.effective_confidence == ConfidenceLevel.HIGH
    assert q.to_summitintel_confidence() == "HIGH"


def test_deal_quality_signals_roundtrip() -> None:
    q = DealQualitySignals(
        overall_confidence=ConfidenceLevel.LOW,
        confidence_score=0.3,
        breakdown=QualityBreakdown(source_attribution="weak press only"),
        citations=("https://sec.gov/...",),
        flags=("near_miss_geography",),
        human_notes="Manually reviewed 8-K",
    )
    # Use model_validate_json for proper enum/tuple coercion from serialized form
    q2 = DealQualitySignals.model_validate_json(q.model_dump_json())
    assert q2.effective_confidence == ConfidenceLevel.LOW
    assert "near_miss_geography" in q2.flags
