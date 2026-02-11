"""
QualityRecordService - 质量记录服务.

封装 ComparisonStore 和 QuarantineStore，为 Port 层提供统一的质量记录接口.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from ditto_datahub.stores.runtime.quality import ComparisonStore, QuarantineStore


class QualityRecordService:
    """
    质量记录服务.

    封装质量对比和隔离数据的存储操作，提供统一的质量记录管理接口。

    职责：
    - 记录质量对比结果（ComparisonStore）
    - 隔离质量失败数据（QuarantineStore）
    - 提供质量统计信息
    - 自动清理过期数据
    """

    def __init__(
        self,
        comparison_store: ComparisonStore,
        quarantine_store: QuarantineStore,
    ) -> None:
        """
        初始化 QualityRecordService.

        Args:
            comparison_store: 质量对比结果存储实例
            quarantine_store: 隔离数据存储实例

        """
        self._comparison_store = comparison_store
        self._quarantine_store = quarantine_store

    # ========================================================================
    # 对比结果相关 (ComparisonStore)
    # ========================================================================

    async def save_comparison(
        self,
        trade_date: str,
        df: pl.DataFrame,
        dataset: str = "stock_daily",
    ) -> None:
        """
        保存质量对比结果.

        Args:
            trade_date: 交易日期
            df: 对比结果 DataFrame
            dataset: 数据集标识

        """
        await self._comparison_store.write_comparison(trade_date, df, dataset)

    async def get_comparison(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> pl.DataFrame | None:
        """
        获取质量对比结果.

        Args:
            trade_date: 交易日期
            dataset: 数据集标识

        Returns:
            对比结果 DataFrame，不存在时返回 None

        """
        return await self._comparison_store.read_comparison(trade_date, dataset)

    def get_comparison_stats(self) -> list[dict[str, str | int]]:
        """
        获取对比结果统计信息.

        Returns:
            统计信息列表

        """
        return self._comparison_store.get_stats()

    # ========================================================================
    # 隔离数据相关 (QuarantineStore)
    # ========================================================================

    def save_failed_data(
        self,
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        """
        保存质量失败数据到隔离区.

        Args:
            dataset: 数据集名称
            rule_id: 失败的规则 ID
            severity: 严重程度 (error/warning/alert)
            failed_data: 失败的数据行
            trade_date: 可选的交易日期

        Returns:
            插入记录的行 ID

        """
        return self._quarantine_store.save_failed_data(
            dataset, rule_id, severity, failed_data, trade_date
        )

    def get_quarantined_data(
        self,
        dataset: str | None = None,
        rule_id: str | None = None,
        limit: int = 1000,
    ) -> pl.DataFrame:
        """
        获取隔离区数据.

        Args:
            dataset: 按数据集过滤（可选）
            rule_id: 按规则 ID 过滤（可选）
            limit: 最大返回行数

        Returns:
            隔离数据 DataFrame

        """
        return self._quarantine_store.get_quarantined_data(dataset, rule_id, limit)

    def get_failed_data_df(self, row_id: int) -> pl.DataFrame:
        """
        根据 row ID 获取失败数据 DataFrame.

        Args:
            row_id: 隔离记录 ID

        Returns:
            失败数据 DataFrame，未找到或解析失败时返回空 DataFrame

        """
        return self._quarantine_store.get_failed_data_df(row_id)

    # ========================================================================
    # 统计信息
    # ========================================================================

    def get_quarantine_stats(self) -> list[dict[str, Any]]:
        """
        获取隔离区统计信息.

        Returns:
            统计信息字典列表

        """
        return self._quarantine_store.get_stats()

    def get_all_stats(self) -> dict[str, Any]:
        """
        获取所有质量统计信息.

        Returns:
            包含对比和隔离统计的字典

        """
        return {
            "comparison": self.get_comparison_stats(),
            "quarantine": self.get_quarantine_stats(),
        }

    # ========================================================================
    # 清理操作
    # ========================================================================

    def clear_old_quarantine_records(self, days: int = 30) -> int:
        """
        清理过期的隔离记录.

        Args:
            days: 删除多少天前的记录

        Returns:
            删除的记录数

        """
        return self._quarantine_store.clear_old_records(days)
