"""Explicit public DTOs for the governed Agent API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class AgentSessionCreateRequest(_StrictModel):
    """Create one short-lived local Agent session."""

    retention_class: Literal["ephemeral", "standard", "audit"] = "standard"


class AgentSessionResponse(_StrictModel):
    """Created session identity and retention contract."""

    session_id: str
    created_at: datetime
    retention_class: RetentionClass


class AgentRunCreateRequest(_StrictModel):
    """Create a governed read-only run without exposing provider state."""

    session_id: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=4096)
    authority_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_model_tokens: int = Field(default=4096, gt=0)
    max_model_spend_usd: Decimal = Field(default=Decimal("1"), ge=0)
    model_profile: Literal["balanced", "quality"] = "balanced"


class AgentRunResponse(_StrictModel):
    """Non-sensitive durable run projection."""

    run_id: str
    session_id: str
    status: RunStatus
    objective_hash: str
    authority_hash: str
    max_model_tokens: int
    max_model_spend_usd: Decimal
    model_profile: ModelProfile
    manifest_hash: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    revision: int


class AgentRunCancelRequest(_StrictModel):
    """Optimistic cancellation fence."""

    expected_revision: int = Field(ge=0)


class AgentApprovalDecisionRequest(_StrictModel):
    """Human decision over one exact immutable action hash."""

    decision: Literal["approve", "reject"]
    expected_action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_id: str = Field(min_length=1, max_length=512)
    reason: str | None = Field(default=None, min_length=1, max_length=4096)


class AgentApprovalDecisionResponse(_StrictModel):
    """Durable terminal approval receipt."""

    approval_id: str
    run_id: str
    action_hash: str
    status: Literal["approved", "rejected"]
    operator_id: str
    reason: str | None
    decided_at: datetime


__all__ = [
    "AgentApprovalDecisionRequest",
    "AgentApprovalDecisionResponse",
    "AgentRunCancelRequest",
    "AgentRunCreateRequest",
    "AgentRunResponse",
    "AgentSessionCreateRequest",
    "AgentSessionResponse",
]
