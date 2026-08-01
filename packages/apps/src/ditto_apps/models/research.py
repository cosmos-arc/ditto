"""Research experiment API DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from ditto_platform.foundation.json_types import JsonValue
from pydantic import BaseModel, ConfigDict

__all__ = [
    "CandidateExclusionEventResponse",
    "CandidateExclusionPageResponse",
    "CandidateFactorContributionPageResponse",
    "CandidateFactorContributionResponse",
    "CandidateSelectionEventResponse",
    "CandidateSelectionPageResponse",
    "CandidateSelectionReceiptResponse",
    "CandidateSelectionRequest",
    "ExperimentArtifactResponse",
    "ExperimentCandidateResponse",
    "ExperimentComparisonResponse",
    "ExperimentControlReceiptResponse",
    "ExperimentControlRequest",
    "ExperimentDetailResponse",
    "ExperimentFoldResponse",
    "ExperimentGateResponse",
    "ExperimentLaunchRequest",
    "ExperimentLaunchResponse",
    "ExperimentPlanningRequest",
    "ExperimentPreflightCheckResponse",
    "ExperimentPreflightResponse",
    "ExperimentRetryFoldRequest",
    "ExperimentReviewPacketResponse",
    "ExperimentSelectionEvidenceResponse",
    "ExperimentSummaryResponse",
    "FactorDescriptorResponse",
    "FactorDiagnosticsResponse",
    "HoldoutEvaluationReceiptResponse",
    "HoldoutEvaluationRequest",
    "NodeDescriptorResponse",
    "ReviewExposureWeightResponse",
    "ReviewGateOutcomeResponse",
    "ReviewSelectionExposureResponse",
    "ReviewSelectionTraceRefResponse",
]


class _StrictPlanningModel(BaseModel):
    """Fail-closed transport base for one canonical planning document node."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class ExperimentPlanningStrategyRequest(_StrictPlanningModel):
    """Exact strategy-version content identity supplied to planning."""

    strategy_id: str
    version: int
    spec_hash: str
    spec_json: dict[str, JsonValue]


class ExperimentPlanningSnapshotRequest(_StrictPlanningModel):
    """Exact certified research snapshot identity supplied to planning."""

    snapshot_id: str
    manifest_hash: str


class ExperimentPlanningBaselineRequest(_StrictPlanningModel):
    """Typed baseline descriptor envelope for the candidate matrix."""

    descriptor_type: str
    payload: dict[str, JsonValue]
    schema_version: int


class ExperimentPlanningParameterValueRequest(_StrictPlanningModel):
    """One tagged scalar matrix value."""

    type: Literal["bool", "int", "float", "string"]
    value: bool | int | float | str


class ExperimentPlanningParameterAxisRequest(_StrictPlanningModel):
    """One ordered candidate-matrix parameter axis."""

    name: str
    values: list[ExperimentPlanningParameterValueRequest]


class ExperimentPlanningMatrixRequest(_StrictPlanningModel):
    """Complete candidate matrix preimage."""

    baseline: ExperimentPlanningBaselineRequest
    axes: list[ExperimentPlanningParameterAxisRequest]
    candidate_limit: int


class ExperimentPlanningDatasetRequirementRequest(_StrictPlanningModel):
    """One exact certified dataset binding."""

    dataset_id: str
    expected_snapshot_ids: list[str]
    requires_pit_universe: bool
    certified_from: str | None


class ExperimentPlanningCostModelRequest(_StrictPlanningModel):
    """Deterministic resource-estimation coefficients."""

    bytes_per_run: int
    bytes_per_trading_session: int


class ExperimentPlanningBudgetRequest(_StrictPlanningModel):
    """Pre-registered hard resource ceilings."""

    candidate_limit: int
    fold_run_limit: int
    trading_session_limit: int
    disk_byte_limit: int


class ExperimentPlanningRequest(_StrictPlanningModel):
    """Complete transport-only document passed unchanged to the builder."""

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy: ExperimentPlanningStrategyRequest
    snapshot: ExperimentPlanningSnapshotRequest
    validation: dict[str, JsonValue]
    matrix: ExperimentPlanningMatrixRequest
    promotion_objective: dict[str, JsonValue]
    dataset_requirements: list[ExperimentPlanningDatasetRequirementRequest]
    cost_model: ExperimentPlanningCostModelRequest
    budget: ExperimentPlanningBudgetRequest
    seed: int
    worker_count: int
    failure_policy: Literal["continue_candidate_failures", "fail_fast"]
    created_at: str


class ExperimentLaunchRequest(ExperimentPlanningRequest):
    """Canonical planning document plus the operator-confirmed plan identity."""

    confirmed_plan_hash: str


