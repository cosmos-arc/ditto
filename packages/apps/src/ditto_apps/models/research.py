"""Research experiment API DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ExperimentControlReceiptResponse",
    "ExperimentControlRequest",
    "ExperimentDetailResponse",
    "ExperimentGateResponse",
    "ExperimentRetryFoldRequest",
    "ExperimentSummaryResponse",
    "FactorDescriptorResponse",
    "NodeDescriptorResponse",
]


class ExperimentDetailResponse(BaseModel):
    """API view of one durable experiment's current server truth."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    status: str
    stage: str
    strategy_version: str
    strategy_spec_hash: str
    snapshot_id: str
    candidate_count: int
    fold_count: int
    created_at: datetime
    updated_at: datetime


class ExperimentGateResponse(BaseModel):
    """API view of one append-only gate evaluation."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    rule_id: str
    policy_version: str
    layer: str
    outcome: str
    artifact_id: str | None
    evaluated_at: datetime


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
