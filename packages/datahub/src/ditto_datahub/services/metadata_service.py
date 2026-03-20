"""
MetadataService - Metadata 域统一查询服务.

整合 Metadata 域所有 Reader/Writer 的功能，提供统一的访问入口.

CQRS 架构：使用 Reader 处理查询，Writer 处理写入。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import polars as pl
from ditto_infra.foundation import logger, traced
from ditto_infra.foundation.util.checksum import ChecksumCompute

from ditto_datahub.errors import AmbiguousTickerError, IdentifierNotFoundError
from ditto_datahub.models.metadata import (
    InstrumentExtension,
    InstrumentRegistration,
    StockExtension,
)
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.stores.capital.index_composition import IndexCompositionReader
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
    NameHistoryReader,
    NameHistoryWriter,
)
from ditto_datahub.stores.metadata.universe import (
    UniverseReader,
    UniverseWriter,
)


def _compute_calendar_enrichment(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    计算日历丰富字段（纯函数）.

    从仅有 trade_date/is_open 的基本日历数据，
    计算 prev_trade_date, next_trade_date, week_of_year,
    month, quarter, year, is_week_end, is_month_end, is_quarter_end.

    Args:
        days: 输入格式 [{"trade_date": "2024-01-02", "is_open": True}, ...]

    Returns:
        丰富后的完整 records 列表（仅包含 is_open=True 的交易日）.

    """
    if not days:
        return []

    # 筛选交易日并按 trade_date 排序
    trading_days = sorted(
        [d for d in days if d.get("is_open", False)],
        key=lambda d: d["trade_date"],
    )

    if not trading_days:
        return []

    results: list[dict[str, Any]] = []

    for i, day in enumerate(trading_days):
        d = date.fromisoformat(day["trade_date"])
        iso = d.isocalendar()
        month = d.month
        quarter = (month - 1) // 3 + 1

        prev_td: str | None = None
        next_td: str | None = None

        if i > 0:
            prev_td = trading_days[i - 1]["trade_date"]
        if i < len(trading_days) - 1:
            next_td = trading_days[i + 1]["trade_date"]

        # 周末/月末/季末: 比较当前和下一个交易日的对应周期
        is_week_end = False
        is_month_end = False
        is_quarter_end = False

        if next_td is not None:
            next_d = date.fromisoformat(next_td)
            next_iso = next_d.isocalendar()
            next_month = next_d.month
            next_quarter = (next_month - 1) // 3 + 1

            is_week_end = (iso[0], iso[1]) != (next_iso[0], next_iso[1])
            is_month_end = month != next_month
            is_quarter_end = quarter != next_quarter

        results.append(
            {
                "trade_date": day["trade_date"],
                "is_open": True,
                "exchange": day.get("exchange", "SSE"),
                "prev_trade_date": prev_td,
                "next_trade_date": next_td,
                "week_of_year": iso[1],
                "month": month,
                "quarter": quarter,
                "year": d.year,
                "is_week_end": is_week_end,
                "is_month_end": is_month_end,
                "is_quarter_end": is_quarter_end,
                "is_half_day": False,
                "is_special": bool(day.get("is_special", False)),
            }
        )

    return results


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
        rebalance_reader: Any,
        rebalance_writer: Any,
        instrument_id_allocator: InstrumentIdAllocator,
        index_composition_reader: IndexCompositionReader,
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """
        初始化 MetadataService.

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

    @traced("metadata.calendar.update_half_days")
    def update_half_days(self, half_days: list[str]) -> int:
        """
        批量更新半日交易标记.

        Args:
            half_days: 半日交易日期列表 (YYYY-MM-DD 格式).

        Returns:
            更新的记录数.

        """
        if not half_days:
            return 0
        records = [{"trade_date": d, "is_half_day": True} for d in half_days]
        return self._calendar_writer.upsert(records)

    @traced("metadata.calendar.enrich_calendar")
    def enrich_calendar(self, start: str, end: str) -> int:
        """
        丰富日历数据：计算 prev/next、周/月/季末标记.

        仅处理 prev_trade_date 为 NULL 的未丰富行。

        Args:
            start: 开始日期.
            end: 结束日期.

        Returns:
            更新的记录数.

        """
        df = self._calendar_reader.get_range_df(start, end, only_open=False)

        if df.is_empty():
            return 0

        # 筛选未丰富的行（prev_trade_date 为 null）
        unenriched = df.filter(pl.col("prev_trade_date").is_null())
        if unenriched.is_empty():
            return 0

        days = unenriched.to_dicts()
        enriched = _compute_calendar_enrichment(days)

        if not enriched:
            return 0

        self._calendar_writer.upsert(enriched)
        return len(enriched)

    @traced("metadata.calendar.auto_enrich_calendar")
    def auto_enrich_calendar(self) -> int:
        """
        自动丰富所有未处理的日历数据。

        自动确定日期范围（从第一个交易日到最后一个交易日），
        然后调用 enrich_calendar。

        Returns:
            更新的记录数。

        """
        first = self._calendar_reader.get_first_trading_day()
        last = self._calendar_reader.get_last_trading_day()
        if first is None or last is None:
            return 0
        return self.enrich_calendar(first, last)

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
    def find_securities(  # noqa: PLR0913
        self,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
        min_list_days: int | None = None,
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
            min_list_days: 最低上市天数（需配合 asof 使用）.

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
            min_list_days=min_list_days,
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

    @traced("metadata.instrument.get_ticker")
    def get_ticker(self, instrument_id: int) -> str | None:
        """
        根据 instrument_id 获取裸代码.

        Args:
            instrument_id: instrument_id.

        Returns:
            裸代码 或 None.

        """
        return self._instrument_reader.get_ticker(instrument_id)

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

    # ============ 状态查询 (PIT) ============

    @traced("metadata.instrument.get_stock_status")
    def get_stock_status(
        self,
        instrument_id: int,
        asof: str,
    ) -> dict[str, Any]:
        """
        获取股票在指定时间点的状态（PIT 查询）.

        通过 SQLite 中的 instrument 表获取 is_st 字段，
        通过 instrument_stock 表获取 list_status。
        完整 PIT 实现将通过 Parquet 数据源提供。

        Args:
            instrument_id: 证券 ID.
            asof: 时间点日期 (YYYY-MM-DD).

        Returns:
            包含 is_st, list_status, is_suspended 的字典。
            无数据时返回默认值。

        """
        defaults: dict[str, Any] = {
            "is_st": False,
            "list_status": "L",
            "is_suspended": False,
        }

        # 从 instrument 表获取 is_st
        instrument = self._instrument_reader.get_by_instrument_id(instrument_id)
        if instrument:
            defaults["is_st"] = bool(instrument.get("is_st", False))

        # 从 instrument_stock 表获取 list_status
        stock_ext = self._instrument_reader.get_stock_extension(instrument_id)
        if stock_ext:
            list_status = stock_ext.get("list_status", "L")
            defaults["list_status"] = list_status
            # P = 暂停上市, D = 退市 → 视为 suspended
            defaults["is_suspended"] = list_status in ("P", "D")

        return defaults

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

    @traced("metadata.universe.get_filtered_universe")
    def get_filtered_universe(
        self,
        universe_id: str,
        asof: str | None = None,
        volume_map: dict[int, float] | None = None,
        min_avg_volume: float | None = None,
        min_list_days: int = 0,
    ) -> list[int]:
        """
        获取过滤后的标的池成分股.

        支持两种过滤维度：
        - 流动性过滤：通过外部传入的 volume_map 进行成交量过滤
        - 上市天数过滤：排除上市时间不足 N 天的标的

        Args:
            universe_id: 标的池 ID.
            asof: 时间点日期（上市天数过滤时必需）.
            volume_map: {instrument_id: avg_volume} 外部传入的成交量数据.
            min_avg_volume: 最低平均成交量阈值.
            min_list_days: 最低上市天数（自然日），0 表示不过滤.

        Returns:
            过滤后的 instrument_id 列表.

        """
        ids = self._universe_reader.get_constituent_instrument_ids(universe_id, asof)

        # 上市天数过滤
        if min_list_days > 0:
            if asof is None:
                msg = "min_list_days > 0 时必须提供 asof 日期"
                raise ValueError(msg)
            ids = self._filter_by_list_days(ids, asof, min_list_days)

        # 流动性过滤
        if min_avg_volume is not None and volume_map is not None:
            ids = [iid for iid in ids if volume_map.get(iid, 0) >= min_avg_volume]

        return ids

    def _filter_by_list_days(
        self,
        instrument_ids: list[int],
        asof: str,
        min_list_days: int,
    ) -> list[int]:
        """
        按上市天数过滤 instrument_id 列表.

        查询各证券的 list_date，排除上市天数不足或 list_date 为 NULL 的标的。

        Args:
            instrument_ids: 待过滤的 instrument_id 列表.
            asof: 时间点日期 (YYYY-MM-DD).
            min_list_days: 最低上市天数（自然日）.

        Returns:
            过滤后的 instrument_id 列表.

        """
        if not instrument_ids:
            return []

        # 批量查询 list_date
        rows = self._instrument_reader.find_securities(
            instrument_ids=instrument_ids,
            is_active=None,
        ).select("instrument_id", "list_date")

        if rows.is_empty():
            return []

        asof_date = date.fromisoformat(asof)
        # 筛选：list_date 非空且 (asof_date - list_date).days >= min_list_days
        days_since_list = (asof_date - pl.col("list_date").dt.date()).dt.total_days()
        qualified = rows.filter(
            pl.col("list_date").is_not_null() & (days_since_list >= min_list_days)
        )

        return qualified["instrument_id"].to_list()

    @traced("metadata.universe.intersection")
    def universe_intersection(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        两个标的池的交集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            同时属于 A 和 B 的 instrument_id 列表.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a & set_b)

    @traced("metadata.universe.union")
    def universe_union(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        两个标的池的并集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            属于 A 或 B 的 instrument_id 列表（去重、排序）.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a | set_b)

    @traced("metadata.universe.subtract")
    def universe_subtract(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        标的池 A 减去 B 的差集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            属于 A 但不属于 B 的 instrument_id 列表（排序）.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a - set_b)

    @traced("metadata.universe.sync_index_universe")
    def sync_index_universe(self, index_code: str, asof_date: date) -> int:
        """
        从指数成分数据同步到标的池.

        查询 IndexCompositionReader 获取指定指数在 asof_date 的成分股，
        原子写入到 UniverseWriter（以 index_code 作为 universe_id）。

        Args:
            index_code: 指数代码（如 "399300.XSHE"），同时作为 universe_id.
            asof_date: 时间点查询日期.

        Returns:
            同步的成分股数量，无数据时返回 0.

        """
        df = self._index_composition_reader.get(index_code, asof_date)

        if df.is_empty():
            return 0

        records = df.select("instrument_id", "effective_from").to_dicts()
        return self._universe_writer.replace_constituents(
            index_code, records, str(asof_date)
        )

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
            ticker=registration.ticker,
            source_ticker=registration.source_ticker,
        )

        return registered_id

    @staticmethod
    def _build_extension(
        row: dict[str, Any], asset_class: str
    ) -> InstrumentExtension | None:
        """
        根据资产类型和行数据构建扩展信息.

        Args:
            row: 包含证券元数据的字典
            asset_class: 资产类别

        Returns:
            对应类型的 InstrumentExtension，如果不需要扩展信息则返回 None

        """
        if asset_class == "stock":
            # 股票扩展信息：list_status
            list_status = row.get("list_status")
            if list_status:
                return StockExtension(
                    instrument_id=0,  # 占位，实际值由 register_instrument 设置
                    list_status=list_status,
                    industry_id=None,
                )
        return None

    @traced("metadata.instrument.register_instruments_batch")
    def register_instruments_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> tuple[str, str]:
        """
        批量注册证券（跳过已存在的）。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - ticker: 裸代码
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
                    ticker=row["ticker"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    delist_date=row.get("delist_date"),
                    source=source,
                    board=row.get("board"),
                    extension=self._build_extension(row, asset_class),
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
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> dict[str, int]:
        """
        批量解析 source_ticker，不存在则自动创建证券。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - ticker: 裸代码
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
            "ticker",
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
                    ticker=row["ticker"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    delist_date=row.get("delist_date"),
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

    # ============ 标识符解析 ============

    @traced("metadata.identity.resolve_source_ticker")
    def resolve_source_ticker(
        self,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str = "stock",
        source: str = "tushare",
    ) -> str:
        """
        将任意标识符解析为 source_ticker.

        优先级: instrument_id > standard_ticker > ticker

        Args:
            ticker: 裸代码（如 "000001"）
            standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
            instrument_id: 内部 ID（如 1000001）
            asset_class: 资产类型（stock | etf | index）
            source: 数据源名称（如 "tushare"）

        Returns:
            source_ticker 字符串

        Raises:
            ValueError: 未提供任何标识符
            AmbiguousTickerError: ticker 不唯一
            IdentifierNotFoundError: 标识符无效

        """
        # 优先级 1: instrument_id
        if instrument_id is not None:
            result = self._instrument_reader.get_source_ticker(
                instrument_id, source, None
            )
            if result is None:
                raise IdentifierNotFoundError(
                    identifier=str(instrument_id),
                    identifier_type="instrument_id",
                )
            return result

        # 优先级 2: standard_ticker
        if standard_ticker is not None:
            return self._resolve_from_standard_ticker(standard_ticker, source)

        # 优先级 3: ticker
        if ticker is not None:
            return self._resolve_from_ticker(ticker, asset_class, source)

        raise ValueError("必须指定 ticker / standard_ticker / instrument_id 之一")

    def _resolve_from_standard_ticker(self, standard_ticker: str, source: str) -> str:
        """
        从 standard_ticker 解析 source_ticker.

        Args:
            standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
            source: 数据源名称

        Returns:
            source_ticker 字符串

        """
        # 使用 transformer 转换 standard_ticker 到 source_ticker
        transformer = self._exchange_transformers.get(source)
        return transformer.from_standard(standard_ticker)

    def _resolve_from_ticker(self, ticker: str, asset_class: str, source: str) -> str:
        """
        从裸 ticker 解析 source_ticker.

        Args:
            ticker: 裸代码
            asset_class: 资产类型
            source: 数据源名称

        Returns:
            source_ticker 字符串

        Raises:
            AmbiguousTickerError: 多个匹配
            IdentifierNotFoundError: 无匹配

        """
        df = self._instrument_reader.find_securities(
            asset_class=asset_class,
            is_active=True,
            source=source,
        )

        if df.is_empty():
            raise IdentifierNotFoundError(
                identifier=ticker,
                identifier_type="ticker",
            )

        # 过滤 ticker 匹配的记录
        matches_df = df.filter(pl.col("ticker") == ticker)

        if matches_df.is_empty():
            raise IdentifierNotFoundError(
                identifier=ticker,
                identifier_type="ticker",
            )

        rows = matches_df.to_dicts()
        if len(rows) > 1:
            matches: list[dict[str, Any]] = [
                {
                    "source_ticker": row.get("source_ticker", ""),
                    "instrument_id": row.get("instrument_id", 0),
                    "name": row.get("name", ""),
                }
                for row in rows
            ]
            raise AmbiguousTickerError(ticker=ticker, matches=matches)

        source_ticker = rows[0].get("source_ticker")
        if source_ticker is None:
            raise IdentifierNotFoundError(
                identifier=ticker,
                identifier_type="ticker",
            )
        return str(source_ticker)

    # ============ list_date 更新 ============

    @traced("metadata.instrument.update_list_date")
    def update_list_date(self, instrument_id: int, list_date: Any) -> None:
        """
        更新证券的上市日期.

        用于从行情数据推断上市日期的场景。

        Args:
            instrument_id: 证券 ID
            list_date: 上市日期

        """
        self._instrument_writer.update_list_date(instrument_id, list_date)

    @traced("metadata.instrument.find_instruments_without_list_date")
    def find_instruments_without_list_date(
        self,
        asset_class: str | None = None,
    ) -> pl.DataFrame:
        """
        查找没有上市日期的证券.

        Args:
            asset_class: 资产类别过滤（可选）

        Returns:
            包含 instrument_id, source_ticker, asset_class 的 DataFrame

        """
        return self._instrument_reader.find_securities(
            asset_class=asset_class,
            is_active=True,
        ).filter(pl.col("list_date").is_null())

    # ============ 证券名称查询 ============

    @traced("metadata.instrument.get_stock_name")
    def get_stock_name(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> str | None:
        """
        获取证券名称（支持 PIT 查询）.

        如果指定 asof 日期，优先从名称变更历史中查找，
        若未找到则 fallback 到 instrument 表中的当前名称。

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 日期 (YYYY-MM-DD)，None 表示当前名称.

        Returns:
            证券名称或 None（未找到时）.

        """
        if asof is not None:
            name = self._name_history_reader.get_name(instrument_id, asof)
            if name is not None:
                return name
        # Fallback: 当前名称
        instrument = self._instrument_reader.get_by_instrument_id(instrument_id)
        return instrument.get("name") if instrument else None

    # ============ 行业多级查询 ============

    @traced("metadata.industry.get_stock_industries_all_levels")
    def get_stock_industries_all_levels(
        self,
        instrument_id: int,
        asof: str | None = None,
        source: str = "sw",
    ) -> list[dict[str, Any]]:
        """
        获取股票所有级别的行业分类.

        JOIN industry_basic 获取 industry_level，按 level 排序。

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 日期，None 表示查询当前.
            source: 行业分类来源（sw=申万, csrc=证监会）.

        Returns:
            行业分类列表（按 industry_level 排序）.

        """
        return self._industry_mapping_reader.get_stock_industries_all_levels(
            instrument_id, asof, source
        )

    # ============ 标的池调仓日程 ============

    @traced("metadata.universe.get_next_rebalance")
    def get_next_rebalance(
        self,
        universe_id: str,
        after_date: str,
    ) -> dict[str, Any] | None:
        """
        获取标的池下一次调仓日程.

        Args:
            universe_id: 标的池 ID.
            after_date: 查询此日期之后的调仓日程.

        Returns:
            调仓日程字典或 None（未找到时）.

        """
        return self._rebalance_reader.get_next_rebalance(universe_id, after_date)

    @traced("metadata.universe.list_rebalances")
    def list_rebalances(self, universe_id: str) -> list[dict[str, Any]]:
        """
        列出标的池所有调仓日程.

        Args:
            universe_id: 标的池 ID.

        Returns:
            调仓日程列表（按 rebalance_date 倒序）.

        """
        return self._rebalance_reader.list_rebalances(universe_id)
