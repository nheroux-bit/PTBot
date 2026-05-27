"""Validated data models for PTBot."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchParams(BaseModel):
    """User-provided research scope for a precedent transaction run."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sector: str = Field(..., min_length=1)
    geography: str = Field(..., min_length=1)
    start_date: str = Field(..., min_length=10)
    end_date: str = Field(..., min_length=10)
    min_multiples: int = Field(default=1, ge=1)
    deal_size_min: str | None = None
    deal_size_max: str | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_iso_date(cls, value: str) -> str:
        """Validate YYYY-MM-DD date strings without coercing to date objects."""
        parts = value.split("-")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("date must use YYYY-MM-DD format")
        year, month, day = (int(part) for part in parts)
        if year < 1900 or not 1 <= month <= 12 or not 1 <= day <= 31:
            raise ValueError("date is outside accepted range")
        return value


class AgentTask(BaseModel):
    """A single Oz agent prompt."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)


class DealCandidate(BaseModel):
    """Candidate acquisition identified by a Pass 1 scout."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    target: str = Field(..., min_length=1)
    acquirer: str = Field(..., min_length=1)
    date: str | None = None
    deal_value: str | None = None
    multiples_disclosed: bool = False
    computed_multiples_available: bool = False
    multiples: tuple[str, ...] = Field(default_factory=tuple)
    source_urls: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("multiples", "source_urls", mode="before")
    @classmethod
    def tuple_from_json_array(cls, value: Any) -> tuple[str, ...]:
        """Accept JSON arrays from agent output while storing immutable tuples."""
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, dict):
            return tuple(f"{key}: {item}" for key, item in value.items())
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ()
            return tuple(item.strip() for item in stripped.split(",") if item.strip())
        raise TypeError("value must be a JSON array, object, or comma-separated string")

    def key(self) -> str:
        """Return a normalized deduplication key."""
        normalized = f"{self._normalize_party(self.target)}|{self._normalize_party(self.acquirer)}"
        return "".join(char for char in normalized if char.isalnum() or char == "|")

    @staticmethod
    def _normalize_party(value: str) -> str:
        """Normalize common legal/geographic suffixes for duplicate detection."""
        value = re.sub(r"\([^)]*\)", " ", value.lower())
        value = re.sub(
            r"\b(inc|corp|corporation|llc|ltd|limited|group|holdings|co|company|assets?)\b",
            " ",
            value,
        )
        value = re.sub(r"\b(nasdaq|nyse|otc|otcqb|otcqx|tse)\b[:\w.]*", " ", value)
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    def standard_multiple_count(self) -> int:
        """Return the number of listed standard valuation multiples."""
        standard_patterns = (
            r"\bev\s*[/_-]\s*(revenue|sales|arr|ebitda|ebit|bookings|gross[ _-]?profit)(\b|_)",
            r"\bev[_-](ltm|ntm|ttm|fy|q\d)?[_-]?(revenue|sales|arr|ebitda|ebit)(\b|_)",
            r"\benterprise value\s*[/_-]\s*(revenue|sales|arr|ebitda|ebit|bookings)\b",
            r"\b(price|equity value)\s*[/_-]\s*(revenue|sales|earnings|book|tangible book)\b",
            r"\bp\s*/\s*e\b",
            r"\bprice\s*/\s*earnings\b",
            r"\bpremium\b|premium[_-]to",
        )
        excluded_patterns = (
            r"\bgoodwill\b",
            r"\bintangibles?\b",
            r"\bpatents?\b",
            r"\blicens(e|ing)\b",
            r"\bbacklog\b",
            r"\bpipeline\b",
            r"\btam\b",
            r"\bnote:",
        )
        count = 0
        for item in self.multiples:
            text = item.lower()
            if any(re.search(pattern, text) for pattern in excluded_patterns):
                continue
            if any(re.search(pattern, text) for pattern in standard_patterns):
                count += 1
        return count

    def multiple_count(self) -> int:
        """Return the number of explicitly listed multiples."""
        return len(tuple(item for item in self.multiples if item.strip()))

    def qualifies(self, min_multiples: int) -> bool:
        """Return whether this deal satisfies the disclosed/computable multiples filter."""
        return self.standard_multiple_count() >= min_multiples


# ---------------------------------------------------------------------------
# Structured Quality & Confidence Signals (quality-signals-001)
# ---------------------------------------------------------------------------


