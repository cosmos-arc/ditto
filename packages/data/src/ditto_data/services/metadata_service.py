"""
MetadataService - Metadata 域统一查询服务（门面模式）.

整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

子服务通过 public property 暴露（``svc.calendar``, ``svc.instrument``,
``svc.universe``），同时保留少量高频便捷方法以降低调用方认知负载。

CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
"""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.services.metadata.calendar import (
    CalendarService,
)
from ditto_data.services.metadata.instrument import (
    InstrumentService,
    InstrumentServiceDeps,
)
from ditto_data.services.metadata.universe import UniverseService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.storage.capital.index_composition import IndexCompositionReader
from ditto_data.storage.metadata.calendar import CalendarReader, CalendarWriter
from ditto_data.storage.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_data.storage.metadata.instrument import (
    InstrumentReader,
    InstrumentWriter,
    NameHistoryReader,
    NameHistoryWriter,
    SecurityQuery,
)
from ditto_data.storage.metadata.universe import (
    RebalanceReader,
    RebalanceWriter,
    UniverseReader,
    UniverseWriter,
)

__all__ = ["MetadataService"]


class MetadataService:
    """
    Metadata 域统一查询服务（门面）.

    整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
    内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

    通过 ``calendar``, ``instrument``, ``universe`` 三个 public property
    暴露子服务的完整能力，同时保留高频便捷方法。

    CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
    """

    def __init__(
        self,
        instrument_reader: InstrumentReader,
        instrument_writer: InstrumentWriter,
        name_history_reader: NameHistoryReader,
        name_history_writer: NameHistoryWriter,
        calendar_reader: CalendarReader,
        calendar_writer: CalendarWriter,
        industry_reader: IndustryReader,
        industry_writer: IndustryWriter,
        industry_mapping_reader: IndustryMappingReader,
        industry_mapping_writer: IndustryMappingWriter,
        universe_reader: UniverseReader,
        universe_writer: UniverseWriter,
        rebalance_reader: RebalanceReader,
        rebalance_writer: RebalanceWriter,
        instrument_id_allocator: InstrumentIdAllocator,
        index_composition_reader: IndexCompositionReader,
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """
        初始化 MetadataService（门面模式）.

        保留原始 17 个参数以保证 DI 注册和测试的向后兼容性。
        内部构建三个子服务实例。

        Args:
            instrument_reader: 证券主数据读取器.
            instrument_writer: 证券主数据写入器.
            name_history_reader: 证券名称变更历史读取器.
            name_history_writer: 证券名称变更历史写入器.
            calendar_reader: 交易日历读取器.
            calendar_writer: 交易日历写入器.
            industry_reader: 行业主数据读取器.
            industry_writer: 行业主数据写入器.
            industry_mapping_reader: 行业映射读取器.
            industry_mapping_writer: 行业映射写入器.
            universe_reader: 标的池读取器.
            universe_writer: 标的池写入器.
            rebalance_reader: 标的池调仓日程读取器.
            rebalance_writer: 标的池调仓日程写入器.
            instrument_id_allocator: instrument_id 分配器.
            index_composition_reader: 指数成分股读取器.
            exchange_transformers: 交易所转换器工厂.

        """
        # 构建子服务
        self._calendar = CalendarService(calendar_reader, calendar_writer)
        self._instrument = InstrumentService(
            InstrumentServiceDeps(
                instrument_reader=instrument_reader,
                instrument_writer=instrument_writer,
                name_history_reader=name_history_reader,
                name_history_writer=name_history_writer,
                industry_reader=industry_reader,
                industry_writer=industry_writer,
                industry_mapping_reader=industry_mapping_reader,
                industry_mapping_writer=industry_mapping_writer,
                instrument_id_allocator=instrument_id_allocator,
                exchange_transformers=exchange_transformers,
            ),
        )
        self._universe = UniverseService(
            universe_reader=universe_reader,
            universe_writer=universe_writer,
            instrument_reader=instrument_reader,
            index_composition_reader=index_composition_reader,
            rebalance_reader=rebalance_reader,
            rebalance_writer=rebalance_writer,
        )

        logger.debug(
            "MetadataService initialized (facade)",
            event="metadata_query_service_init_complete",
        )

    # ============ 子服务 property ============

    @property
    def calendar(self) -> CalendarService:
        """交易日历子服务."""
        return self._calendar

    @property
    def instrument(self) -> InstrumentService:
        """证券/工具子服务."""
        return self._instrument

    @property
    def universe(self) -> UniverseService:
        """标的池子服务."""
        return self._universe

    # ============ 高频便捷方法（< 10） ============

    def list_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """查询交易日列表。委托到 CalendarService."""
        return self._calendar.list_trading_days(start, end, only_open)

    def is_trading_day(self, date: str) -> bool:
        """判断是否为交易日。委托到 CalendarService."""
        return self._calendar.is_trading_day(date)

    def get_last_trading_day(self) -> str | None:
        """获取最后一个交易日。委托到 CalendarService."""
        return self._calendar.get_last_trading_day()

    def find_securities(
        self,
        query: SecurityQuery | None = None,
        *,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
        min_list_days: int | None = None,
    ) -> pl.DataFrame:
        """多维查询证券数据。委托到 InstrumentService."""
        if query is not None:
            return self._instrument.find_securities(query)

        return self._instrument.find_securities(
            SecurityQuery(
                instrument_ids=instrument_ids,
                source_tickers=source_tickers,
                source=source,
                asset_class=asset_class,
                exchange=exchange,
                is_active=is_active,
                asof=asof,
                min_list_days=min_list_days,
            ),
        )

    def list_instrument_ids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
    ) -> list[int]:
        """列出所有 instrument_id（可选过滤）。委托到 InstrumentService."""
        return self._instrument.list_instrument_ids(
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

    def register_instrument(self, registration: InstrumentRegistration) -> int:
        """注册新证券。委托到 InstrumentService."""
        return self._instrument.register_instrument(registration)

    def resolve_instrument_id(
        self,
        identifier: str,
        source: str,
        asof: str | None,
    ) -> int | None:
        """解析标识符到 instrument_id。委托到 InstrumentService."""
        return self._instrument.resolve_instrument_id(identifier, source, asof)

    def resolve_source_ticker(
        self,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str = "stock",
        source: str = "tushare",
        asof: str | None = None,
    ) -> str:
        """将任意标识符解析为 source_ticker。委托到 InstrumentService."""
        return self._instrument.resolve_source_ticker(
            ticker,
            standard_ticker,
            instrument_id,
            asset_class,
            source,
            asof,
        )

    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """查询标的池成分股。委托到 UniverseService."""
        return self._universe.get_universe(universe_id, asof)