class ExperimentPreflightCheckResponse(BaseModel):
    """Transport view of one deterministic planning gate result."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    outcome: str
    code: str | None
    reason: str | None
    remediation: str | None
    observed: dict[str, JsonValue]
    policy: dict[str, JsonValue]


class ExperimentPreflightResponse(BaseModel):
    """Complete operator confirmation surface returned by read-only preflight."""

    model_config = ConfigDict(frozen=True)

    status: str
    plan_hash: str | None
    checks: list[ExperimentPreflightCheckResponse]
    candidate_count: int
    planned_fold_count: int
    budget_run_count: int
    estimated_trading_sessions: int
    estimated_disk_bytes: int
    eligible_month_count: int
    isolation_width_sessions: int


class ExperimentLaunchResponse(BaseModel):
    """Durable server truth returned after launch or exact replay."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    status: str
    queue_ordinal: int
    revision: int
    candidate_count: int
    fold_count: int
    plan_hash: str


class ExperimentCandidateResponse(BaseModel):
    """API view of one immutable experiment candidate."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    ordinal: int
    is_baseline: bool
    parameters: dict[str, Any]


class ExperimentFoldResponse(BaseModel):
    """API view of one persisted fold specification and projection."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    fold_id: str
    ordinal: int
    role: str
    status: str
    train_start: date | None
    train_end: date | None
    test_start: date
    test_end: date
    purge_sessions: int
    embargo_sessions: int
    claim_owner_token: str | None
    revision: int
    updated_at: datetime


class ExperimentDetailResponse(BaseModel):
    """API view of one durable experiment's current server truth."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy_version: str
    strategy_spec_hash: str
    snapshot_id: str
    status: str
    desired_state: str
    stage: str
    failure_code: str | None
    queue_ordinal: int | None
    revision: int
    created_at: datetime
    updated_at: datetime
    seed: int
    worker_count: int
    failure_policy: str
    candidate_limit: int
    fold_run_limit: int
    fold_protocol_id: str
    fold_protocol_version: int
    fold_protocol_hash: str
    candidate_count: int
    fold_count: int
    candidates: list[ExperimentCandidateResponse]
    folds: list[ExperimentFoldResponse]


class ExperimentGateResponse(BaseModel):
    """API view of one append-only gate evaluation."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    experiment_id: str
    candidate_id: str | None
    fold_id: str | None
    attempt_id: str | None
    rule_id: str
    policy_version: str
    layer: str
    outcome: str
    observed: Any
    policy: Any
    artifact_id: str | None
    payload_hash: str
    evaluated_at: datetime


class ExperimentArtifactResponse(BaseModel):
    """API view of one immutable indexed experiment artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    experiment_id: str
    candidate_id: str | None
    fold_id: str | None
    attempt_id: str | None
    artifact_kind: str
    relative_path: str
    content_hash: str
    schema_hash: str
    row_count: int
    byte_size: int
    reproduction_fingerprint: str
    manifest: Any
    is_pinned: bool
    pinned_at: datetime | None
    created_at: datetime
    revision: int


class ExperimentSelectionEvidenceResponse(BaseModel):
    """API view of one experiment's verified selection-evidence ledger."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    experiment_id: str
    content_hash: str
    byte_size: int
    is_pinned: bool
    created_at: datetime
    payload: Any


class ExperimentComparisonResponse(BaseModel):
    """API view of one experiment's candidate comparison projection."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    payload_hash: str
    revision: int
    payload: Any


class ReviewGateOutcomeResponse(BaseModel):
    """API view of one gate rule's identity and outcome in a review packet."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    layer: str
    outcome: str


class ReviewSelectionTraceRefResponse(BaseModel):
    """API view of one verified selection-trace artifact reference."""

    model_config = ConfigDict(frozen=True)

    artifact_kind: str
    artifact_id: str
    content_hash: str


class ReviewExposureWeightResponse(BaseModel):
    """One canonical exposure dimension and aggregate selected weight."""

    model_config = ConfigDict(frozen=True)

    key: str
    weight: float


class ReviewSelectionExposureResponse(BaseModel):
    """Explicit stock exposure or ETF not-applicable review evidence."""

    model_config = ConfigDict(frozen=True)

    applicability: str
    lane: str
    industry_weights: list[ReviewExposureWeightResponse]
    size_bucket_weights: list[ReviewExposureWeightResponse]
    artifact_refs: list[ReviewSelectionTraceRefResponse]


