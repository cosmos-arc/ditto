"""Universe API 模型."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from ditto_application.queries.historical_universe import HistoricalUniverseSources
from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.technical_analysis import HttpDateTime


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


class HistoricalUniverseSourcesBody(BaseModel):
    """Pinned evidence chains needed to reconstruct a historical observation pool."""

    model_config = ConfigDict(extra="forbid")
    universe_id: str = Field(min_length=1)
    asset_kind: Literal["stock", "etf"]
    master_snapshot_ids: list[str] = Field(min_length=1)
    status_snapshot_ids: list[str] = Field(min_length=1)
    membership_snapshot_ids: list[str] | None = None
    index_id: str | None = None

    def to_application(self) -> HistoricalUniverseSources:
        """Adapt transport values without claiming qualification."""
        return HistoricalUniverseSources(
            universe_id=self.universe_id,
            asset_kind=self.asset_kind,
            master_snapshot_ids=tuple(self.master_snapshot_ids),
            status_snapshot_ids=tuple(self.status_snapshot_ids),
            membership_snapshot_ids=tuple(self.membership_snapshot_ids or ()),
            index_id=self.index_id,
        )


class HistoricalUniverseBody(BaseModel):
    """Read-only historical resolution request."""

    model_config = ConfigDict(extra="forbid")
    sources: HistoricalUniverseSourcesBody
    as_of: date
    knowledge_cutoff: HttpDateTime
    publication_cutoff: HttpDateTime


class HistoricalUniverseMemberResponse(BaseModel):
    """Observation membership is separate from investment eligibility."""

    instrument_id: int
    list_date: date
    delist_date: date | None
    is_suspended: bool | None
    tracking_index: str | None = None
    investable: bool
    exclusion_reasons: list[str]


class HistoricalUniverseResponse(BaseModel):
    """Exact scope, time and snapshot identity for a historical universe."""

    snapshot_id: str
    sources: HistoricalUniverseSourcesBody
    as_of: date
    knowledge_cutoff: HttpDateTime
    publication_cutoff: HttpDateTime
    rule_version: str
    members: list[HistoricalUniverseMemberResponse]
