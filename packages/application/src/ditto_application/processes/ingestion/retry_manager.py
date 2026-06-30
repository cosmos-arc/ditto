"""重试管理器 — RetryManager."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ditto_data.catalog import DataCatalogReader
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.models.ingestion import IngestionResult, RetryResult
from ditto_platform.foundation import logger

from ditto_application.catalog_freshness import catalog_repair_priority
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)


class RetryManager:
    """重试管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinatorLike,
        ingestion_log_store: IngestionLogStore,
        source: str = "tushare",
        *,
        data_catalog_reader: DataCatalogReader | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """

        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器

            ingestion_log_store: 摄取日志服务

            source: 数据源标识符

            data_catalog_reader: 可选 catalog 读端口，用于按 freshness/SLA
                优先级排序失败修复任务。

            now: 可选当前时间函数，便于测试 SLA 判定。



        """
        self._coordinator = coordinator

        self._ingestion_log_store = ingestion_log_store

        self._source = source
        self._data_catalog_reader = data_catalog_reader
        self._now = now

    def get_failed_dates(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> list[str]:
        """

        获取失败的交易日期列表。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）

            max_attempts: 最大尝试次数筛选条件

            limit: 返回的最大日期数量



        Returns:
            失败的交易日期列表（YYYY-MM-DD）



        """
        failed_dates = self._ingestion_log_store.list_failed_dates(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
        )

        failed_dates = self._prioritize_failed_dates(dataset, failed_dates)

        logger.debug(
            "获取失败日期",
            event="get_failed_dates",
            dataset=dataset,
            count=len(failed_dates),
            max_attempts=max_attempts,
        )

        return failed_dates

    def _prioritize_failed_dates(
        self,
        dataset: str,
        failed_dates: list[str],
    ) -> list[str]:
        reader = self._data_catalog_reader
        if reader is None:
            return failed_dates
        return sorted(
            failed_dates,
            key=lambda trade_date: catalog_repair_priority(
                reader=reader,
                dataset=dataset,
                source=self._source,
                trade_date=trade_date,
                now=self._now,
            ),
        )

    def retry_failed(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> RetryResult:
        """

        重试失败的任务。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）

            max_attempts: 最大尝试次数筛选条件

            limit: 重试的最大任务数量



        Returns:
            重试结果



        """
        failed_dates = self.get_failed_dates(
            dataset=dataset,
            max_attempts=max_attempts,
            limit=limit,
        )

        total_failed = len(failed_dates)

        results: list[IngestionResult] = []

        logger.info(
            "开始重试失败任务",
            event="retry_failed_start",
            dataset=dataset,
            total_failed=total_failed,
            max_attempts=max_attempts,
        )

        for trade_date in failed_dates:
            result = self._coordinator.ingest_date(
                dataset=dataset,
                trade_date=trade_date,
                force=True,
            )

            results.append(result)

        # 统计结果

        counts = count_results(results)

        retry_result = RetryResult(
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=counts.success,
            still_failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "重试失败任务完成",
            event="retry_failed_complete",
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=counts.success,
            still_failed_count=counts.failed,
        )

        return retry_result


__all__ = ["RetryManager"]