class ExperimentReviewPacketResponse(BaseModel):
    """API view of one immutable promotion review packet."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    candidate_id: str | None
    bundle_hash: str
    hard_review_blocked: bool
    gate_outcomes: list[ReviewGateOutcomeResponse]
    schema_version: int
    fold_ids: list[str]
    attempt_ids: list[str]
    spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    snapshot_hash: str
    registry_hash: str
    objective_payload_hash: str
    comparison_payload_hash: str | None
    r1_impact_payload_hash: str | None
    selection_evidence_artifact_id: str | None
    holdout_claim_id: str | None
    candidate_rationale: str
    selection_trace_artifact_refs: list[ReviewSelectionTraceRefResponse]
    selection_exposure: ReviewSelectionExposureResponse | None


class ExperimentSummaryResponse(BaseModel):
    """API view of one experiment root in list views (no candidate/fold expansion)."""

    experiment_id: str
    status: str
    desired_state: str
    stage: str
    failure_code: str | None
    queue_ordinal: int | None
    revision: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


class NodeDescriptorResponse(BaseModel):
    """API view of one immutable strategy pipeline node descriptor."""

    node_type: str
    version: str
    category: str
    display_name: str
    implementation_key: str
    config_schema: dict[str, str]
    default_config: dict[str, Any]
    required_datasets: list[str]
    capability_tags: list[str]
    deterministic: bool

    model_config = ConfigDict(strict=True, extra="ignore")


class FactorDescriptorResponse(BaseModel):
    """API view of one governed core-factor descriptor."""

    factor_id: str
    resolved_payload: dict[str, Any]

    model_config = ConfigDict(strict=True, extra="ignore")


class FactorDiagnosticsResponse(BaseModel):
    """Typed immutable factor diagnostics and their complete read identity."""

    model_config = ConfigDict(frozen=True)

    factor_id: str
    snapshot_id: str
    snapshot_hash: str
    registry_hash: str
    start_date: date
    end_date: date
    provenance: dict[str, Any]
    metrics: dict[str, Any]
    artifact_id: str
    content_hash: str


class CandidateSelectionRequest(BaseModel):
    """Body for one durable server-side promotion preselection."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    rationale: str
    comparison_payload_hash: str
    expected_revision: int


class CandidateSelectionReceiptResponse(BaseModel):
    """API projection of one append-only candidate preselection event."""

    model_config = ConfigDict(frozen=True)

    selection_id: str
    experiment_id: str
    candidate_id: str
    comparison_payload_hash: str
    candidate_evidence_artifact_id: str
    candidate_evidence_content_hash: str
    selection_evidence_content_hash: str
    revision: int
    event_id: str
    occurred_at: datetime


class HoldoutSelectionReasonRequest(BaseModel):
    """Operator-authored reason bound into the immutable holdout claim."""

    model_config = ConfigDict(frozen=True)

    code: str
    summary: str


class HoldoutEvaluationRequest(BaseModel):
    """Body for the one-shot holdout claim of a persisted preselection."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    selection_id: str
    expected_selection_evidence_hash: str
    expected_candidate_evidence_content_hash: str
    expected_revision: int
    operator_confirmation: str
    selection_reason: HoldoutSelectionReasonRequest


class HoldoutEvaluationReceiptResponse(BaseModel):
    """API projection of one committed or exactly replayed holdout claim."""

    model_config = ConfigDict(frozen=True)

    claim_id: str
    selection_id: str
    experiment_id: str
    candidate_id: str
    state: Literal["claimed"]
    fold_id: str
    logical_run_id: str
    reproduction_fingerprint: str
    claim_payload_hash: str
    selection_evidence_content_hash: str
    candidate_evidence_content_hash: str
    revision: int
    event_id: str
    occurred_at: datetime


class CandidateSelectionEventResponse(BaseModel):
    """One candidate selection event from an immutable candidate bundle."""

    model_config = ConfigDict(frozen=True)

    validation_fold_ordinal: int
    fold_id: str
    trade_date: str
    instrument_id: int | str
    score: float | None
    rank: int
    selected: bool
    evidence_hash: str


class CandidateExclusionEventResponse(BaseModel):
    """One candidate exclusion event from an immutable candidate bundle."""

    model_config = ConfigDict(frozen=True)

    validation_fold_ordinal: int
    fold_id: str
    trade_date: str
    instrument_id: int | str
    stage: str
    reason_code: str
    message: str | None
    evidence_hash: str


class CandidateFactorContributionResponse(BaseModel):
    """One factor contribution bound to a fold decision and evidence hash."""

    model_config = ConfigDict(frozen=True)

    validation_fold_ordinal: int
    fold_id: str
    trade_date: str
    instrument_id: int | str
    factor_id: str
    contribution: float | None
    rank: int | None
    selected: bool | None
    evidence_hash: str


class CandidateSelectionPageResponse(BaseModel):
    """Typed selections page over one immutable candidate bundle."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    experiment_id: str
    artifact_id: str
    content_hash: str
    items: list[CandidateSelectionEventResponse]
    next_cursor: str | None


class CandidateExclusionPageResponse(BaseModel):
    """Typed exclusions page over one immutable candidate bundle."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    experiment_id: str
    artifact_id: str
    content_hash: str
    items: list[CandidateExclusionEventResponse]
    next_cursor: str | None


class CandidateFactorContributionPageResponse(BaseModel):
    """Typed contribution page over one immutable candidate bundle."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    experiment_id: str
    artifact_id: str
    content_hash: str
    items: list[CandidateFactorContributionResponse]
    next_cursor: str | None


class ExperimentControlRequest(BaseModel):
    """Body for one revision-fenced experiment control action (pause/cancel/resume)."""

    model_config = ConfigDict(frozen=True)

    expected_revision: int


class ExperimentRetryFoldRequest(BaseModel):
    """
    Body for one revision-fenced terminal fold retry.

    expected_revision is the fold projection revision (not experiment revision).
    """

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    fold_id: str
    expected_revision: int


class ExperimentControlReceiptResponse(BaseModel):
    """API view of one durable control receipt (CAS post-state)."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    status: str
    desired_state: str
    revision: int
    occurred_at: datetime
    live_run_ids: list[str]
