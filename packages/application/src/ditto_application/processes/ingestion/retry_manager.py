"""重试管理器 — RetryManager."""

from __future__ import annotations

from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.models.ingestion import (
    IngestionFailedErrorGroup,
    IngestionResult,
    RetryResult,
    classify_ingestion_failure,
    is_retryable_ingestion_failure,
)
from ditto_platform.foundation import logger

from ditto_application.catalog_freshness import snapshot_repair_priority
from ditto_application.processes.ingestion.result_handler import count_results
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)

# 与 reader/store 既有默认一致的尝试上限（既有签名保持原字面量）。
DEFAULT_MAX_ATTEMPTS = 3


class RetryManager:
    """重试管理器（#623：补偿只选瞬态失败，按真实失败记录而非全注册表）。"""

    def __init__(
        self,
        coordinator: IngestionCoordinatorLike,
        ingestion_log_store: IngestionLogStore,
        source: str = "tushare",
    ) -> None:
        """

        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器
            ingestion_log_store: 摄取日志服务
            source: 数据源标识符

        """
        self._coordinator = coordinator

        self._ingestion_log_store = ingestion_log_store

        self._source = source

    def get_failed_dates(
        self,
        dataset: str,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        limit: int = 10,
    ) -> list[str]:
        """
        获取需要自动重试的交易日期列表（仅瞬态失败）。

        永久错误/源缺失/不支持分类的失败不进入自动重试：重试不改变
        结果，只会烧配额（#623）。被排除的失败经 ``retry_failed`` 的
        ``excluded_failures`` 保留原因与补偿范围。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）
            max_attempts: 最大尝试次数筛选条件
            limit: 返回的最大日期数量

        Returns:
            待重试的交易日期列表（YYYY-MM-DD）

        """
        eligible_logs = self._ingestion_log_store.list_failed_logs(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
            # SQL 内过滤瞬态：永久失败行 attempts 冻结，若 Python 侧再
            # 过滤会占满 LIMIT 窗口饿死更新的瞬态失败（#623 correctness F1）
            failure_filter="transient",
        )

        return self._prioritize_failed_dates(
            [log.trade_date for log in eligible_logs],
            dataset=dataset,
        )

    def _prioritize_failed_dates(
        self,
        failed_dates: list[str],
        *,
        dataset: str,
    ) -> list[str]:
        return sorted(
            failed_dates,
            key=lambda trade_date: snapshot_repair_priority(
                logs=self._ingestion_log_store,
                dataset=dataset,
                source=self._source,
                trade_date=trade_date,
            ),
        )

    def _error_groups(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> list[IngestionFailedErrorGroup]:
        return self._ingestion_log_store.list_failed_error_groups(
            source=self._source,
            max_attempts=max_attempts,
        )

    def compensation_selection(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> tuple[list[str], list[dict[str, object]]]:
        """
        每日补偿编排的单次查询选择（#623）。

        返回 (瞬态失败数据集升序列表, 非瞬态失败分组投影)。补偿目标按
        真实失败记录驱动，天然有界（最多注册表 45 项且仅含实际 FAIL
        者），不扫全注册表；非瞬态失败（永久/源缺失/不支持）不进入
        自动补偿，投影含 ``kind`` 分类与补偿范围供人工裁决。
        """
        groups = self._error_groups(max_attempts)
        retryable = sorted(
            {
                group.dataset
                for group in groups
                if is_retryable_ingestion_failure(group.error_code)
            }
        )
        excluded: list[dict[str, object]] = [
            {
                "dataset": group.dataset,
                "error_code": group.error_code,
                "kind": classify_ingestion_failure(group.error_code).value,
                "failure_count": group.failure_count,
                "oldest_trade_date": group.oldest_trade_date,
                "newest_trade_date": group.newest_trade_date,
            }
            for group in groups
            if not is_retryable_ingestion_failure(group.error_code)
        ]
        return retryable, excluded

    def excluded_failure_groups(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> list[IngestionFailedErrorGroup]:
        """
        非瞬态失败分组（永久/源缺失/不支持）——补偿报告用。

        满足尝试次数门槛但按失败分类不自动重试的失败：保留原因与
        补偿范围供人工裁决（#623 验收条款）。
        """
        return [
            group
            for group in self._error_groups(max_attempts)
            if not is_retryable_ingestion_failure(group.error_code)
        ]

    def retry_failed(
        self,
        dataset: str,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        limit: int = 10,
    ) -> RetryResult:
        """
        重试失败的任务（仅瞬态失败）。

        非瞬态失败满足尝试门槛也被排除出重试，随结果的
        ``excluded_failures`` 返回原因与范围。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）
            max_attempts: 最大尝试次数筛选条件
            limit: 重试的最大任务数量

        Returns:
            重试结果

        """
        transient_logs = self._ingestion_log_store.list_failed_logs(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
            failure_filter="transient",
        )
        excluded = self._ingestion_log_store.list_failed_logs(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
            failure_filter="non_transient",
        )
        failed_dates = self._prioritize_failed_dates(
            [log.trade_date for log in transient_logs],
            dataset=dataset,
        )

        total_failed = len(failed_dates)
        if excluded:
            logger.warning(
                "失败按分类排除出自动重试",
                event="retry_excluded_failures",
                dataset=dataset,
                excluded_count=len(excluded),
                kinds=sorted(
                    {
                        classify_ingestion_failure(log.error_code).value
                        for log in excluded
                    }
                ),
            )

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
            excluded_failures=tuple(excluded),
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


__all__ = ["DEFAULT_MAX_ATTEMPTS", "RetryManager"]
