"""
重试管理器。

负责重试失败的任务，包括：
- 支持按最大重试次数筛选
- 支持按日期范围筛选
- 限制重试数量以防资源耗尽
"""

from ditto_datahub import DataHub
from ditto_foundation import logger

from ditto_port.models import IngestionResult, RetryResult
from ditto_port.services.ingestion.coordinator import IngestionCoordinator
from ditto_port.services.ingestion.result_utils import count_results


class RetryManager:
    """重试管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        hub: DataHub,
        source: str = "tushare",
    ) -> None:
        """
        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器
            hub: 数据访问中心
            source: 数据源标识符

        """
        self._coordinator = coordinator
        self._hub = hub
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
        failed_dates = self._hub.ingestion_log.get_failed_dates(
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
