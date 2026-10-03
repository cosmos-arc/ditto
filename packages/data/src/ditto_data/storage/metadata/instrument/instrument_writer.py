"""InstrumentWriter - 证券主数据写入接口."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from ditto_platform.foundation import DataCache, SQLiteClient, logger

from ditto_data.models.metadata import (
    ETFExtension,
    IndexExtension,
    InstrumentExtension,
    InstrumentRegistration,
    StockExtension,
)


class InstrumentWriter:
    """
    证券主数据写入接口。

    提供：
    - register() - 注册新证券（事务性操作 + 缓存失效 + 扩展信息自动路由）

    Attributes:
        _client: SQLite 客户端，用于数据库访问
        _cache: DataCache 缓存管理器（可选）

    """

    # 类型路由表：根据扩展类型分发到对应的注册方法
    _EXTENSION_ROUTES: ClassVar[dict[Any, str]] = {
        StockExtension: "_register_stock",
        ETFExtension: "_register_etf",
        IndexExtension: "_register_index",
    }

    def __init__(
        self, client: SQLiteClient, cache: DataCache[Any] | None = None
    ) -> None:
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

        扩展信息自动路由到对应的扩展表（使用 Protocol + 类型路由）。

        Args:
            instrument_id: 证券 ID
            registration: 证券注册配置（可选扩展信息）

        Returns:
            注册的 instrument_id

        Raises:
            Exception: 数据库操作失败时（已回滚）

        """
        logger.info(
            "Starting instrument registration",
            event="instrument_register_start",
            instrument_id=instrument_id,
            ticker=registration.ticker,
            source_ticker=registration.source_ticker,
            source=registration.source,
            asset_class=registration.asset_class,
            exchange=registration.exchange,
        )

        try:
            # 插入 instrument 表（注册即带退市证据时直接落 inactive 状态，
            # 退市更新仅用于已注册证券后续发生退市的场景）
            self._client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, ticker, name, exchange, board, asset_class,
                    list_date, delist_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    instrument_id,
                    registration.ticker,
                    registration.name,
                    registration.exchange,
                    registration.board,
                    registration.asset_class,
                    registration.list_date,
                    registration.delist_date,
                    registration.delist_date is None,
                ],
            )

            # 插入 instrument_mapping 表
            # effective_from 使用 list_date，若为 NULL 则使用默认值
            effective_from = registration.list_date or "1990-01-01"
            self._client.execute(
                """INSERT INTO instrument_mapping
                (instrument_id, source, source_ticker, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    registration.source,
                    registration.source_ticker,
                    effective_from,
                ],
            )

            # 路由扩展信息到对应表（新增）
            if registration.extension:
                self._register_extension(instrument_id, registration.extension)

            # 失效相关缓存
            if self._cache:
                # 失效特定 source_ticker 的缓存
                cache_key = (
                    f"instrument_id:{registration.source_ticker}:"
                    f"{registration.source}:current"
                )
                self._cache.invalidate(cache_key)
                # 失效 instrument_id_ticker_map 缓存
                self._cache.invalidate_pattern("instrument_id_ticker_map:*")

            self._client.commit()

            logger.info(
                "Instrument registered successfully",
                event="instrument_register_complete",
                instrument_id=instrument_id,
                ticker=registration.ticker,
            )

            return instrument_id

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Instrument registration failed",
                event="instrument_register_failed",
                instrument_id=instrument_id,
                ticker=registration.ticker,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise

    def _register_extension(
        self, instrument_id: int, extension: InstrumentExtension
    ) -> None:
        """
        内部方法：根据扩展类型路由到对应表。

        使用类型路由表避免 if-elif 链，符合开闭原则。

        Args:
            instrument_id: 证券 ID
            extension: 扩展信息对象

        """
        extension_type = type(extension)
        method_name = self._EXTENSION_ROUTES.get(extension_type)

        if method_name:
            method = getattr(self, method_name)
            method(instrument_id, extension)
            logger.info(
                "Instrument extension registered",
                event="instrument_extension_registered",
                instrument_id=instrument_id,
                extension_type=extension_type.__name__,
            )
        else:
            logger.warning(
                "Unknown extension type, skipping",
                event="instrument_extension_unknown",
                instrument_id=instrument_id,
                extension_type=extension_type.__name__,
            )

    def _register_stock(self, instrument_id: int, extension: StockExtension) -> None:
        """注册股票扩展信息"""
        self._client.execute(
            """INSERT OR REPLACE INTO instrument_stock
            (instrument_id, list_status, industry_id)
            VALUES (?, ?, ?)""",
            [instrument_id, extension.list_status, extension.industry_id],
        )

    def _register_etf(self, instrument_id: int, extension: ETFExtension) -> None:
        """注册 ETF 扩展信息"""
        self._client.execute(
            """INSERT OR REPLACE INTO instrument_etf
            (instrument_id, fund_type, fund_manager, establish_date, tracking_index)
            VALUES (?, ?, ?, ?, ?)""",
            [
                instrument_id,
                extension.fund_type,
                extension.fund_manager,
                extension.establish_date,
                extension.tracking_index,
            ],
        )

    def _register_index(self, instrument_id: int, extension: IndexExtension) -> None:
        """注册指数扩展信息"""
        self._client.execute(
            """INSERT OR REPLACE INTO instrument_index
            (instrument_id, base_date, base_point, num_constituents)
            VALUES (?, ?, ?, ?)""",
            [
                instrument_id,
                extension.base_date,
                extension.base_point,
                extension.num_constituents,
            ],
        )

    def register_source_mapping(
        self,
        *,
        instrument_id: int,
        source: str,
        source_ticker: str,
        effective_from: str,
        observed_at: str,
    ) -> bool:
        """
        为已注册证券登记一条来源映射（幂等，冲突拒绝）。

        语义：
        - 同 (source, source_ticker) 已在生效区间内映射到同一 instrument_id
          → 幂等跳过（返回 True，不重复写）。
        - 同 (source, source_ticker) 在重叠生效区间内映射到不同 instrument_id
          → 拒绝（返回 False，不写入）。
        - 否则写入映射行，created_at = 观察时间。

        Args:
            instrument_id: 目标证券 ID.
            source: 数据源标识（如 "fuyao"）.
            source_ticker: 源代码（如 "600000.SH"）.
            effective_from: 有证据的最早日期（不得用默认日期冒充真实历史）.
            observed_at: 观察时间（写入 created_at）.

        Returns:
            True 表示映射可用（已存在或新写入）；False 表示冲突拒绝.

        """
        rows = self._client.fetchall(
            """SELECT instrument_id, effective_from, effective_to
            FROM instrument_mapping
            WHERE source = ? AND source_ticker = ?""",
            [source, source_ticker],
        )
        for row in rows:
            same_instrument = int(row["instrument_id"]) == instrument_id
            # 与新开放区间 [effective_from, ∞) 重叠的已有区间：
            # effective_to 为空或晚于新起点即重叠。
            overlaps = row["effective_to"] is None or str(row["effective_to"]) > str(
                effective_from
            )
            if same_instrument and overlaps:
                return True  # 幂等：已有同向映射覆盖，不重复写
            if not same_instrument and overlaps:
                logger.warning(
                    "Source mapping conflict rejected",
                    event="instrument_source_mapping_conflict",
                    source=source,
                    source_ticker=source_ticker,
                    existing_instrument_id=int(row["instrument_id"]),
                    new_instrument_id=instrument_id,
                    effective_from=effective_from,
                )
                return False
        self._client.execute(
            """INSERT OR IGNORE INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from,
             is_primary, created_at)
            VALUES (?, ?, ?, ?, FALSE, ?)""",
            [instrument_id, source, source_ticker, effective_from, observed_at],
        )
        self._client.commit()
        if self._cache is not None:
            self._cache.invalidate(f"instrument_id:{source_ticker}:{source}:current")
        return True

    def apply_delisting(self, instrument_id: int, delist_date: str) -> None:
        """
        退市发生时更新 instrument.delist_date/is_active。

        历史池成员不删除：is_active=False 的行仍在 instrument 表中，
        历史宇宙按 delist_date 判定可见性。已有更早退市日期时不回退。

        Args:
            instrument_id: 证券 ID.
            delist_date: 退市日期（真实生效日期，不得为默认占位）.

        """
        current = self._client.fetchone(
            "SELECT delist_date FROM instrument WHERE instrument_id = ?",
            [instrument_id],
        )
        if current is None:
            logger.warning(
                "Delisting update skipped for unknown instrument",
                event="instrument_delist_unknown",
                instrument_id=instrument_id,
            )
            return
        existing = current["delist_date"]
        if existing is not None and str(existing) <= str(delist_date):
            return  # 已有相同或更早的退市证据，不回退重写
        self._client.execute(
            """UPDATE instrument
            SET delist_date = ?, is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE instrument_id = ?""",
            [delist_date, instrument_id],
        )
        self._client.commit()
        logger.info(
            "Instrument delisting recorded",
            event="instrument_delist_recorded",
            instrument_id=instrument_id,
            delist_date=delist_date,
        )

    def update_list_date(
        self, instrument_id: int, list_date: date | str | None
    ) -> None:
        """
        更新证券的上市日期.

        用于从行情数据推断上市日期的场景。

        Args:
            instrument_id: 证券 ID
            list_date: 上市日期

        """
        self._client.execute(
            """UPDATE instrument SET list_date = ? WHERE instrument_id = ?""",
            [list_date, instrument_id],
        )
        self._client.commit()

        logger.info(
            "Instrument list_date updated",
            event="instrument_list_date_updated",
            instrument_id=instrument_id,
            list_date=str(list_date),
        )
