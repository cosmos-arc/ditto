"""Research experiment API DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ExperimentArtifactResponse",
    "ExperimentCandidateResponse",
    "ExperimentControlReceiptResponse",
    "ExperimentControlRequest",
    "ExperimentDetailResponse",
    "ExperimentFoldResponse",
    "ExperimentGateResponse",
    "ExperimentRetryFoldRequest",
    "ExperimentReviewPacketResponse",
    "ExperimentSummaryResponse",
    "FactorDescriptorResponse",
    "NodeDescriptorResponse",
    "ReviewGateOutcomeResponse",
    "ReviewSelectionTraceRefResponse",
]


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
