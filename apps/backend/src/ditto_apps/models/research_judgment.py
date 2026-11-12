"""Research judgment transport models for saved comparison conclusions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_JUDGMENT_ID_PATTERN = r"^research-judgment:sha256:[0-9a-f]{64}$"


class ResearchJudgmentResponse(BaseModel):
    """One saved research conclusion bound to explicit compared run identities."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    judgment_id: str = Field(min_length=1, pattern=_JUDGMENT_ID_PATTERN)
    run_ids: tuple[str, ...] = Field(min_length=1)
    judgment: str = Field(min_length=1)
    created_at: datetime
    strategy_id: str | None = Field(default=None, min_length=1)
    strategy_version: int | None = Field(default=None, ge=1)
    schema_version: int


class ResearchJudgmentSummaryResponse(BaseModel):
    """Compact judgment summary for the reopen list."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    judgment_id: str = Field(min_length=1, pattern=_JUDGMENT_ID_PATTERN)
    run_ids: tuple[str, ...] = Field(min_length=1)
    created_at: datetime
    judgment: str = Field(min_length=1)
    strategy_id: str | None = Field(default=None, min_length=1)
    strategy_version: int | None = Field(default=None, ge=1)


class CreateResearchJudgmentBody(BaseModel):
    """User record of one comparison conclusion with optional follow-up entry."""

    model_config = ConfigDict(extra="forbid")

    run_ids: tuple[str, ...] = Field(min_length=1)
    judgment: str = Field(min_length=1)
    strategy_id: str | None = Field(default=None, min_length=1)
    strategy_version: int | None = Field(default=None, ge=1)


__all__ = [
    "CreateResearchJudgmentBody",
    "ResearchJudgmentResponse",
    "ResearchJudgmentSummaryResponse",
]
