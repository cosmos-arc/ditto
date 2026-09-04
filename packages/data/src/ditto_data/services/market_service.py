"""
MarketService - Market 域统一查询入口（Facade）.

薄委托层：公开方法保留 @traced 装饰器，
核心查询逻辑委托到 market_queries 模块级函数。
"""

from __future__ import annotations

from typing import cast

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_adjustment import apply_etf_adjustment
from ditto_data.services.market_queries import (
    MarketBarsQuery,  # re-export: backward compat
    MarketConstituentsQuery,
    MarketQuery,
    query_bars,
    query_constituents,
)
from ditto_data.services.market_types import (
    AdjType,  # re-export: 消费者 from ditto_data.services.market_service import AdjType
)

__all__ = [
    "AdjType",
    "MarketBarsQuery",
    "MarketConstituentsQuery",
    "MarketQuery",
    "MarketService",
]


class MarketService:
    """
    Market 域统一查询服务（Facade）.

    整合 Market 域所有 Store 的查询功能，提供统一的 K线查询接口。
    核心查询逻辑委托到 market_queries 模块级函数。

    替代: BarsAccessor

    """

    def __init__(
        self,
        read_ports: MarketReaders,
    ) -> None:
        """
        初始化 MarketService.

        Args:
            read_ports: Market 域读取依赖（包含所有 Reader）.

        """
        self._read_ports = read_ports

    @traced("market.find_bars")
    def find_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """K线查询入口."""
        return query_bars(query, self._read_ports)

    @traced("market.list_bars")
    def list_bars(
        self,
        request: MarketBarsQuery | list[int] | None = None,
        **params: object,
    ) -> pl.DataFrame:
        """
        便利方法：批量查询K线数据.

        Args:
            request: Preferred ``MarketBarsQuery`` request object. A positional
                instrument-id list is still accepted for legacy callers.
            params: Legacy keyword parameters used to build ``MarketBarsQuery``.

        Returns:
            K线数据 DataFrame.

        """
        query = _normalize_list_bars_request(request, params)
        return query_bars(query, self._read_ports)

    @traced("market.get_constituents")
    def get_constituents(
        self,
        index_instrument_id: int,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """指数成分股查询入口."""
        return query_constituents(
            MarketConstituentsQuery(index_instrument_id=index_instrument_id, asof=asof),
            self._read_ports,
        )

    @traced("market.get_stock_bars")
    def get_stock_bars(self, start: str, end: str) -> pl.DataFrame:
        """
        查询全市场股票日K线（不复权）.

        提供公开的行情查询接口，供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的原始行情。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            原始行情 DataFrame，包含 instrument_id、trade_date、open、high、
            low、close、pre_close、volume、amount 等列。

        """
        logger.debug(
            "Fetching stock daily bars",
            event="market_stock_bars_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_bars.read(start_date=start, end_date=end)

        logger.debug(
            "Stock daily bars fetched",
            event="market_stock_bars_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "stock_daily", "operation": "get"},
        )

        return df

    @traced("market.get_etf_bars")
    def get_etf_bars(self, start: str, end: str, adj: str = "none") -> pl.DataFrame:
        """
        查询全市场 ETF 日K线，可选复权.

        提供公开的行情查询接口，供 ETF 因子评估等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部 ETF 的行情数据。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).
            adj: 复权类型 ("none", "qfq", "hfq")，默认不复权。

        Returns:
            行情 DataFrame，包含 instrument_id、trade_date、open、high、
            low、close、volume、amount 等列。如果请求复权但无复权因子
            数据，则返回未复权的原始数据。

        """
        logger.debug(
            "Fetching ETF daily bars",
            event="market_etf_bars_get_start",
            start=start,
            end=end,
            adj=adj,
        )

        df = self._read_ports.etf_bars.read(start_date=start, end_date=end)

        # 应用复权（如果需要且 etf_adj 依赖可用）
        adj_type = AdjType.from_string(adj)
        if adj_type != AdjType.NONE and self._read_ports.etf_adj is not None:
            df = apply_etf_adjustment(df, adj_type, start, end, self._read_ports)

        logger.debug(
            "ETF daily bars fetched",
            event="market_etf_bars_get_complete",
            row_count=len(df),
            adj=adj,
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "etf_daily", "operation": "get", "adj": adj},
        )

        return df

    @traced("market.get_global_index_bars")
    def get_global_index_bars(self, start: str, end: str) -> pl.DataFrame:
        """Read global-index observations with their explicit PIT timestamps."""
        reader = self._read_ports.global_index_bars
        if reader is None:
            raise ValueError("global_index_daily reader not configured")
        return reader.read(start_date=start, end_date=end)

    @traced("market.get_adj_factors")
    def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
        """
        查询股票复权因子.

        提供公开的 adj_factor 查询接口，
        供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的复权因子。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            复权因子 DataFrame，包含 instrument_id、trade_date、adj_factor 等列。

        """
        logger.debug(
            "Fetching adjustment factors",
            event="market_adj_factors_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_adj.read(start_date=start, end_date=end)

        logger.debug(
            "Adjustment factors fetched",
            event="market_adj_factors_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "adj_factor", "operation": "get"},
        )

        return df

    @traced("market.get_stock_status")
    def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
        """
        查询股票状态.

        提供公开的 stock_status 查询接口，
        供 RuntimeDerivedInputProvider 等上层组件使用。
        不传入 instrument_ids 参数，返回日期范围内全部证券的状态数据。

        状态包含：is_suspended、suspend_timing、is_st、st_type、list_status。

        Args:
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            股票状态 DataFrame，包含 instrument_id、trade_date、is_suspended 等列。

        """
        logger.debug(
            "Fetching stock status",
            event="market_stock_status_get_start",
            start=start,
            end=end,
        )

        df = self._read_ports.stock_status.read(start_date=start, end_date=end)

        logger.debug(
            "Stock status fetched",
            event="market_stock_status_get_complete",
            row_count=len(df),
        )

        Metrics.data_records.add(
            len(df),
            {"dataset": "stock_status", "operation": "get"},
        )

        return df


def _normalize_list_bars_request(
    request: MarketBarsQuery | list[int] | None,
    params: dict[str, object],
) -> MarketBarsQuery:
    """Normalize query-object and legacy list_bars inputs."""
    if isinstance(request, MarketBarsQuery):
        if params:
            msg = "MarketBarsQuery cannot be combined with list_bars keyword params"
            raise ValueError(msg)
        return request

    if request is not None:
        if "instrument_ids" in params:
            msg = "instrument_ids cannot be supplied both positionally and by keyword"
            raise ValueError(msg)
        params = {**params, "instrument_ids": request}

    return MarketBarsQuery(
        instrument_ids=_instrument_ids_param(params.get("instrument_ids")),
        start=_optional_str_param(params.get("start")),
        end=_optional_str_param(params.get("end")),
        adj=_adj_param(params.get("adj")),
        with_ticker=_bool_param(params.get("with_ticker")),
        with_status=_bool_param(params.get("with_status")),
        asset_class=_optional_str_param(params.get("asset_class")),
        limit=_optional_int_param(params.get("limit")),
    )


def _instrument_ids_param(raw: object) -> list[int] | None:
    """Read legacy instrument ID values."""
    if raw is None:
        return None
    if isinstance(raw, list):
        values = cast(list[object], raw)
        return [_coerce_int_param(value) for value in values]
    if isinstance(raw, tuple):
        values = cast(tuple[object, ...], raw)
        return [_coerce_int_param(value) for value in values]
    return [_coerce_int_param(raw)]


def _optional_str_param(raw: object) -> str | None:
    """Read an optional string parameter."""
    if raw is None:
        return None
    return str(raw)


def _optional_int_param(raw: object) -> int | None:
    """Read an optional integer parameter."""
    if raw is None:
        return None
    return _coerce_int_param(raw)


def _coerce_int_param(raw: object) -> int:
    """Coerce one legacy integer parameter."""
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        return int(raw)
    msg = f"Expected integer-compatible value, got {type(raw).__name__}"
    raise TypeError(msg)


def _bool_param(raw: object) -> bool:
    """Read a legacy bool parameter."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in {"1", "true", "yes", "y"}
    return False


def _adj_param(raw: object) -> AdjType:
    """Read a legacy adjustment parameter."""
    if isinstance(raw, AdjType):
        return raw
    if isinstance(raw, str):
        return AdjType(raw)
    return AdjType.NONE
