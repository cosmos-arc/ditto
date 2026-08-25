"""Explicit public DTOs for the governed Agent API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.runtime.service import (
    AgentApprovalStatus,
    AgentProjectionState,
    AgentRuntimeState,
)
from ditto_application.agent_campaign_runtime import CampaignStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class AgentSessionCreateRequest(_StrictModel):
    """Create one short-lived local Agent session."""

    retention_class: Literal["ephemeral", "standard", "audit"] = "standard"


class AgentCapabilityResponse(_StrictModel):
    """Non-sensitive Agent runtime and profile availability."""

    enabled: bool
    runtime_state: AgentRuntimeState
    provider: str | None
    available_profiles: tuple[ModelProfile, ...]
    default_profile: ModelProfile | None
    degradation_reason: str | None
    checked_at: datetime


class AgentDecisionOpinionIdentity(_StrictModel):
    """Exact Daily Decision V3 and PIT identity behind a shadow opinion."""

    strategy_id: str
    strategy_version: str
    trade_date: str
    account_id: str
    sleeve_id: str
    v3_artifact_id: str
    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_id: str


class AgentDecisionOpinionQueryParams(BaseModel):
    """HTTP query parameters parsed before building the strict PIT identity."""

    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_version: str
    trade_date: str
    account_id: str
    sleeve_id: str
    v3_artifact_id: str
    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_id: str


class AgentDecisionOpinionResponse(_StrictModel):
    """Fail-closed shadow opinion projection that never changes V3 authority."""

    decision_identity: AgentDecisionOpinionIdentity
    status: Literal["completed", "blocked", "unavailable"]
    generated_at: datetime | None
    model_profile: str | None
    summary: str | None
    disagreements: tuple[str, ...]
    uncertainties: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provenance_match: bool
    shadow_outcome_identity: str | None
    unavailable_reason: str | None


class AgentSessionResponse(_StrictModel):
    """Created session identity and retention contract."""

    session_id: str
    created_at: datetime
    retention_class: RetentionClass


class AgentRunContext(_StrictModel):
    """Stable host-owned product context for one Agent run."""

    context_type: str = Field(min_length=1, max_length=128)
    context_id: str = Field(min_length=1, max_length=1024)


class AgentRunToolRecord(_StrictModel):
    """Redacted tool identity and authenticated evidence references."""

    call_id: str
    tool_name: str
    arguments_hash: str
    result_hash: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]


class AgentRunGuardrail(_StrictModel):
    """Bounded public guardrail outcome."""

    status: Literal["passed", "blocked", "unknown"]
    reason_code: str | None


class AgentRunUsage(_StrictModel):
    """Non-sensitive model/tool usage counters."""

    model_attempts: int
    model_turns: int
    tool_calls: int
    retries: int
    total_tokens: int
    model_spend_usd: Decimal
    exhausted_reason: str | None


class AgentRunCreateRequest(_StrictModel):
    """Create a governed read-only run without exposing provider state."""

    session_id: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=4096)
    authority_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_model_tokens: int = Field(default=4096, gt=0)
    max_model_spend_usd: Decimal = Field(default=Decimal("1"), ge=0)
    model_profile: Literal["balanced", "quality"] = "balanced"
    context: AgentRunContext | None = None

    @field_validator("max_model_spend_usd", mode="before")
    @classmethod
    def _parse_json_decimal(cls, value: object) -> object:
        """Preserve decimal precision across the public JSON boundary."""
        if isinstance(value, (Decimal, bool)):
            return value
        if isinstance(value, (str, int, float)):
            try:
                parsed = Decimal(str(value))
            except ValueError as exc:
                raise ValueError("max_model_spend_usd must be a decimal") from exc
            if not parsed.is_finite():
                raise ValueError("max_model_spend_usd must be finite")
            return parsed
        return value


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
    objective: str | None
    context: AgentRunContext | None
    output_summary: str | None
    tool_records: tuple[AgentRunToolRecord, ...]
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    guardrail: AgentRunGuardrail | None
    usage: AgentRunUsage | None
    failure_code: str | None
    event_cursor: int
    projection_state: AgentProjectionState
    projection_reason: str | None
    projection_version: int | None
    projection_updated_at: datetime | None


class AgentRunCancelRequest(_StrictModel):
    """Optimistic cancellation fence."""

    expected_revision: int = Field(ge=0)


class AgentApprovalDecisionRequest(_StrictModel):
    """Human decision over one exact immutable action hash."""

    decision: Literal["approve", "reject"]
    expected_action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_id: str = Field(min_length=1, max_length=512)
    reason: str | None = Field(default=None, min_length=1, max_length=4096)


class AgentApprovalResponse(_StrictModel):
    """Exact immutable approval subject and its current state."""

    approval_id: str
    run_id: str
    action_type: str
    target_identity: str
    action_payload: dict[str, object]
    action_hash: str
    status: AgentApprovalStatus
    requested_at: datetime
    expires_at: datetime
    operator_id: str | None
    reason: str | None
    decided_at: datetime | None


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


class AgentCampaignToolRecord(_StrictModel):
    """Redacted Campaign tool call presentation."""

    call_id: str
    tool_name: str
    arguments_hash: str
    result_hash: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]


class AgentCampaignGuardrail(_StrictModel):
    """Public Campaign guardrail outcome."""

    status: Literal["passed", "blocked", "unknown"]
    reason_code: str | None


class AgentCampaignUsage(_StrictModel):
    """Durable Campaign counters and available spend visibility."""

    statistical_trial_count: int
    operational_attempt_count: int
    no_improvement_generations: int
    model_spend_usd_micros: int | None
    exhausted_reason: str | None


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


class AgentCampaignHypothesisValidationRequest(_StrictModel):
    """Validate the preregistered hypothesis wizard step."""

    step: Literal["hypothesis"]
    campaign_id: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=4096)
    primary_metric_id: str = Field(min_length=1, max_length=128)
    hypothesis: AgentCampaignHypothesis


class AgentCampaignExperimentPlanValidationRequest(_StrictModel):
    """Validate baseline, single search axis, and PIT experiment plan."""

    step: Literal["experiment_plan"]
    search_axis: Literal["factor_code", "model_code", "parameters"]
    baseline_candidate: AgentCampaignBaselineCandidate
    experiment_plan: AgentCampaignExperimentPlan


class AgentCampaignGovernanceValidationRequest(_StrictModel):
    """Validate finite budget, hashes, stopping rule, and tool authority."""

    step: Literal["governance"]
    budget: AgentCampaignBudget
    search_space_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_root: str = Field(pattern=r"^[0-9a-f]{64}$")
    stopping_rule: str = Field(min_length=1, max_length=4096)
    allowed_tools: list[str] = Field(min_length=1)
    prohibited_actions: list[str] = Field(min_length=1)


class AgentCampaignManifestValidationRequest(_StrictModel):
    """Compile the complete draft into canonical immutable authority."""

    step: Literal["manifest"]
    manifest: AgentCampaignManifest


AgentCampaignValidationRequest = Annotated[
    AgentCampaignHypothesisValidationRequest
    | AgentCampaignExperimentPlanValidationRequest
    | AgentCampaignGovernanceValidationRequest
    | AgentCampaignManifestValidationRequest,
    Field(discriminator="step"),
]


class AgentCampaignValidationResponse(_StrictModel):
    """Successful server validation; canonical authority exists only when complete."""

    step: Literal["hypothesis", "experiment_plan", "governance", "manifest"]
    valid: bool
    canonical_manifest: dict[str, object] | None
    manifest_hash: str | None


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
    canonical_manifest: dict[str, object]
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
    objective: str | None
    output_summary: str | None
    tool_records: tuple[AgentCampaignToolRecord, ...]
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    guardrail: AgentCampaignGuardrail | None
    usage: AgentCampaignUsage | None
    event_cursor: int
    projection_state: Literal["complete", "partial"]
    projection_reason: str | None
    projection_version: int | None
    projection_updated_at: datetime | None


__all__ = [
    "AgentApprovalDecisionRequest",
    "AgentApprovalDecisionResponse",
    "AgentApprovalResponse",
    "AgentCampaignApproveRequest",
    "AgentCampaignBaselineCandidate",
    "AgentCampaignBudget",
    "AgentCampaignCancelRequest",
    "AgentCampaignCreateRequest",
    "AgentCampaignExperimentPlan",
    "AgentCampaignGuardrail",
    "AgentCampaignHypothesis",
    "AgentCampaignManifest",
    "AgentCampaignResponse",
    "AgentCampaignSandboxLimits",
    "AgentCampaignToolRecord",
    "AgentCampaignUsage",
    "AgentCampaignValidationRequest",
    "AgentCampaignValidationResponse",
    "AgentCapabilityResponse",
    "AgentDecisionOpinionIdentity",
    "AgentDecisionOpinionQueryParams",
    "AgentDecisionOpinionResponse",
    "AgentRunCancelRequest",
    "AgentRunContext",
    "AgentRunCreateRequest",
    "AgentRunGuardrail",
    "AgentRunResponse",
    "AgentRunToolRecord",
    "AgentRunUsage",
    "AgentSessionCreateRequest",
    "AgentSessionResponse",
]
