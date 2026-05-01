"""Tests for PTBot data models."""

from __future__ import annotations

import pytest

from ptbot.models import DealCandidate, ResearchParams


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
