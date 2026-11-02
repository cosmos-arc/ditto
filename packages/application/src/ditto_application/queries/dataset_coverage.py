"""
Dataset coverage query facade — 覆盖限制传播的消费入口（#628 P4）。

backend/CLI 经 application 消费 ditto_data 的覆盖限制真源；
语义标注（latest/as-of/frozen）由各数据读取响应自行声明，
本 facade 只回答「该数据集的测量覆盖与限制是什么」。
"""

from __future__ import annotations

from ditto_data.coverage import (
    DatasetCoverageLimit,
    get_dataset_coverage,
    list_dataset_coverage,
)

__all__ = ["DatasetCoverageQueryFacade"]


class DatasetCoverageQueryFacade:
    """数据集覆盖限制查询 facade（无状态，数据源为运行时蒸馏真源）."""

    def get(self, dataset: str) -> DatasetCoverageLimit | None:
        """返回单数据集覆盖限制；未注册数据集返回 None."""
        return get_dataset_coverage(dataset)

    def list(self) -> tuple[DatasetCoverageLimit, ...]:
        """返回全部数据集覆盖限制（按 dataset 字典序）."""
        return list_dataset_coverage()
