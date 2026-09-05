"""Operational API response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthFeatures(BaseModel):
    """Process-level capabilities reported by liveness."""

    prefect: bool
    observability: bool


class HealthResponse(BaseModel):
    """Liveness response."""

    status: Literal["ok"]
    service: str
    timestamp: float
    features: HealthFeatures


class ReadinessCheckResponse(BaseModel):
    """One readiness dependency result."""

    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    """Runtime readiness response."""

    status: Literal["ready", "not_ready"]
    service: str
    checks: dict[str, ReadinessCheckResponse]


class SystemFeatures(BaseModel):
    """Product capabilities exposed by the status endpoint."""

    data_collection: bool
    data_validation: bool
    backtest: bool
    trading: bool


class ObservabilityStatus(BaseModel):
    """Active observability settings."""

    level: str
    structured: bool


class SystemStatusResponse(BaseModel):
    """Product runtime and deployable contract identity."""

    status: Literal["running"]
    version: str
    product_version: str
    git_sha: str
    api_contract_version: str
    api_contract_sha256: str
    environment: str
    features: SystemFeatures
    observability: ObservabilityStatus
