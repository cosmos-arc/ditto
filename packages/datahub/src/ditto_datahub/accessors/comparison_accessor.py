"""质量对比结果访问器."""

from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.quality.comparison_store import ComparisonStore


class ComparisonAccessor:
    """
    质量对比结果访问器.

    提供跨源对比结果的领域级操作接口，
    遵循 Accessor 模式以保持架构一致性.
    """

    def __init__(self, comparison_store: ComparisonStore) -> None:
        """
        初始化访问器.

        Args:
            comparison_store: 对比结果存储.

        """
        self._comparison_store = comparison_store

    @traced("accessor.comparison.write_result")
    async def write_result(
        self,
        trade_date: str,
        df: pl.DataFrame,
        dataset: str = "stock_daily",
    ) -> None:
        """
        写入对比结果.

        Args:
            trade_date: 交易日期
            df: 对比结果 DataFrame（由 Port 层转换）
            dataset: 数据集标识

        """
        logger.info(
            "Writing comparison result",
            event="comparison_write_start",
            trade_date=trade_date,
            dataset=dataset,
            row_count=len(df),
        )

        await self._comparison_store.write_comparison(trade_date, df, dataset)

        logger.info(
            "Comparison result written",
            event="comparison_write_complete",
            trade_date=trade_date,
            dataset=dataset,
        )

        # 记录指标
        M.data_records.add(
            len(df), {"dataset": "quality_comparison", "operation": "write"}
        )

    @traced("accessor.comparison.read_result")
    async def read_result(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> pl.DataFrame | None:
        """
        读取对比结果.

        Args:
            trade_date: 交易日期
            dataset: 数据集标识

        Returns:
            对比结果 DataFrame，如果不存在则返回 None

        """
        logger.debug(
            "Reading comparison result",
            event="comparison_read_start",
            trade_date=trade_date,
            dataset=dataset,
        )

        result = await self._comparison_store.read_comparison(trade_date, dataset)

        row_count = len(result) if result is not None else 0
        logger.debug(
            "Comparison result read",
            event="comparison_read_complete",
            trade_date=trade_date,
            found=result is not None,
            row_count=row_count,
        )

        return result

    @traced("accessor.comparison.get_stats")
    def get_stats(self) -> list[dict[str, Any]]:
        """
        获取对比结果统计信息.

        Returns:
            统计信息列表

        """
        logger.debug(
            "Fetching comparison statistics",
            event="comparison_stats_start",
        )

        stats = self._comparison_store.get_stats()

        logger.debug(
            "Comparison statistics fetched",
            event="comparison_stats_complete",
            stats_count=len(stats),
        )

        return stats
