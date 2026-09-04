"""Universe API 模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UniverseResponse(BaseModel):
    """Universe 响应."""

    universe_id: str
    name: str
    description: str | None = None
    universe_type: str = "custom"
    source_ref: str | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class MemberResponse(BaseModel):
    """Universe 成分股响应."""

    instrument_id: int

    model_config = ConfigDict(strict=True, extra="ignore")


class CreateUniverseRequest(BaseModel):
    """创建 Universe 请求."""

    universe_id: str = Field(..., min_length=1, description="Universe ID")
    name: str = Field(..., min_length=1, description="名称")
    description: str | None = Field(default=None, description="描述")

    model_config = ConfigDict(strict=True, extra="ignore")


class UpdateUniverseRequest(BaseModel):
    """更新 Universe 请求."""

    name: str = Field(..., min_length=1, description="名称")
    description: str | None = Field(default=None, description="描述")
    members: list[str] | None = Field(default=None, description="成分列表")
    effective_date: str | None = Field(default=None, description="生效日期")

    model_config = ConfigDict(strict=True, extra="ignore")


def to_universe_response(row: dict[str, Any]) -> UniverseResponse:
    """将 universe dict 转为 API 响应."""
    return UniverseResponse(
        universe_id=row.get("universe_id", ""),
        name=row.get("name", ""),
        description=row.get("description"),
        universe_type=row.get("universe_type", "custom"),
        source_ref=row.get("source_ref"),
    )


__all__ = [
    "CreateUniverseRequest",
    "MemberResponse",
    "UniverseResponse",
    "UpdateUniverseRequest",
    "to_universe_response",
]
