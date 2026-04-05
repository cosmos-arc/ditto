"""摄取结果处理 — count_results + IngestionResultHandler."""

from __future__ import annotations

from collections import Counter

import polars as pl
from ditto_data.errors import SourceFetchError
from ditto_data.models.ingestion import (
    IngestionLog,
    IngestionResult,
    IngestionStatus,
    ResultCounts,
)
from ditto_data.models.storage import WriteResult
from ditto_data.services import IngestionLogService


def count_results(
    results: list[IngestionResult] | dict[str, dict[str, object]],
) -> ResultCounts:
    """
    统计摄取结果。

    Args:
        results: 摄取结果列表或字典

    Returns:
        ResultCounts: 包含 success/failed/skipped 计数

    Examples:
        >>> results = [
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-01",
        ...         status="success",
        ...     ),
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-02",
        ...         status="failed",
        ...         error="FETCH_ERROR",
        ...     ),
        ... ]
        >>> counts = count_results(results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

        >>> # 字典类型结果
        >>> dict_results = {
        ...     "task1": {"status": "success"},
        ...     "task2": {"status": "failed"},
        ... }
        >>> counts = count_results(dict_results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

    """
    if isinstance(results, list):
        # 处理 IngestionResult 列表
        statuses = [r.status for r in results if hasattr(r, "status")]
    else:
        # 处理字典类型结果
        statuses = [v.get("status") for v in results.values() if "status" in v]

    # 使用 Counter 统计
    counter = Counter(statuses)

    return ResultCounts(
        success=counter.get("success", 0),
        failed=counter.get("failed", 0),
        skipped=counter.get("skipped", 0),
    )


class IngestionResultHandler:
    """
    摄取结果处理器。

    负责将摄取操作的各种结果转换为 IngestionResult 并记录日志。
    """

    def __init__(
        self, ingestion_log_service: IngestionLogService | None, source_name: str
    ) -> None:
        """
        初始化 IngestionResultHandler。

        Args:
            ingestion_log_service: IngestionLogService 实例，用于访问 ingestion_log
            source_name: 数据源名称

        """
        self._ingestion_log_service = ingestion_log_service
        self._source_name = source_name

    def _save_log(self, log: IngestionLog) -> None:
        """保存日志（如果提供了 ingestion_log_service）。"""
        if self._ingestion_log_service:
            self._ingestion_log_service.save_log(log)

    def handle_fetch_error(
        self, dataset: str, trade_date: str, error: SourceFetchError
    ) -> IngestionResult:
        """
        处理数据获取错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 获取错误

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="FETCH_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="FETCH_ERROR",
            message=f"获取数据失败: {error}",
        )

    def handle_unknown_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理未知错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="UNKNOWN_ERROR",
                error_message=f"{type(error).__name__}: {error}",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="UNKNOWN_ERROR",
            message=f"未知错误: {error}",
        )

    def handle_empty_data(self, dataset: str, trade_date: str) -> IngestionResult:
        """
        处理空数据。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="EMPTY_DATA",
                error_message="获取的数据为空",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="EMPTY_DATA",
            message="获取的数据为空",
        )

    def handle_write_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理写入错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="WRITE_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="WRITE_ERROR",
            message=f"写入数据失败: {error}",
        )

    def handle_dq_blocked(
        self, dataset: str, trade_date: str, write_result: WriteResult
    ) -> IngestionResult:
        """
        处理 DQ 阻断。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            write_result: 写入结果

        Returns:
            IngestionResult: 失败结果

        """
        # DQ 检查已移到 Port 层，这里使用默认错误计数
        error_count = 1
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="DQ_BLOCKED",
                error_message=f"DQ L1 check failed: {error_count} errors",
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="DQ_BLOCKED",
            message=(
                "DQ L1 check failed, data rejected (will retry via reprocess task)"
            ),
        )

    def handle_success(
        self,
        dataset: str,
        trade_date: str,
        df: pl.DataFrame,
        write_result: WriteResult,
    ) -> IngestionResult:
        """
        处理成功写入。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            df: 数据框
            write_result: 写入结果

        Returns:
            IngestionResult: 成功结果

        """
        self._save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
                checksum=write_result.checksum,
                rows=len(df),
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="success",
            row_count=len(df),
            # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
            checksum=write_result.checksum,
            message="数据摄取成功",
        )
