"""重试管理器 — RetryManager."""

from __future__ import annotations

from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.models.ingestion import IngestionResult, RetryResult
from ditto_platform.foundation import logger

from ditto_app.process.ingestion.coordinator import IngestionCoordinator
from ditto_app.process.ingestion.result_handler import count_results


class RetryManager:
    """重试管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        ingestion_log_service: IngestionLogService,
        source: str = "tushare",
    ) -> None:
        """

        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器

            ingestion_log_service: 摄取日志服务

            source: 数据源标识符



        """
        self._coordinator = coordinator

        self._ingestion_log_service = ingestion_log_service

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
        failed_dates = self._ingestion_log_service.list_failed_dates(
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
