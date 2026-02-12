"""
MetadataService - Metadata 域统一查询服务.

整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口.

CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
"""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.checksum import ChecksumCompute

from ditto_datahub.models.metadata import InstrumentRegistration
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.stores.metadata.calendar import CalendarReader, CalendarWriter
from ditto_datahub.stores.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_datahub.stores.metadata.instrument import (
    InstrumentReader,
    InstrumentWriter,
)
from ditto_datahub.stores.metadata.universe import UniverseReader, UniverseWriter


class MetadataService:
    """
    Metadata 域统一查询服务.

    整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口.

    CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
    """

    def __init__(  # noqa: PLR0913
        self,
        instrument_reader: InstrumentReader,
        instrument_writer: InstrumentWriter,
        calendar_reader: CalendarReader,
        calendar_writer: CalendarWriter,
        industry_reader: IndustryReader,
        industry_writer: IndustryWriter,
        industry_mapping_reader: IndustryMappingReader,
        industry_mapping_writer: IndustryMappingWriter,
        universe_reader: UniverseReader,
        universe_writer: UniverseWriter,
        instrument_id_allocator: InstrumentIdAllocator,
    ) -> None:
        """
        初始化 MetadataService.

        Args:
            instrument_reader: 证券主数据读取器.
            instrument_writer: 证券主数据写入器.
            calendar_reader: 交易日历读取器.
            calendar_writer: 交易日历写入器.
            industry_reader: 行业主数据读取器.
            industry_writer: 行业主数据写入器.
            industry_mapping_reader: 行业映射读取器.
            industry_mapping_writer: 行业映射写入器.
            universe_reader: 标的池读取器.
            universe_writer: 标的池写入器.
            instrument_id_allocator: instrument_id 分配器.

        """
        self._instrument_reader = instrument_reader
        self._instrument_writer = instrument_writer
        self._calendar_reader = calendar_reader
        self._calendar_writer = calendar_writer
        self._industry_reader = industry_reader
        self._industry_writer = industry_writer
        self._industry_mapping_reader = industry_mapping_reader
        self._industry_mapping_writer = industry_mapping_writer
        self._universe_reader = universe_reader
        self._universe_writer = universe_writer
        self._instrument_id_allocator = instrument_id_allocator

        logger.debug(
            "MetadataService initialized",
            event="metadata_query_service_init_complete",
        )

    # ============ 交易日历查询 ============

    @traced("metadata.calendar.list_trading_days")
    def list_trading_days(
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
        return self._calendar_reader.get_range(start, end)

    @traced("metadata.calendar.list_calendar_range")
    def list_calendar_range(
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
        return self._calendar_reader.get_range_df(start, end, only_open)

    @traced("metadata.calendar.save_calendar")
    def save_calendar(self, records: list[dict[str, Any]]) -> int:
        """
        插入或更新日历记录.

        Args:
            records: 日历记录列表.

        Returns:
            插入的记录数.

        """
        self._calendar_writer.upsert(records)
        return len(records)

    @traced("metadata.calendar.is_trading_day")
    def is_trading_day(self, date: str) -> bool:
        """
        判断是否为交易日.

        Args:
            date: 日期字符串.

        Returns:
            是否为交易日.

        """
        return self._calendar_reader.is_trading_day(date)

    @traced("metadata.calendar.get_last_trading_day")
    def get_last_trading_day(self) -> str | None:
        """
        获取最后一个交易日.

        Returns:
            最后一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_reader.get_last_trading_day()

    @traced("metadata.calendar.get_first_trading_day")
    def get_first_trading_day(self) -> str | None:
        """
        获取第一个交易日.

        Returns:
            第一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_reader.get_first_trading_day()

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
        return self._instrument_reader.resolve_instrument_id(identifier, source, asof)

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
        return self._instrument_reader.resolve_instrument_ids_batch(
            identifiers, source, asof
        )

    # ============ 证券查询 ============

    @traced("metadata.instrument.get_instrument")
    def get_instrument(self, instrument_id: int) -> dict[str, Any] | None:
        """
        获取单个证券信息.

        Args:
            instrument_id: 证券 ID.

        Returns:
            证券信息字典，未找到时返回 None.

        """
        return self._instrument_reader.get_by_instrument_id(instrument_id)

    @traced("metadata.instrument.find_securities")
    def find_securities(
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
        多维查询证券数据.

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
        return self._instrument_reader.find_securities(
            instrument_ids=instrument_ids,
            source_tickers=source_tickers,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

    @traced("metadata.instrument.list_instrument_ids")
    def list_instrument_ids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
    ) -> list[int]:
        """
        列出所有 instrument_id（可选过滤）.

        Args:
            asset_class: 按资产类别过滤.
            exchange: 按交易所过滤.
            is_active: 按活跃状态过滤.

        Returns:
            instrument_id 列表.

        """
        return self._instrument_reader.list_instrument_ids(
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

    @traced("metadata.instrument.get_symbol")
    def get_symbol(self, instrument_id: int) -> str | None:
        """
        根据 instrument_id 获取交易代码.

        Args:
            instrument_id: instrument_id.

        Returns:
            交易代码 或 None.

        """
        return self._instrument_reader.get_symbol(instrument_id)

    @traced("metadata.instrument.get_source_ticker")
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
        return self._instrument_reader.get_source_ticker(instrument_id, source, asof)

    # ============ 行业查询 ============

    @traced("metadata.industry.find_industries")
    def find_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        多维查询行业数据.

        Args:
            is_active: 是否只返回活跃行业.
            industry_level: 行业级别过滤.

        Returns:
            行业数据 DataFrame.

        """
        return self._industry_reader.get_all(is_active, industry_level)

    @traced("metadata.industry.list_industry_stocks")
    def list_industry_stocks(
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
            Instrument ID 列表.

        """
        return self._industry_mapping_reader.get_stocks(industry_id, asof)

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
        return self._industry_mapping_reader.get_stock_industry(instrument_id, asof)

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
            Instrument ID 列表.

        """
        return self._universe_reader.get_constituent_instrument_ids(universe_id, asof)

    # ============ 证券注册 ============

    @traced("metadata.instrument.register_instrument")
    def register_instrument(self, registration: InstrumentRegistration) -> int:
        """
        注册新证券.

        Args:
            registration: 证券注册信息.

        Returns:
            分配的 instrument_id.

        """
        # 分配 instrument_id
        instrument_id = self._instrument_id_allocator.allocate(registration.asset_class)

        # 注册到 instrument_writer
        registered_id = self._instrument_writer.register(instrument_id, registration)

        logger.info(
            "Instrument registered via MetadataService",
            event="metadata_instrument_registered",
            instrument_id=registered_id,
            symbol=registration.symbol,
            source_ticker=registration.source_ticker,
        )

        return registered_id

    @traced("metadata.instrument.register_instruments_batch")
    def register_instruments_batch(
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
            existing_instrument_id = self._instrument_reader.resolve_instrument_id(
                source_ticker, source, None
            )
            if existing_instrument_id is not None:
                skipped_count += 1
                continue

            # 注册新证券
            self.register_instrument(
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

        file_path = f"instrument_reader:{asset_class}_basic"

        logger.info(
            "Batch instrument registration completed",
            event="instrument_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            checksum=checksum,
        )

        return file_path, checksum

    @traced("metadata.instrument.resolve_or_create_instruments_batch")
    def resolve_or_create_instruments_batch(
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
        existing_mappings = self._instrument_reader.resolve_instrument_ids_batch(
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
            instrument_id = self.register_instrument(
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
            event="instrument_resolve_or_create_complete",
            total_count=len(result),
            created_count=created_count,
        )

        return result
