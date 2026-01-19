"""
元数据管理器。

负责处理数据摄取的元数据逻辑, 包括：
- 比较新旧数据
- 判断是否需要跳过摄取(基于 checksum 和游标)
"""

import polars as pl
from ditto_datahub.models.ingestion import IngestionLog
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_foundation import logger
from ditto_foundation.util.checksum import ChecksumCompute


class MetadataManager:
    """
    元数据管理器。

    负责处理数据摄取的元数据逻辑, 包括：
    - 计算 checksum
    - 比较数据是否变化
    - 判断是否需要跳过

    Attributes:
        _log_store: IngestionLogStore 实例, 用于访问摄取日志。

    """

    def __init__(self, log_store: IngestionLogStore | None = None) -> None:
        """
        初始化 MetadataManager。

        Args:
            log_store: IngestionLogStore 实例。如果为 None, 必须稍后设置。

        """
        self._log_store = log_store

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
        if self._log_store is None:
            logger.warning(
                "log_store not set, cannot check history",
                event="should_skip_log_store_missing",
                dataset=dataset,
                trade_date=trade_date,
            )
            return False, None

        existing = self._log_store.get_log(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )

        # 无历史记录, 不跳过
        if existing is None:
            logger.debug(
                "No history found, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="no_history",
            )
            return False, None

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
        new_checksum = ChecksumCompute.from_dataframe(new_df, existing_log.dataset)

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
