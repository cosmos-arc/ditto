"""
Dataset coverage query facade — 覆盖限制传播的消费入口（#628 P4）。

backend/CLI 经 application 消费 ditto_data 的覆盖限制真源；
语义标注（latest/as-of/frozen）由各数据读取响应自行声明，
本 facade 只回答「该数据集的测量覆盖与限制是什么」。
对外暴露自有 View（隐藏 data 层符号，不做跨包再导出）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from ditto_data.coverage import (
    COVERAGE_MEASURED_AT,
    KNOWLEDGE_AXIS_VOCABULARY,
    DatasetCoverageLimit,
    get_dataset_coverage,
    get_knowledge_axis,
    list_dataset_coverage,
)

from ditto_application.exceptions import AppQueryError

__all__ = [
    "DatasetCoverageQueryFacade",
    "DatasetCoverageView",
]


type CoverageStatus = Literal["ready", "partial", "empty"]
type KnowledgeAxis = Literal["provider_anchor", "derived_t1", "same_day", "observation"]

_ALLOWED_STATUS: frozenset[str] = frozenset({"ready", "partial", "empty"})


@dataclass(frozen=True)
class DatasetCoverageView:
    """单数据集覆盖限制（测量时点快照，非实时）。"""

    dataset: str
    domain: str
    # ready=预期范围完整且当前 / partial=起点末端味道品种有缺 / empty=本地零行
    status: CoverageStatus
    measured_start: str | None
    measured_end: str | None
    gaps: tuple[str, ...]
    notes: str | None
    measured_at: date
    # 知识轴分类（provider_anchor/derived_t1/same_day/observation；
    # None=未分类，如纯元数据集——不宣称公告可知性）
    knowledge_axis: KnowledgeAxis | None


def _to_view(limit: DatasetCoverageLimit) -> DatasetCoverageView:
    if limit.status not in _ALLOWED_STATUS:
        message = (
            f"unknown coverage status {limit.status!r} for dataset "
            f"{limit.dataset!r}; vocabulary is ready/partial/empty"
        )
        raise AppQueryError(message)
    return DatasetCoverageView(
        dataset=limit.dataset,
        domain=limit.domain,
        status=cast("CoverageStatus", limit.status),
        measured_start=limit.measured_start,
        measured_end=limit.measured_end,
        gaps=limit.gaps,
        notes=limit.notes,
        measured_at=COVERAGE_MEASURED_AT,
        knowledge_axis=_knowledge_axis(limit.dataset),
    )


def _knowledge_axis(dataset: str) -> KnowledgeAxis | None:
    """词表校验后收敛为 Literal（与 status 同一单点模式）。"""
    axis = get_knowledge_axis(dataset)
    if axis is not None and axis not in KNOWLEDGE_AXIS_VOCABULARY:
        message = (
            f"unknown knowledge axis {axis!r} for dataset {dataset!r}; "
            f"vocabulary is {sorted(KNOWLEDGE_AXIS_VOCABULARY)}"
        )
        raise AppQueryError(message)
    return cast("KnowledgeAxis | None", axis)


class DatasetCoverageQueryFacade:
    """数据集覆盖限制查询 facade（无状态，数据源为运行时蒸馏真源）."""

    def get(self, dataset: str) -> DatasetCoverageView | None:
        """返回单数据集覆盖限制；未注册数据集返回 None."""
        limit = get_dataset_coverage(dataset)
        return None if limit is None else _to_view(limit)

    def list(self) -> tuple[DatasetCoverageView, ...]:
        """返回全部数据集覆盖限制（按 dataset 字典序）."""
        return tuple(_to_view(limit) for limit in list_dataset_coverage())
