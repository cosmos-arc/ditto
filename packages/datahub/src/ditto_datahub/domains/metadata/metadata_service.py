"""
MetadataService - Metadata 域统一查询服务.

整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口.

替代: SecuritiesAccessor + CalendarAccessor 的部分功能
"""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.checksum import ChecksumCompute

from ditto_datahub.domains.metadata.calendar.calendar_store import CalendarStore
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore
from ditto_datahub.domains.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.domains.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.domains.metadata.instrument.models import InstrumentRegistration
from ditto_datahub.domains.metadata.universe.universe_store import UniverseStore
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator


class MetadataService:
    """
    Metadata 域统一查询服务.

    整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口.

    替代: SecuritiesAccessor + CalendarAccessor 的部分功能
    """

    def __init__(
        self,
        instrument_store: InstrumentStore,
        identity_store: IdentityStore,
        calendar_store: CalendarStore,
        industry_basic_store: IndustryBasicStore,
        industry_mapping_store: IndustryMappingStore,
        universe_store: UniverseStore,
        instrument_id_allocator: InstrumentIdAllocator,
    ) -> None:
        """
        初始化 MetadataService.

        Args:
            instrument_store: 证券主数据存储.
            identity_store: Identity 映射存储.
            calendar_store: 交易日历存储.
            industry_basic_store: 行业主数据存储.
            industry_mapping_store: 行业映射存储.
            universe_store: 标的池存储.
            instrument_id_allocator: instrument_id 分配器.

        """
        self._instrument_store = instrument_store
        self._identity_store = identity_store
        self._calendar_store = calendar_store
        self._industry_basic_store = industry_basic_store
        self._industry_mapping_store = industry_mapping_store
        self._universe_store = universe_store
        self._instrument_id_allocator = instrument_id_allocator

        logger.debug(
            "MetadataService initialized",
            event="metadata_query_service_init_complete",
        )

    # ============ Identity 解析 ============

    @traced("metadata.identity.resolve_instrument_id")
    def resolve_instrument_id(
        self,
        identifier: str,
        source: str,
        asof: str | None,
    ) -> int | None:
        """
        解析标识符到 instrument_id.

        Args:
            identifier: 数据源代码 (source_ticker).
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            instrument_id 或 None.

        """
        return self._identity_store.resolve_instrument_id(identifier, source, asof)

    @traced("metadata.identity.resolve_instrument_ids_batch")
    def resolve_instrument_ids_batch(
        self,
        identifiers: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """
        批量解析标识符到 instrument_id.

        Args:
            identifiers: 数据源代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            {identifier: instrument_id} 映射字典.

        """
        return self._identity_store.resolve_instrument_ids_batch(
            identifiers, source, asof
        )

    # ============ 证券查询 ============

    @traced("metadata.security.get_securities")
    def get_securities(
        self,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        查询证券数据.

        Args:
            instrument_ids: 过滤 instrument_id 列表.
            source_tickers: 过滤源代码列表.
            source: 数据源标识.
            asset_class: 过滤资产类别.
            exchange: 过滤交易所.
            is_active: 过滤活跃状态.
            asof: 时间点日期.

        Returns:
            证券数据 DataFrame.

        """
        return self._instrument_store.find_securities(
            instrument_ids=instrument_ids,
            source_tickers=source_tickers,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

    @traced("metadata.security.get_symbol")
    def get_symbol(self, instrument_id: int) -> str | None:
        """
        根据 instrument_id 获取交易代码.

        Args:
            instrument_id: instrument_id.

        Returns:
            交易代码 或 None.

        """
        return self._instrument_store.get_symbol(instrument_id)

    @traced("metadata.security.get_source_ticker")
    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        根据 instrument_id 获取源代码.

        Args:
            instrument_id: instrument_id.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            源代码 或 None.

        """
        return self._identity_store.get_source_ticker(instrument_id, source, asof)

    # ============ 行业查询 ============

    @traced("metadata.industry.get_industries")
    def get_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        查询行业数据.

        Args:
            is_active: 是否只返回活跃行业.
            industry_level: 行业级别过滤.

        Returns:
            行业数据 DataFrame.

        """
        return self._industry_basic_store.get_all(is_active, industry_level)

    @traced("metadata.industry.get_stock_industry")
    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        查询股票所属行业.

        Args:
            instrument_id: 证券 ID.
            asof: 时间点日期.

        Returns:
            行业映射信息 或 None.

        """
        return self._industry_mapping_store.get_stock_industry(instrument_id, asof)

    @traced("metadata.industry.get_industry_stocks")
    def get_industry_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询行业成分股.

        Args:
            industry_id: 行业 ID.
            asof: 时间点日期.

        Returns:
            SID 列表.

        """
        return self._industry_mapping_store.get_stocks(industry_id, asof)

    # ============ 交易日历查询 ============

    @traced("metadata.calendar.get_range_df")
    def get_range_df(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        查询日历数据（DataFrame 格式）.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            日历数据 DataFrame，包含 trade_date, is_open, prev_trade_date 等列.

        """
        return self._calendar_store.get_range_df(start, end, only_open)

    @traced("metadata.calendar.get_trading_days")
    def get_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """
        查询交易日列表.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            交易日列表.

        """
        return self._calendar_store.get_range(start, end)

    @traced("metadata.calendar.is_trading_day")
    def is_trading_day(self, date: str) -> bool:
        """
        判断是否为交易日.

        Args:
            date: 日期字符串.

        Returns:
            是否为交易日.

        """
        return self._calendar_store.is_trading_day(date)

    @traced("metadata.calendar.upsert")
    def upsert(self, records: list[dict[str, Any]]) -> int:
        """
        插入或更新日历记录.

        Args:
            records: 日历记录列表.

        Returns:
            插入的记录数.

        """
        self._calendar_store.upsert(records)
        return len(records)

    @traced("metadata.calendar.get_last_trading_day")
    def get_last_trading_day(self) -> str | None:
        """
        获取最后一个交易日.

        Returns:
            最后一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_store.get_last_trading_day()

    @traced("metadata.calendar.get_first_trading_day")
    def get_first_trading_day(self) -> str | None:
        """
        获取第一个交易日.

        Returns:
            第一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_store.get_first_trading_day()

    @traced("metadata.calendar.list_trading_days")
    def list_trading_days(self, start: str, end: str) -> list[str]:
        """
        获取交易日列表（别名方法，与 get_trading_days 相同）.

        Args:
            start: 开始日期.
            end: 结束日期.

        Returns:
            交易日列表.

        """
        return self.get_trading_days(start, end, only_open=True)

    # ============ 标的池查询 ============

    @traced("metadata.universe.get_universe")
    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询标的池成分股.

        Args:
            universe_id: 标的池 ID.
            asof: 时间点日期.

        Returns:
            SID 列表.

        """
        return self._universe_store.get_constituents_sids(universe_id, asof)

    # ============ 证券注册 ============

    @traced("metadata.security.register_security")
    def register_security(self, registration: InstrumentRegistration) -> int:
        """
        注册新证券.

        Args:
            registration: 证券注册信息.

        Returns:
            分配的 instrument_id.

        """
        # 分配 instrument_id
        instrument_id = self._instrument_id_allocator.allocate(registration.asset_class)

        # 注册到 security_store
        registered_id = self._instrument_store.register(instrument_id, registration)

        logger.info(
            "Security registered via MetadataService",
            event="metadata_security_registered",
            instrument_id=registered_id,
            symbol=registration.symbol,
            source_ticker=registration.source_ticker,
        )

        return registered_id

    @traced("metadata.security.register_securities_batch")
    def register_securities_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        source_ticker_col: str = "source_ticker",
    ) -> tuple[str, str]:
        """
        批量注册证券（跳过已存在的）。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - symbol: 显示符号
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符
            asset_class: 资产类别
            source_ticker_col: DataFrame 中源代码的列名

        Returns:
            (file_path, checksum) 元组

        """
        logger.info(
            "Starting batch instrument registration",
            event="instrument_batch_register_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        registered_count = 0
        skipped_count = 0

        for row in df.to_dicts():
            source_ticker = row[source_ticker_col]

            # 检查是否已存在
            existing_instrument_id = self._instrument_store.resolve_instrument_id(
                source_ticker, source, None
            )
            if existing_instrument_id is not None:
                skipped_count += 1
                continue

            # 注册新证券
            self.register_security(
                InstrumentRegistration(
                    source_ticker=source_ticker,
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    source=source,
                    board=row.get("board"),
                )
            )
            registered_count += 1

        # 计算 checksum
        dataset_name = f"{asset_class}_basic"
        df_with_source = df.with_columns(pl.lit(source).alias("source"))
        checksum = ChecksumCompute.from_dataframe(df_with_source, dataset_name)

        file_path = f"instrument_store:{asset_class}_basic"

        logger.info(
            "Batch instrument registration completed",
            event="instrument_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            checksum=checksum,
        )

        return file_path, checksum

    @traced("metadata.security.resolve_or_create_batch")
    def resolve_or_create_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        source_ticker_col: str = "source_ticker",
    ) -> dict[str, int]:
        """
        批量解析 source_ticker，不存在则自动创建证券。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - symbol: 显示符号
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符
            asset_class: 资产类别
            source_ticker_col: DataFrame 中源代码的列名

        Returns:
            {source_ticker: instrument_id} 映射字典

        """
        logger.debug(
            "Resolving or creating instruments in batch",
            event="instrument_resolve_or_create_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        result: dict[str, int] = {}
        created_count = 0

        # 处理空 DataFrame
        if len(df) == 0:
            return result

        # 验证必需列
        required_cols = [
            source_ticker_col,
            "symbol",
            "name",
            "exchange",
            "list_date",
        ]
        for col in required_cols:
            if col not in df.columns:
                msg = f"DataFrame 缺少必需列: {col}"
                raise KeyError(msg)

        # 批量查询已存在的证券
        source_tickers = df[source_ticker_col].to_list()
        existing_mappings = self._instrument_store.resolve_instrument_ids_batch(
            source_tickers, source, None
        )

        # 处理每一行
        for row in df.to_dicts():
            source_ticker = row[source_ticker_col]

            # 如果已存在，使用已有的 instrument_id
            if source_ticker in existing_mappings:
                result[source_ticker] = existing_mappings[source_ticker]
                continue

            # 不存在则创建新证券
            instrument_id = self.register_security(
                InstrumentRegistration(
                    source_ticker=source_ticker,
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    source=source,
                )
            )
            result[source_ticker] = instrument_id
            created_count += 1

        logger.debug(
            "Batch resolve or create completed",
            event="security_resolve_or_create_complete",
            total_count=len(result),
            created_count=created_count,
        )

        return result
