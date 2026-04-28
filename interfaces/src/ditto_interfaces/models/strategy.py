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
    updated_at: str = ""
    tags: list[str] = []

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "CreateStrategyRequest",
    "PublishStrategyRequest",
    "StrategyResponse",
    "UpdateStrategyRequest",
]
