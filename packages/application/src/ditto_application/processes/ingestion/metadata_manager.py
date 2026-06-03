"""元数据管理器 — checksum 比对与跳过决策."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import polars as pl
from ditto_data.catalog import (
    DataCatalogEntry,
    DataCatalogReader,
)
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.models.ingestion import IngestionLog
from ditto_platform.foundation import ChecksumCompute, logger

from ditto_application.catalog_freshness import (
    assess_catalog_freshness,
    catalog_entry_for_date,
)


class MetadataManager:
    """
    元数据管理器。

    负责处理数据摄取的元数据逻辑, 包括：
    - 计算 checksum
    - 比较数据是否变化
    - 判断是否需要跳过

    Attributes:
        _ingestion_log_store: IngestionLogStore 实例, 用于访问数据摄取日志等数据。

    """

    def __init__(
        self,
        ingestion_log_store: IngestionLogStore | None,
        *,
        data_catalog_reader: DataCatalogReader | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """
        初始化 MetadataManager。

        Args:
            ingestion_log_store: IngestionLogStore 实例。
            data_catalog_reader: 可选 DataCatalog 读端口，用于无 log 历史时的
                exact-date 落库资产跳过决策。
            now: 可选当前时间函数，便于测试 freshness/SLA 判定。

        """
        self._ingestion_log_store = ingestion_log_store
        self._data_catalog_reader = data_catalog_reader
        self._now = now or _utcnow

    def should_skip(
        self,
        dataset: str,
        trade_date: str,
        source: str = "tushare",
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """
        判断是否应该跳过此次摄取。

        Args:
            dataset: 数据集名称(如 "stock_daily")。
            trade_date: 交易日期(YYYY-MM-DD)。
            source: 数据源名称(如 "tushare", "akshare")。
            force: 是否强制重新摄取。

        Returns:
            (should_skip, reason) 元组：
            - should_skip: 是否应该跳过
            - reason: 跳过原因(如果不跳过则为 None)

        """
        # 如果 force=True, 不跳过
        if force:
            logger.debug(
                "Force mode enabled, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="force=True",
            )
            return False, None

        # 检查是否有历史记录
        if self._ingestion_log_store is None:
            # 如果没有提供 ingestion_log_store，不跳过
            logger.debug(
                "No ingestion_log_store provided, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="no_log_service",
            )
            return False, None

        existing = self._ingestion_log_store.get_log(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )

        # 无历史记录, 不跳过
        if existing is None:
            return self._should_skip_without_history(
                dataset=dataset,
                trade_date=trade_date,
                source=source,
            )

        # 历史成功, 跳过
        if existing.status.value == "SUCCESS":
            reason = (
                f"数据已存在且摄取成功({trade_date}, "
                f"checksum={existing.checksum[:8] if existing.checksum else 'N/A'}..., "
                f"rows={existing.rows})"
            )
            logger.debug(
                "Previous success found, skipping",
                event="should_skip_true",
                dataset=dataset,
                trade_date=trade_date,
                checksum=existing.checksum,
                rows=existing.rows,
            )
            return True, reason

        # 历史失败, 不跳过
        logger.debug(
            "Previous failure found, not skipping",
            event="should_skip_false",
            dataset=dataset,
            trade_date=trade_date,
            reason="previous_failure",
        )
        return False, None

    def _should_skip_without_history(
        self,
        *,
        dataset: str,
        trade_date: str,
        source: str,
    ) -> tuple[bool, str | None]:
        catalog_entry = self._catalog_entry_for_date(
            dataset=dataset,
            trade_date=trade_date,
            source=source,
        )
        if catalog_entry is None:
            logger.debug(
                "No history found, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="no_history",
            )
            return False, None

        freshness = assess_catalog_freshness(
            dataset=dataset,
            catalog_entry=catalog_entry,
            now=self._now,
        )
        if freshness.status == "stale":
            logger.debug(
                "Catalog asset stale, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                storage_uri=catalog_entry.storage_uri,
                source=source,
            )
            return False, None

        reason = (
            f"DataCatalog asset exists({trade_date}, "
            f"storage_uri={catalog_entry.storage_uri}, "
            f"schema={catalog_entry.schema.schema_hash}, "
            f"rows={catalog_entry.schema.row_count}, "
            f"freshness_at={catalog_entry.freshness_at.isoformat()})"
        )
        logger.debug(
            "Catalog asset found, skipping",
            event="should_skip_true",
            dataset=dataset,
            trade_date=trade_date,
            storage_uri=catalog_entry.storage_uri,
            source=source,
        )
        return True, reason

    def _catalog_entry_for_date(
        self,
        *,
        dataset: str,
        trade_date: str,
        source: str,
    ) -> DataCatalogEntry | None:
        if self._data_catalog_reader is None:
            return None
        return catalog_entry_for_date(
            reader=self._data_catalog_reader,
            dataset=dataset,
            trade_date=trade_date,
            source=source,
        )

    def compare_data(
        self,
        new_df: pl.DataFrame,
        existing_log: IngestionLog,
    ) -> bool:
        """
        比较新数据与已有数据是否相同。

        Args:
            new_df: 新的 Polars DataFrame。
            existing_log: 已有的摄取日志记录。

        Returns:
            如果数据相同返回 True, 否则返回 False。

        """
        # 如果现有记录没有 checksum, 认为不同
        if existing_log.checksum is None:
            logger.debug(
                "Existing log has no checksum, treating as different",
                event="compare_data_different",
                reason="no_checksum",
            )
            return False

        # 计算新数据的 checksum（使用统一的 ChecksumCompute）
        new_checksum = ChecksumCompute.from_dataframe(
            new_df, dataset_sort_keys(existing_log.dataset)
        )

        # 比较 checksum
        if new_checksum != existing_log.checksum:
            logger.debug(
                "Checksum mismatch, data changed",
                event="compare_data_different",
                reason="checksum_mismatch",
                new_checksum=new_checksum,
                existing_checksum=existing_log.checksum,
            )
            return False

        # 比较行数
        if existing_log.rows is not None and len(new_df) != existing_log.rows:
            logger.debug(
                "Row count mismatch, data changed",
                event="compare_data_different",
                reason="row_count_mismatch",
                new_rows=len(new_df),
                existing_rows=existing_log.rows,
            )
            return False

        # 数据相同
        logger.debug(
            "Data comparison successful, data unchanged",
            event="compare_data_same",
            checksum=new_checksum,
            rows=len(new_df),
        )
        return True


def _utcnow() -> datetime:
    return datetime.now(UTC)
