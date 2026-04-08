"""
MetadataService - Metadata 域统一查询服务（门面模式）.

整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
"""

from datetime import date
from typing import Any, Literal

import polars as pl
from ditto_infra.foundation import logger
from ditto_kernel.identity import InstrumentId as _InstrumentId

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
from ditto_data.sources import ExchangeTransformers
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

InstrumentId = _InstrumentId

__all__ = ["MetadataService"]


class MetadataService:
    """
    Metadata 域统一查询服务（门面）.

    整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
    内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

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
        内部构建三个子服务实例，所有方法委托到对应子服务。

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

        # 保留原始属性引用以支持直接访问（测试兼容性）
        self._instrument_reader = instrument_reader
        self._instrument_writer = instrument_writer
        self._name_history_reader = name_history_reader
        self._name_history_writer = name_history_writer
        self._calendar_reader = calendar_reader
        self._calendar_writer = calendar_writer
        self._industry_reader = industry_reader
        self._industry_writer = industry_writer
        self._industry_mapping_reader = industry_mapping_reader
        self._industry_mapping_writer = industry_mapping_writer
        self._universe_reader = universe_reader
        self._universe_writer = universe_writer
        self._rebalance_reader = rebalance_reader
        self._rebalance_writer = rebalance_writer
        self._instrument_id_allocator = instrument_id_allocator
        self._index_composition_reader = index_composition_reader
        self._exchange_transformers = exchange_transformers

        logger.debug(
            "MetadataService initialized (facade)",
            event="metadata_query_service_init_complete",
        )

    # ============ 交易日历查询（→ CalendarService） ============

    def list_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """查询交易日列表。委托到 CalendarService."""
        return self._calendar.list_trading_days(start, end, only_open)

    def list_calendar_range(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """查询日历数据（DataFrame 格式）。委托到 CalendarService."""
        return self._calendar.list_calendar_range(start, end, only_open)

    def save_calendar(self, records: list[dict[str, Any]]) -> int:
        """插入或更新日历记录。委托到 CalendarService."""
        return self._calendar.save_calendar(records)

    def is_trading_day(self, date: str) -> bool:
        """判断是否为交易日。委托到 CalendarService."""
        return self._calendar.is_trading_day(date)

    def get_last_trading_day(self) -> str | None:
        """获取最后一个交易日。委托到 CalendarService."""
        return self._calendar.get_last_trading_day()

    def get_first_trading_day(self) -> str | None:
        """获取第一个交易日。委托到 CalendarService."""
        return self._calendar.get_first_trading_day()

    def update_half_days(self, half_days: list[str]) -> int:
        """批量更新半日交易标记。委托到 CalendarService."""
        return self._calendar.update_half_days(half_days)

    def enrich_calendar(self, start: str, end: str) -> int:
        """丰富日历数据。委托到 CalendarService."""
        return self._calendar.enrich_calendar(start, end)

    def auto_enrich_calendar(self) -> int:
        """自动丰富所有未处理的日历数据。委托到 CalendarService."""
        return self._calendar.auto_enrich_calendar()

    # ============ Identity 解析（→ InstrumentService） ============

    def resolve_instrument_id(
        self,
        identifier: str,
        source: str,
        asof: str | None,
    ) -> int | None:
        """解析标识符到 instrument_id。委托到 InstrumentService."""
        return self._instrument.resolve_instrument_id(identifier, source, asof)

    def resolve_instrument_ids_batch(
        self,
        identifiers: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """批量解析标识符到 instrument_id。委托到 InstrumentService."""
        return self._instrument.resolve_instrument_ids_batch(identifiers, source, asof)

    # ============ 证券查询（→ InstrumentService） ============

    def get_instrument(self, instrument_id: int) -> dict[str, Any] | None:
        """获取单个证券信息。委托到 InstrumentService."""
        return self._instrument.get_instrument(instrument_id)

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

    def get_ticker(self, instrument_id: int) -> str | None:
        """根据 instrument_id 获取裸代码。委托到 InstrumentService."""
        return self._instrument.get_ticker(instrument_id)

    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """根据 instrument_id 获取源代码。委托到 InstrumentService."""
        return self._instrument.get_source_ticker(instrument_id, source, asof)

    # ============ 行业查询（→ InstrumentService） ============

    def find_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """多维查询行业数据。委托到 InstrumentService."""
        return self._instrument.find_industries(is_active, industry_level)

    def list_industry_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """查询行业成分股。委托到 InstrumentService."""
        return self._instrument.list_industry_stocks(industry_id, asof)

    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """查询股票所属行业。委托到 InstrumentService."""
        return self._instrument.get_stock_industry(instrument_id, asof)

    # ============ 状态查询 PIT（→ InstrumentService） ============

    def get_stock_status(
        self,
        instrument_id: int,
        asof: str,
    ) -> dict[str, Any]:
        """获取股票在指定时间点的状态（PIT 查询）。委托到 InstrumentService."""
        return self._instrument.get_stock_status(instrument_id, asof)

    # ============ 标的池查询（→ UniverseService） ============

    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """查询标的池成分股。委托到 UniverseService."""
        return self._universe.get_universe(universe_id, asof)

    def get_filtered_universe(
        self,
        universe_id: str,
        asof: str | None = None,
        volume_map: dict[int, float] | None = None,
        min_avg_volume: float | None = None,
        min_list_days: int = 0,
    ) -> list[int]:
        """获取过滤后的标的池成分股。委托到 UniverseService."""
        return self._universe.get_filtered_universe(
            universe_id,
            asof,
            volume_map,
            min_avg_volume,
            min_list_days,
        )

    def universe_intersection(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """两个标的池的交集。委托到 UniverseService."""
        return self._universe.universe_intersection(id_a, id_b, asof)

    def universe_union(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """两个标的池的并集。委托到 UniverseService."""
        return self._universe.universe_union(id_a, id_b, asof)

    def universe_subtract(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """标的池 A 减去 B 的差集。委托到 UniverseService."""
        return self._universe.universe_subtract(id_a, id_b, asof)

    def sync_index_universe(self, index_code: str, asof_date: date) -> int:
        """从指数成分数据同步到标的池。委托到 UniverseService."""
        return self._universe.sync_index_universe(index_code, asof_date)

    # ============ 证券注册（→ InstrumentService） ============

    def register_instrument(self, registration: InstrumentRegistration) -> int:
        """注册新证券。委托到 InstrumentService."""
        return self._instrument.register_instrument(registration)

    def register_instruments_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> tuple[str, str]:
        """批量注册证券（跳过已存在的）。委托到 InstrumentService."""
        return self._instrument.register_instruments_batch(
            df, source, asset_class, source_ticker_col
        )

    def resolve_or_create_instruments_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> dict[str, int]:
        """批量解析 source_ticker，不存在则自动创建证券。委托到 InstrumentService."""
        return self._instrument.resolve_or_create_instruments_batch(
            df, source, asset_class, source_ticker_col
        )

    # ============ 标识符解析（→ InstrumentService） ============

    def resolve_instrument_identifier(
        self,
        *,
        instrument_id: int | None = None,
        standard_ticker: str | None = None,
        ticker: str | None = None,
        asset_class: str | None = None,
        source: str,
        asof: str | None = None,
    ) -> InstrumentId | None:
        """统一标识符解析入口。委托到 InstrumentService。"""
        return self._instrument.resolve_instrument_identifier(
            instrument_id=instrument_id,
            standard_ticker=standard_ticker,
            ticker=ticker,
            asset_class=asset_class,
            source=source,
            asof=asof,
        )

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

    # ============ list_date 更新（→ InstrumentService） ============

    def update_list_date(self, instrument_id: int, list_date: Any) -> None:
        """更新证券的上市日期。委托到 InstrumentService."""
        return self._instrument.update_list_date(instrument_id, list_date)

    def find_instruments_without_list_date(
        self,
        asset_class: str | None = None,
    ) -> pl.DataFrame:
        """查找没有上市日期的证券。委托到 InstrumentService."""
        return self._instrument.find_instruments_without_list_date(asset_class)

    # ============ 证券名称查询（→ InstrumentService） ============

    def get_stock_name(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> str | None:
        """获取证券名称（支持 PIT 查询）。委托到 InstrumentService."""
        return self._instrument.get_stock_name(instrument_id, asof)

    # ============ 行业多级查询（→ InstrumentService） ============

    def get_stock_industries_all_levels(
        self,
        instrument_id: int,
        asof: str | None = None,
        source: str = "sw",
    ) -> list[dict[str, Any]]:
        """获取股票所有级别的行业分类。委托到 InstrumentService."""
        return self._instrument.get_stock_industries_all_levels(
            instrument_id, asof, source
        )

    # ============ 标的池调仓日程（→ UniverseService） ============

    def get_next_rebalance(
        self,
        universe_id: str,
        after_date: str,
    ) -> dict[str, Any] | None:
        """获取标的池下一次调仓日程。委托到 UniverseService."""
        return self._universe.get_next_rebalance(universe_id, after_date)

    def list_rebalances(self, universe_id: str) -> list[dict[str, Any]]:
        """列出标的池所有调仓日程。委托到 UniverseService."""
        return self._universe.list_rebalances(universe_id)
