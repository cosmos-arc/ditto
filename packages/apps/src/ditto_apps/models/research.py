"""Research experiment API DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["ExperimentDetailResponse", "ExperimentGateResponse"]


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