class ConfidenceLevel(StrEnum):
    """Canonical confidence levels aligned with SummitIntel DealConfidence."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class QualityBreakdown(BaseModel):
    """Per-criterion quality assessment for defensibility and auditability."""

    model_config = ConfigDict(strict=True, extra="forbid")

    source_attribution: str = Field(default="", description="Strength of source URLs/filings")
    multiples_quality: str = Field(
        default="", description="Clarity and standard-ness of disclosed multiples"
    )
    geographic_fit: str = Field(
        default="", description="Target HQ fit to requested geography (incl. near-miss notes)"
    )
    date_accuracy: str = Field(
        default="", description="Announcement/close date alignment to window"
    )
    consistency: str = Field(
        default="", description="Cross-section consistency (target/acquirer/value/multiples)"
    )
    benchmark_context: str = Field(
        default="", description="Presence and relevance of sector M&A benchmarks"
    )


class DealQualitySignals(BaseModel):
    """Structured, queryable quality and confidence signals for a deal (or overall QC).

    Enables data defensibility, human feedback loops, and clean SummitIntel ingestion.
    Human overrides take precedence for effective_confidence.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=False)

    overall_confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Agent-assessed confidence for this deal or report",
    )
    confidence_score: float = Field(
        default=0.65, ge=0.0, le=1.0, description="Normalized 0-1 score backing the level"
    )
    breakdown: QualityBreakdown = Field(
        default_factory=QualityBreakdown,
        description="Criterion-by-criterion rationale (maps to QC criteria)",
    )
    citations: tuple[str, ...] = Field(
        default_factory=tuple, description="Source URLs or filing refs backing the assessment"
    )
    flags: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Structured tags (near_miss_geography, low_source_diversity, ...)",
    )
    methodology_tags: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Provenance tags e.g. press_only, filings_verified, analyst_sourced",
    )

    # Human feedback layer (mutable for overrides)
    human_confidence_override: ConfidenceLevel | None = Field(
        default=None, description="Operator override (takes precedence)"
    )
    human_notes: str | None = Field(default=None, description="Free-text rationale for override")
    reviewer: str | None = Field(default=None, description="Operator or system reviewer id")
    reviewed_at: str | None = Field(default=None, description="ISO timestamp of last human touch")

    @property
    def effective_confidence(self) -> ConfidenceLevel:
        """Return the human override if present, else the agent overall_confidence."""
        return self.human_confidence_override or self.overall_confidence

    def to_summitintel_confidence(self) -> str:
        """Map to SummitIntel's expected HIGH/MEDIUM/LOW (already aligned)."""
        return self.effective_confidence.value


class AgentRunResult(BaseModel):
    """Normalized result from an Oz agent invocation.

    Extended with optional cost for cost-accounting-001 (non-breaking: default None).
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    state: str
    output: str
    run_id: str = ""
    run_url: str = ""
    error: str | None = None
    cost: CostBreakdown | None = None


class PipelinePaths(BaseModel):
    """Output paths produced by a pipeline run."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    output_dir: Path
    final_markdown: Path
    final_pdf: Path
    comps_excel: Path
    qualified_deals: Path
    # Cost accounting (cost-accounting-001) — populated by orchestrator for callers that need it
    cost: CostBreakdown | None = None


# ---------------------------------------------------------------------------
# Cost accounting models (cost-accounting-001)
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """Token counts for an agent invocation or full pipeline run aggregate."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)


class CostBreakdown(BaseModel):
    """Per-task or per-run cost estimate using the static price table.

    All monetary values in USD. Used for both per-agent instrumentation and
    industry-level budget rollups.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    model: str = Field(default="oz-default", min_length=1)
    usage: TokenUsage
    estimated_cost_usd: float = Field(..., ge=0)
    input_cost_usd: float = Field(..., ge=0)
    output_cost_usd: float = Field(..., ge=0)


# Static price table: USD per million tokens. Conservative defaults chosen so
# a typical 8-agent PTBot run (~2k-5k total tokens) produces $0.5-$5 estimates
# consistent with COST-ESTIMATE.md. Extended later when model tier selection lands.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "oz-default": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
}


def estimate_cost(prompt: str, output: str, model: str = "oz-default") -> CostBreakdown:
    """Heuristic token + cost estimation from char length (≈4 chars/token).

    Used by runners for both local and cloud paths. Guarantees positive token
    counts and matches the vBRIEF requirement for a static price table.
    """
    input_tokens = max(1, len(prompt or "") // 4)
    output_tokens = max(1, len(output or "") // 4)
    prices = PRICE_TABLE.get(model, PRICE_TABLE["oz-default"])
    in_cost = (input_tokens / 1_000_000) * prices["input_per_mtok"]
    out_cost = (output_tokens / 1_000_000) * prices["output_per_mtok"]
    total = in_cost + out_cost
    return CostBreakdown(
        model=model,
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        estimated_cost_usd=round(total, 6),
        input_cost_usd=round(in_cost, 6),
        output_cost_usd=round(out_cost, 6),
    )
