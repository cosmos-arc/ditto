"""策略 API 模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateStrategyRequest(BaseModel):
    """创建策略请求."""

    strategy_id: str = Field(description="策略 ID")
    name: str = Field(description="策略名称")
    spec_json: dict[str, Any] = Field(description="策略定义 JSON")
    tags: list[str] = Field(default_factory=list, description="标签")

    model_config = ConfigDict(strict=True, extra="ignore")


class UpdateStrategyRequest(BaseModel):
    """更新策略请求."""

    name: str = Field(description="策略名称")
    spec_json: dict[str, Any] = Field(description="策略定义 JSON")
    tags: list[str] = Field(default_factory=list, description="标签")
    version: int | None = Field(default=None, description="版本号(乐观锁)")

    model_config = ConfigDict(strict=True, extra="ignore")


class PublishStrategyRequest(BaseModel):
    """发布策略请求."""

    version: int = Field(ge=1, description="版本号")

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyResponse(BaseModel):
    """策略响应."""

    strategy_id: str
    name: str
    spec_json: dict[str, Any]
    version: int
    status: str
    created_at: str = ""
    tags: list[str] = []

    model_config = ConfigDict(strict=True, extra="ignore")


# ---------------------------------------------------------------------------
# Strategy governance (R3) — review/publish/reactivate control plane
# ---------------------------------------------------------------------------


class GovernanceDecisionRequest(BaseModel):
    """Shared actor + reason body for one governance state-machine decision."""

    actor: str = Field(description="决策执行者")
    reason: str = Field(description="决策原因")

    model_config = ConfigDict(strict=True, extra="ignore")


class ReactivateStrategyRequest(GovernanceDecisionRequest):
    """Reactivate one published version with an optimistic pointer CAS guard."""

    expected_pointer_revision: int = Field(
        ge=0, description="最后读到的 active pointer revision (optimistic CAS)"
    )


class StrategyVersionResponse(BaseModel):
    """One immutable governance version (list-versions view, no payload bytes)."""

    strategy_id: str
    version: int
    parent_version: int | None
    spec_hash: str
    state: str
    review_outcome: str
    created_at: str

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyVersionStateResponse(BaseModel):
    """Lifecycle projection returned after one governance state-machine decision."""

    strategy_id: str
    version: int
    state: str
    review_outcome: str

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyActivePointerResponse(BaseModel):
    """Active pointer returned after a reactivate decision."""

    strategy_id: str
    active_version: int
    pointer_revision: int

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyActiveResponse(BaseModel):
    """Active pointer joined with its published payload (get-active view)."""

    strategy_id: str
    active_version: int
    pointer_revision: int
    spec: StrategyResponse

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "CreateStrategyRequest",
    "GovernanceDecisionRequest",
    "PublishStrategyRequest",
    "ReactivateStrategyRequest",
    "StrategyActivePointerResponse",
    "StrategyActiveResponse",
    "StrategyResponse",
    "StrategyVersionResponse",
    "StrategyVersionStateResponse",
    "UpdateStrategyRequest",
]


class PublishStrategyVersionRequest(BaseModel):
    """Body for one evidence-gated strategy version publish."""

    model_config = ConfigDict(frozen=True)

    bundle_hash: str
    actor: str
    reason: str
