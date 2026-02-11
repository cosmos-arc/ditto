"""
IngestionLogService - 数据摄入日志服务.

封装 IngestionLogReader 和 IngestionLogWriter，为 Port 层提供统一的数据摄入日志管理接口.
"""

from __future__ import annotations

from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.runtime.ingestion import (
    IngestionLogReader,
    IngestionLogWriter,
)


class IngestionLogService:
    """
    数据摄入日志服务.

    封装 IngestionLogReader 和 IngestionLogWriter，提供统一的摄入日志管理接口。

    职责：
    - 追踪每个交易日期的数据摄入状态
    - 管理摄入失败重试记录
    - 提供摄入统计信息
    """

    def __init__(
        self,
        ingestion_log_reader: IngestionLogReader,
        ingestion_log_writer: IngestionLogWriter,
    ) -> None:
        """
        初始化 IngestionLogService.

        Args:
            ingestion_log_reader: 摄入日志读取器实例
            ingestion_log_writer: 摄入日志写入器实例

        """
        self._reader = ingestion_log_reader
        self._writer = ingestion_log_writer

    def save_log(self, log: IngestionLog) -> IngestionLog:
        """
        保存或更新摄入日志记录.

        Args:
            log: 摄入日志对象

        Returns:
            保存后的摄入日志对象（包含更新的时间戳和尝试次数）

        """
        return self._writer.save_log(log)

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """
        获取指定日期的摄入日志.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（如 "tushare"）
            trade_date: 交易日期（YYYY-MM-DD）

        Returns:
            摄入日志对象，不存在时返回 None

        """
        return self._reader.get_log(dataset, source, trade_date)

    def list_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """
        获取需要重试的失败交易日期.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）
            limit: 返回的最大日期数量
            max_attempts: 仅返回尝试次数小于此值的日期

        Returns:
            需要重试的交易日期列表（YYYY-MM-DD）

        """
        return self._reader.list_failed_dates(dataset, source, limit, max_attempts)

    def list_failed_logs(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[IngestionLog]:
        """
        获取需要重试的失败摄入日志.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）
            limit: 返回的最大日志数量
            max_attempts: 仅返回尝试次数小于此值的日志

        Returns:
            需要重试的摄入日志列表

        """
        return self._reader.list_failed_logs(dataset, source, limit, max_attempts)

    def count_success_rate(
        self,
        dataset: str,
        source: str = "tushare",
        start_date: str | None = None,
    ) -> float:
        """
        计算数据集的摄入成功率.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）
            start_date: 可选的起始日期过滤（YYYY-MM-DD）

        Returns:
            成功率（0.0 到 1.0）

        """
        return self._reader.count_success_rate(dataset, source, start_date)

    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """
        获取数据集的摄入统计信息.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）

        Returns:
            统计信息字典，包含 success_count, fail_count, total_count

        """
        return self._reader.get_stats(dataset, source)

    def list_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
        status: IngestionStatus | None = None,
    ) -> list[str]:
        """
        获取数据集的所有已摄入交易日期.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）
            status: 可选的状态过滤（SUCCESS 或 FAIL）。
                    为 None 时返回所有日期。

        Returns:
            已摄入的交易日期列表（YYYY-MM-DD）

        """
        return self._reader.list_ingested_dates(dataset, source, status)

    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """
        获取数据集最后成功的交易日期.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）

        Returns:
            最后成功的交易日期（YYYY-MM-DD），不存在时返回 None

        """
        return self._reader.get_last_success_date(dataset, source)
