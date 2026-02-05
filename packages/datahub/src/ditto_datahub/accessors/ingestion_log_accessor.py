"""IngestionLog Accessor for ingestion log data access."""

from ditto_foundation.observability.tracing import traced
from loguru import logger

from ditto_datahub.models.ingestion import IngestionLog
from ditto_datahub.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)


class IngestionLogAccessor:
    """
    摄取日志访问器。

    为 Port 层提供摄取日志的访问接口，避免直接使用 Store。
    代理所有操作到 IngestionLogStore。
    """

    def __init__(self, ingestion_log_store: IngestionLogStore) -> None:
        """
        初始化 IngestionLogAccessor。

        Args:
            ingestion_log_store: 摄取日志存储实例。

        """
        self._ingestion_log_store = ingestion_log_store
        logger.debug(
            "IngestionLogAccessor initialized",
            event="ingestion_log_accessor_init",
        )

    @traced("accessor.ingestion_log.save_log")
    def save_log(self, log: IngestionLog) -> IngestionLog:
        """
        保存摄取日志。

        Args:
            log: 摄取日志对象。

        Returns:
            保存后的摄取日志（包含更新后的时间戳和尝试次数）。

        """
        logger.info(
            "Saving ingestion log",
            event="ingestion_log_save_start",
            dataset=log.dataset,
            source=log.source,
            trade_date=log.trade_date,
            status=log.status.value,
        )

        result = self._ingestion_log_store.save_log(log)

        logger.info(
            "Ingestion log saved",
            event="ingestion_log_save_complete",
            dataset=log.dataset,
            source=log.source,
            trade_date=log.trade_date,
            attempts=result.attempts,
        )

        return result

    @traced("accessor.ingestion_log.get_log")
    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """
        获取指定日期的摄取日志。

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识符（如 "tushare"）
            trade_date: 交易日期（YYYY-MM-DD）

        Returns:
            摄取日志对象，如果不存在则返回 None。

        """
        logger.debug(
            "Fetching ingestion log",
            event="ingestion_log_get_start",
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )

        result = self._ingestion_log_store.get_log(dataset, source, trade_date)

        logger.debug(
            "Ingestion log fetched",
            event="ingestion_log_get_complete",
            dataset=dataset,
            source=source,
            trade_date=trade_date,
            found=result is not None,
        )

        return result

    @traced("accessor.ingestion_log.get_failed_dates")
    def get_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """
        获取失败的交易日期。

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识符（默认 "tushare"）
            limit: 返回的最大日期数量
            max_attempts: 只返回尝试次数小于此值的日期

        Returns:
            需要重试的交易日期列表（YYYY-MM-DD）。

        """
        logger.debug(
            "Fetching failed dates",
            event="ingestion_log_get_failed_dates_start",
            dataset=dataset,
            source=source,
            limit=limit,
            max_attempts=max_attempts,
        )

        result = self._ingestion_log_store.get_failed_dates(
            dataset, source, limit, max_attempts
        )

        logger.debug(
            "Failed dates fetched",
            event="ingestion_log_get_failed_dates_complete",
            dataset=dataset,
            source=source,
            count=len(result),
        )

        return result

    @traced("accessor.ingestion_log.get_ingested_dates")
    def get_ingested_dates(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> list[str]:
        """
        获取已摄取的日期列表。

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识符（默认 "tushare"）

        Returns:
            已摄取的交易日期列表（YYYY-MM-DD）。

        """
        logger.debug(
            "Fetching ingested dates",
            event="ingestion_log_get_ingested_dates_start",
            dataset=dataset,
            source=source,
        )

        result = self._ingestion_log_store.get_ingested_dates(dataset, source)

        logger.debug(
            "Ingested dates fetched",
            event="ingestion_log_get_ingested_dates_complete",
            dataset=dataset,
            source=source,
            count=len(result),
        )

        return result

    @traced("accessor.ingestion_log.get_stats")
    def get_stats(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> dict[str, int]:
        """
        获取摄取统计。

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识符（默认 "tushare"）

        Returns:
            包含统计信息的字典：success_count, fail_count, total_count

        """
        logger.debug(
            "Fetching ingestion stats",
            event="ingestion_log_get_stats_start",
            dataset=dataset,
            source=source,
        )

        result = self._ingestion_log_store.get_stats(dataset, source)

        logger.debug(
            "Ingestion stats fetched",
            event="ingestion_log_get_stats_complete",
            dataset=dataset,
            source=source,
            stats=result,
        )

        return result

    @traced("accessor.ingestion_log.get_last_success_date")
    def get_last_success_date(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """
        获取最后成功的交易日期。

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识符（默认 "tushare"）

        Returns:
            最后成功的交易日期（YYYY-MM-DD），如果不存在则返回 None。

        """
        logger.debug(
            "Fetching last success date",
            event="ingestion_log_get_last_success_date_start",
            dataset=dataset,
            source=source,
        )

        result = self._ingestion_log_store.get_last_success_date(dataset, source)

        logger.debug(
            "Last success date fetched",
            event="ingestion_log_get_last_success_date_complete",
            dataset=dataset,
            source=source,
            found=result is not None,
        )

        return result
