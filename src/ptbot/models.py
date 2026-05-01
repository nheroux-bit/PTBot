"""Validated data models for PTBot."""

from __future__ import annotations

import re
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


class AgentRunResult(BaseModel):
    """Normalized result from an Oz agent invocation."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    state: str
    output: str
    run_id: str = ""
    run_url: str = ""
    error: str | None = None


class PipelinePaths(BaseModel):
    """Output paths produced by a pipeline run."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    output_dir: Path
    final_markdown: Path
    final_pdf: Path
    comps_excel: Path
    qualified_deals: Path
