"""
摄取结果处理器。

负责处理数据摄取的各种结果状态，包括：
- 数据获取错误
- 未知错误
- 空数据
- 写入错误
- DQ 阻断
- 成功写入
"""

import polars as pl
from ditto_datahub.models import WriteResult
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.services import IngestionLogService

from ditto_port.models import IngestionResult
from ditto_port.services.ingestion.errors import SourceFetchError


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
