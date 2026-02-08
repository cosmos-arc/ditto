"""Industry 相关数据模型."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndustryBasic:
    """申万行业基本信息."""

    industry_id: str
    industry_name: str
    industry_level: str  # 一级/二级行业
    parent_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class IndustryMapping:
    """股票-行业映射."""

    instrument_id: int
    industry_id: str
    source: str = "sw"  # 申万
    effective_from: str | None = None
    effective_to: str | None = None
    entry_reason: str | None = None
