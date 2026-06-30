"""
MetadataService - Metadata 域统一查询服务（门面模式）.

整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

子服务通过 public property 暴露（``svc.calendar``, ``svc.instrument``,
``svc.universe``），同时保留少量高频便捷方法以降低调用方认知负载。

CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast, overload

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

__all__ = ["MetadataService", "MetadataServiceDeps"]


@dataclass(frozen=True)
class MetadataServiceDeps:
    """MetadataService 依赖聚合 — 服务层首选构造协议."""

    instrument_reader: InstrumentReader
    instrument_writer: InstrumentWriter
    name_history_reader: NameHistoryReader
    name_history_writer: NameHistoryWriter
    calendar_reader: CalendarReader
    calendar_writer: CalendarWriter
    industry_reader: IndustryReader
    industry_writer: IndustryWriter
    industry_mapping_reader: IndustryMappingReader
    industry_mapping_writer: IndustryMappingWriter
    universe_reader: UniverseReader
    universe_writer: UniverseWriter
    rebalance_reader: RebalanceReader
    rebalance_writer: RebalanceWriter
    instrument_id_allocator: InstrumentIdAllocator
    index_composition_reader: IndexCompositionReader
    exchange_transformers: ExchangeTransformers


_LEGACY_DEPENDENCY_NAMES = (
    "instrument_reader",
    "instrument_writer",
    "name_history_reader",
    "name_history_writer",
    "calendar_reader",
    "calendar_writer",
    "industry_reader",
    "industry_writer",
    "industry_mapping_reader",
    "industry_mapping_writer",
    "universe_reader",
    "universe_writer",
    "rebalance_reader",
    "rebalance_writer",
    "instrument_id_allocator",
    "index_composition_reader",
    "exchange_transformers",
)

_LEGACY_DEPENDENCY_NAME_SET = frozenset(_LEGACY_DEPENDENCY_NAMES)

_SECURITY_QUERY_FILTER_NAMES = frozenset(
    {
        "instrument_ids",
        "source_tickers",
        "source",
        "asset_class",
        "exchange",
        "is_active",
        "asof",
        "min_list_days",
    }
)


class MetadataService:
    """
    Metadata 域统一查询服务（门面）.

    整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口。
    内部委托到三个子服务：CalendarService、InstrumentService、UniverseService。

    通过 ``calendar``, ``instrument``, ``universe`` 三个 public property
    暴露子服务的完整能力，同时保留高频便捷方法。

    CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
    """

    @overload
    def __init__(self, deps: MetadataServiceDeps) -> None: ...

    @overload
    def __init__(self, **legacy_ports: object) -> None: ...

    def __init__(
        self,
        deps: object | None = None,
        *legacy_args: object,
        **legacy_ports: object,
    ) -> None:
        """
        初始化 MetadataService（门面模式）.

        首选 ``MetadataServiceDeps`` 依赖对象；保留原始散装依赖调用作为
        兼容桥，便于分阶段迁移测试和调用方。
        内部构建三个子服务实例。

        Args:
            deps: MetadataServiceDeps 依赖聚合对象.
            legacy_args: 兼容旧 positional 依赖列表.
            legacy_ports: 兼容旧 keyword 依赖列表.

        """
        service_deps = _normalize_metadata_service_deps(
            deps,
            legacy_args,
            legacy_ports,
        )

        # 构建子服务
        self._calendar = CalendarService(
            service_deps.calendar_reader,
            service_deps.calendar_writer,
        )
        self._instrument = InstrumentService(
            InstrumentServiceDeps(
                instrument_reader=service_deps.instrument_reader,
                instrument_writer=service_deps.instrument_writer,
                name_history_reader=service_deps.name_history_reader,
                name_history_writer=service_deps.name_history_writer,
                industry_reader=service_deps.industry_reader,
                industry_writer=service_deps.industry_writer,
                industry_mapping_reader=service_deps.industry_mapping_reader,
                industry_mapping_writer=service_deps.industry_mapping_writer,
                instrument_id_allocator=service_deps.instrument_id_allocator,
                exchange_transformers=service_deps.exchange_transformers,
            ),
        )
        self._universe = UniverseService(
            universe_reader=service_deps.universe_reader,
            universe_writer=service_deps.universe_writer,
            instrument_reader=service_deps.instrument_reader,
            index_composition_reader=service_deps.index_composition_reader,
            rebalance_reader=service_deps.rebalance_reader,
            rebalance_writer=service_deps.rebalance_writer,
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
        **filters: object,
    ) -> pl.DataFrame:
        """多维查询证券数据。委托到 InstrumentService."""
        if query is not None:
            if filters:
                raise TypeError(
                    "find_securities accepts either a SecurityQuery or "
                    + "filter keywords, not both"
                )
            return self._instrument.find_securities(query)

        return self._instrument.find_securities(_security_query_from_filters(filters))

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


def _normalize_metadata_service_deps(
    deps: object | None,
    legacy_args: tuple[object, ...],
    legacy_ports: dict[str, object],
) -> MetadataServiceDeps:
    if isinstance(deps, MetadataServiceDeps):
        if legacy_args or legacy_ports:
            raise TypeError(
                "MetadataServiceDeps cannot be combined with legacy dependencies"
            )
        return deps

    if deps is None:
        return _metadata_service_deps_from_legacy(legacy_args, legacy_ports)

    return _metadata_service_deps_from_legacy((deps, *legacy_args), legacy_ports)


def _metadata_service_deps_from_legacy(
    legacy_args: tuple[object, ...],
    legacy_ports: dict[str, object],
) -> MetadataServiceDeps:
    if len(legacy_args) > len(_LEGACY_DEPENDENCY_NAMES):
        raise TypeError("MetadataService received too many positional dependencies")

    ports = dict(legacy_ports)
    for name, value in zip(_LEGACY_DEPENDENCY_NAMES, legacy_args, strict=False):
        if name in ports:
            raise TypeError(f"MetadataService got duplicate dependency: {name}")
        ports[name] = value

    unexpected = sorted(set(ports) - _LEGACY_DEPENDENCY_NAME_SET)
    if unexpected:
        names = ", ".join(unexpected)
        raise TypeError(f"MetadataService got unexpected dependencies: {names}")

    missing = [name for name in _LEGACY_DEPENDENCY_NAMES if name not in ports]
    if missing:
        names = ", ".join(missing)
        raise TypeError(f"MetadataService missing dependencies: {names}")

    return MetadataServiceDeps(
        instrument_reader=cast(InstrumentReader, ports["instrument_reader"]),
        instrument_writer=cast(InstrumentWriter, ports["instrument_writer"]),
        name_history_reader=cast(NameHistoryReader, ports["name_history_reader"]),
        name_history_writer=cast(NameHistoryWriter, ports["name_history_writer"]),
        calendar_reader=cast(CalendarReader, ports["calendar_reader"]),
        calendar_writer=cast(CalendarWriter, ports["calendar_writer"]),
        industry_reader=cast(IndustryReader, ports["industry_reader"]),
        industry_writer=cast(IndustryWriter, ports["industry_writer"]),
        industry_mapping_reader=cast(
            IndustryMappingReader,
            ports["industry_mapping_reader"],
        ),
        industry_mapping_writer=cast(
            IndustryMappingWriter,
            ports["industry_mapping_writer"],
        ),
        universe_reader=cast(UniverseReader, ports["universe_reader"]),
        universe_writer=cast(UniverseWriter, ports["universe_writer"]),
        rebalance_reader=cast(RebalanceReader, ports["rebalance_reader"]),
        rebalance_writer=cast(RebalanceWriter, ports["rebalance_writer"]),
        instrument_id_allocator=cast(
            InstrumentIdAllocator,
            ports["instrument_id_allocator"],
        ),
        index_composition_reader=cast(
            IndexCompositionReader,
            ports["index_composition_reader"],
        ),
        exchange_transformers=cast(
            ExchangeTransformers,
            ports["exchange_transformers"],
        ),
    )


def _security_query_from_filters(filters: dict[str, object]) -> SecurityQuery:
    unexpected = sorted(set(filters) - _SECURITY_QUERY_FILTER_NAMES)
    if unexpected:
        names = ", ".join(unexpected)
        raise TypeError(f"find_securities got unexpected filters: {names}")

    return SecurityQuery(
        instrument_ids=cast(list[int] | None, filters.get("instrument_ids")),
        source_tickers=cast(list[str] | None, filters.get("source_tickers")),
        source=cast(str, filters.get("source", "tushare")),
        asset_class=cast(str | None, filters.get("asset_class")),
        exchange=cast(str | None, filters.get("exchange")),
        is_active=cast(bool | None, filters.get("is_active", True)),
        asof=cast(str | None, filters.get("asof")),
        min_list_days=cast(int | None, filters.get("min_list_days")),
    )
