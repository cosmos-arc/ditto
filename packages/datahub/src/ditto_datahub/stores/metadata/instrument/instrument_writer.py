"""InstrumentWriter - 证券主数据写入接口."""

from __future__ import annotations

from typing import Any

from ditto_foundation import logger

from ditto_datahub.stores.metadata.instrument.models import InstrumentRegistration


class InstrumentWriter:
    """
    证券主数据写入接口。

    提供：
    - register() - 注册新证券（事务性操作 + 缓存失效）

    Attributes:
        _client: SQLite 客户端，用于数据库访问
        _cache: DataCache 缓存管理器（可选）

    """

    def __init__(self, client: Any, cache: Any | None = None) -> None:
        """
        初始化 InstrumentWriter。

        Args:
            client: SQLite 客户端实例
            cache: 可选的 DataCache 实例

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "InstrumentWriter initialized",
            event="instrument_writer_init_complete",
        )

    def register(self, instrument_id: int, registration: InstrumentRegistration) -> int:
        """
        注册新证券。

        事务性操作：插入 instrument 和 instrument_mapping 表，
        失败时自动回滚，成功时提交。

        Args:
            instrument_id: 证券 ID
            registration: 证券注册配置

        Returns:
            注册的 instrument_id

        Raises:
            Exception: 数据库操作失败时（已回滚）

        """
        logger.info(
            "Starting instrument registration",
            event="instrument_register_start",
            instrument_id=instrument_id,
            symbol=registration.symbol,
            source_ticker=registration.source_ticker,
            source=registration.source,
            asset_class=registration.asset_class,
            exchange=registration.exchange,
        )

        try:
            # 插入 instrument 表
            self._client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, symbol, name, exchange, board, asset_class,
                    list_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    registration.symbol,
                    registration.name,
                    registration.exchange,
                    registration.board,
                    registration.asset_class,
                    registration.list_date,
                ],
            )

            # 插入 instrument_mapping 表
            self._client.execute(
                """INSERT INTO instrument_mapping
                (instrument_id, source, source_ticker, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    registration.source,
                    registration.source_ticker,
                    registration.list_date,
                ],
            )

            # 失效相关缓存
            if self._cache:
                # 失效特定 source_ticker 的缓存
                cache_key = (
                    f"instrument_id:{registration.source_ticker}:"
                    f"{registration.source}:current"
                )
                self._cache.invalidate(cache_key)
                # 失效 instrument_id_symbol_map 缓存
                self._cache.invalidate_pattern("instrument_id_symbol_map:*")

            self._client.commit()

            logger.info(
                "Instrument registered successfully",
                event="instrument_register_complete",
                instrument_id=instrument_id,
                symbol=registration.symbol,
            )

            return instrument_id

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Instrument registration failed",
                event="instrument_register_failed",
                instrument_id=instrument_id,
                symbol=registration.symbol,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
