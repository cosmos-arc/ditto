"""
IdentityStore for identity mapping with PIT support.

This module provides storage and retrieval for identity mappings
with Point-in-Time support for identifier resolution.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from pathlib import Path

from ditto_foundation import logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IdentityStore(SQLiteStore):
    """
    Identity 映射存储。

    管理 identity_mapping 表，支持 PIT 查询。

    表结构:
        - instrument_id: 证券内部标识符
        - source: 数据源标识
        - source_ticker: 数据源原始代码
        - effective_from: 生效开始日期
        - effective_to: 生效结束日期 (NULL 表示当前有效)
        - is_primary: 是否主标识符
    """

    def __init__(self, db_path: Path) -> None:
        """
        初始化 IdentityStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        super().__init__(db_path)

    @traced("data.identity.resolve_instrument_id")
    def resolve_instrument_id(
        self, source_ticker: str, source: str, asof: str | None
    ) -> int | None:
        """
        解析 source_ticker 到 instrument_id（支持 PIT）.

        Args:
            source_ticker: 数据源原始代码.
            source: 数据源标识.
            asof: 时间点日期，None 表示当前.

        Returns:
            instrument_id 或 None（如果未找到）.

        """
        logger.debug(
            "Starting identity Instrument ID resolution",
            event="identity_instrument_id_resolve_start",
            source_ticker=source_ticker,
            source=source,
            asof=asof,
        )

        if asof:
            # PIT mode: 查询历史映射
            row = self.fetchone(
                """SELECT instrument_id FROM identity_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, source_ticker, asof, asof],
            )
        else:
            # Current mode: 只查询当前有效映射（更快）
            row = self.fetchone(
                """SELECT instrument_id FROM identity_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_to IS NULL""",
                [source, source_ticker],
            )

        instrument_id = int(row["instrument_id"]) if row else None

        if instrument_id:
            logger.debug(
                "Identity Instrument ID resolved successfully",
                event="identity_instrument_id_resolve_complete",
                source_ticker=source_ticker,
                instrument_id=instrument_id,
            )
        else:
            logger.warning(
                "Identity Instrument ID not found",
                event="identity_instrument_id_resolve_not_found",
                source_ticker=source_ticker,
                source=source,
                asof=asof,
            )

        return instrument_id

    @traced("data.identity.resolve_instrument_ids_batch")
    def resolve_instrument_ids_batch(
        self,
        source_tickers: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """
        批量解析 source_tickers 到 instrument_ids.

        Args:
            source_tickers: 数据源原始代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            字典，映射 source_ticker 到 instrument_id（仅包含找到的代码）.

        """
        logger.info(
            "Starting batch identity Instrument ID resolution",
            event="identity_instrument_id_batch_resolve_start",
            source=source,
            asof=asof,
            input_count=len(source_tickers),
        )

        result: dict[str, int] = {}
        for code in source_tickers:
            instrument_id = self.resolve_instrument_id(code, source, asof)
            if instrument_id:
                result[code] = instrument_id

        logger.info(
            "Batch identity Instrument ID resolution completed",
            event="identity_instrument_id_batch_resolve_complete",
            requested=len(source_tickers),
            found=len(result),
            not_found=len(source_tickers) - len(result),
        )

        return result

    @traced("data.identity.get_source_ticker")
    def get_source_ticker(
        self, instrument_id: int, source: str, asof: str | None
    ) -> str | None:
        """
        反向查询：instrument_id 到 source_ticker.

        Args:
            instrument_id: 证券内部标识符.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            source_ticker 或 None（如果未找到）.

        """
        if asof:
            row = self.fetchone(
                """SELECT source_ticker FROM identity_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [instrument_id, source, asof, asof],
            )
        else:
            row = self.fetchone(
                """SELECT source_ticker FROM identity_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_to IS NULL""",
                [instrument_id, source],
            )

        return str(row["source_ticker"]) if row else None

    @traced("data.identity.register")
    def register(
        self,
        instrument_id: int,
        source_ticker: str,
        source: str,
        effective_from: str,
        is_primary: bool = True,
    ) -> None:
        """
        注册 identity_mapping 记录.

        Args:
            instrument_id: 证券内部标识符.
            source_ticker: 数据源原始代码.
            source: 数据源标识.
            effective_from: 生效开始日期.
            is_primary: 是否主标识符.

        """
        logger.info(
            "Starting identity registration",
            event="identity_register_start",
            instrument_id=instrument_id,
            source_ticker=source_ticker,
            source=source,
            effective_from=effective_from,
            is_primary=is_primary,
        )

        try:
            self.execute(
                """INSERT INTO identity_mapping
                (instrument_id, source, source_ticker, effective_from, is_primary)
                VALUES (?, ?, ?, ?, ?)""",
                [
                    instrument_id,
                    source,
                    source_ticker,
                    effective_from,
                    1 if is_primary else 0,
                ],
            )

            self.commit()

            logger.info(
                "Identity registered successfully",
                event="identity_register_complete",
                instrument_id=instrument_id,
                source_ticker=source_ticker,
                source=source,
            )

        except Exception as e:
            logger.error(
                "Identity registration failed",
                event="identity_register_failed",
                instrument_id=instrument_id,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
