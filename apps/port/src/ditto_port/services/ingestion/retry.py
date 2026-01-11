"""
重试管理器。

负责重试失败的任务，包括：
- 支持按最大重试次数筛选
- 支持按日期范围筛选
- 限制重试数量以防资源耗尽
"""

from typing import TYPE_CHECKING

from ditto_foundation import logger
from pydantic import BaseModel

from ditto_port.services.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionResult,
)

if TYPE_CHECKING:
    from ditto_datahub.stores.ingestion_log import IngestionLogStore


class RetryResult(BaseModel):
    """重试结果。"""

    dataset: str
    total_failed: int
    retried_count: int
    success_count: int
    still_failed_count: int
    results: list[IngestionResult]


class RetryManager:
    """重试管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        ingestion_log_store: "IngestionLogStore",
        source: str = "tushare",
    ) -> None:
        """
        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器
            ingestion_log_store: 摄取日志存储
            source: 数据源标识符

        """
        self._coordinator = coordinator
        self._ingestion_log_store = ingestion_log_store
        self._source = source

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
        failed_dates = self._ingestion_log_store.get_failed_dates(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
        )

        logger.debug(
            "获取失败日期",
            event="get_failed_dates",
            dataset=dataset,
            count=len(failed_dates),
            max_attempts=max_attempts,
        )

        return failed_dates

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

        success_count = sum(1 for r in results if r.status == "success")
        still_failed_count = sum(1 for r in results if r.status == "failed")

        retry_result = RetryResult(
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=success_count,
            still_failed_count=still_failed_count,
            results=results,
        )

        logger.info(
            "重试失败任务完成",
            event="retry_failed_complete",
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=success_count,
            still_failed_count=still_failed_count,
        )

        return retry_result
