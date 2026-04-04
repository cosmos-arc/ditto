"""Data 领域事件 — 数据入库/质量检查相关事件子类."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ditto_kernel import DomainEvent

__all__ = [
    "DataIngested",
    "QualityCheckCompleted",
]


@dataclass(frozen=True, kw_only=True)
class DataIngested(DomainEvent):
    """数据入库完成事件（预留 — 当前未在 ingestion 流程中发布）."""

    event_type: str = field(default="data_ingested", init=False)
    dataset: str
    trade_date: date
    row_count: int
    source: str = ""


@dataclass(frozen=True, kw_only=True)
class QualityCheckCompleted(DomainEvent):
    """质量检查完成事件（预留 — 当前未在 quality 流程中发布）."""

    event_type: str = field(default="quality_check_completed", init=False)
    dataset: str
    trade_date: date
    passed: bool
    issues: list[str] = field(default_factory=list)
