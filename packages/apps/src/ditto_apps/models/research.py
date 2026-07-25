"""Research experiment API DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ExperimentDetailResponse",
    "ExperimentGateResponse",
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
