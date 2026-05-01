"""Validated data models for PTBot."""

from __future__ import annotations

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

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

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
        raise TypeError("value must be a JSON array")

    def key(self) -> str:
        """Return a normalized deduplication key."""
        normalized = f"{self.target}|{self.acquirer}".lower()
        return "".join(char for char in normalized if char.isalnum() or char == "|")

    def multiple_count(self) -> int:
        """Return the number of explicitly listed multiples."""
        return len(tuple(item for item in self.multiples if item.strip()))

    def qualifies(self, min_multiples: int) -> bool:
        """Return whether this deal satisfies the disclosed/computable multiples filter."""
        if self.multiple_count() >= min_multiples:
            return True
        return min_multiples == 1 and (
            self.multiples_disclosed or self.computed_multiples_available
        )


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
