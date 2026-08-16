"""Explicit public DTOs for the governed Agent API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_application.agent_campaign_runtime import CampaignStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class AgentCampaignHypothesis(_StrictModel):
    """Falsifiable hypothesis embedded in a Campaign manifest."""

    statement: str = Field(min_length=1, max_length=4096)
    mechanism: str = Field(min_length=1, max_length=4096)
    universe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_signal: str = Field(min_length=1, max_length=4096)
    failure_condition: str = Field(min_length=1, max_length=4096)


class AgentCampaignBaselineCandidate(_StrictModel):
    """Exact immutable baseline and its one authorized search axis."""

    candidate_id: str = Field(min_length=1, max_length=512)
    ordinal: int = Field(gt=0)
    parameters: dict[str, object]
    factor_code_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    model_code_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    data_requirement_hashes: list[str] = Field(min_length=1)


class AgentCampaignExperimentPlan(_StrictModel):
    """PIT-sensitive fold/snapshot/cost inputs frozen before approval."""

    fold_protocol_id: str = Field(min_length=1, max_length=512)
    fold_protocol_version: int = Field(gt=0)
    fold_protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_id: str = Field(min_length=1, max_length=512)
    validation_objective_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cost_model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0)
    purge_sessions: int = Field(ge=0)
    embargo_sessions: int = Field(ge=0)


class AgentCampaignSandboxLimits(_StrictModel):
    """Per-execution resource ceilings displayed with Campaign authority."""

    cpu_count: int = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    process_limit: int = Field(gt=0)
    temporary_storage_bytes: int = Field(gt=0)
    wall_time_seconds: int = Field(gt=0)
    output_bytes: int = Field(gt=0)


class AgentCampaignBudget(_StrictModel):
    """Finite Campaign-wide budget that cannot be patched after creation."""

    candidate_limit: int = Field(gt=0)
    fold_run_limit: int = Field(gt=0)
    generation_limit: int = Field(gt=0)
    concurrent_sandbox_limit: int = Field(gt=0)
    wall_time_limit_seconds: int = Field(gt=0)
    temporary_storage_limit_bytes: int = Field(gt=0)
    model_spend_limit_usd_micros: int = Field(gt=0)
    sandbox_resource_limits: AgentCampaignSandboxLimits


class AgentCampaignManifest(_StrictModel):
    """Versioned public document compiled into ResearchCampaignManifest."""

    campaign_id: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=4096)
    primary_metric_id: str = Field(min_length=1, max_length=128)
    hypothesis: AgentCampaignHypothesis
    baseline_candidate: AgentCampaignBaselineCandidate
    experiment_plan: AgentCampaignExperimentPlan
    budget: AgentCampaignBudget
    search_axis: Literal["factor_code", "model_code", "parameters"]
    search_space_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_root: str = Field(pattern=r"^[0-9a-f]{64}$")
    stopping_rule: str = Field(min_length=1, max_length=4096)
    allowed_tools: list[str] = Field(min_length=1)
    prohibited_actions: list[str] = Field(min_length=1)


class AgentCampaignCreateRequest(_StrictModel):
    """Create one durable immutable Campaign draft."""

    manifest: AgentCampaignManifest


class AgentCampaignApproveRequest(_StrictModel):
    """Human approval of one exact persisted manifest hash."""

    expected_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_id: str = Field(min_length=1, max_length=512)
    expires_at: datetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def parse_wire_datetime(cls, value: object) -> object:
        """Parse the RFC 3339 JSON wire representation before strict validation."""
        if type(value) is str:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        return value

    @field_validator("expires_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        """Reject local/naive expiry values at the transport boundary."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class AgentCampaignCancelRequest(_StrictModel):
    """Cancellation bound to the immutable Campaign authorization."""

    expected_authorization_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentCampaignResponse(_StrictModel):
    """Persisted Campaign projection with immutable authority and budget."""

    campaign_id: str
    status: CampaignStatus
    manifest_hash: str
    authorization_hash: str | None
    authorized_by: str | None
    authorization_expires_at: datetime | None
    search_axis: str
    source_snapshot_id: str
    allowed_tools: tuple[str, ...]
    budget: AgentCampaignBudget
    best_primary_metric_value: float | None
    no_improvement_generations: int
    statistical_trial_count: int
    operational_attempt_count: int
    revision: int


__all__ = [
    "AgentApprovalDecisionRequest",
    "AgentApprovalDecisionResponse",
    "AgentCampaignApproveRequest",
    "AgentCampaignBaselineCandidate",
    "AgentCampaignBudget",
    "AgentCampaignCancelRequest",
    "AgentCampaignCreateRequest",
    "AgentCampaignExperimentPlan",
    "AgentCampaignHypothesis",
    "AgentCampaignManifest",
    "AgentCampaignResponse",
    "AgentCampaignSandboxLimits",
    "AgentRunCancelRequest",
    "AgentRunCreateRequest",
    "AgentRunResponse",
    "AgentSessionCreateRequest",
    "AgentSessionResponse",
]
