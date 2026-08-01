"""Tushare data source -- facade 委托入口."""

from __future__ import annotations

from datetime import date, timedelta
from time import sleep

import polars as pl

from ditto_data.config import DataSourceSettings
from ditto_data.errors import SourceFetchError
from ditto_data.sources.tushare._market_facades import (
    EtfIndexFacade as _EtfIndexFacade,
)
from ditto_data.sources.tushare._market_facades import StockFacade as _StockFacade
from ditto_data.sources.tushare.adapters.calendar import CalendarTushareAdapter
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_data.sources.tushare.adapters.fx import FxTushareAdapter
from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter
from ditto_data.sources.tushare.adapters.industry import IndustryTushareAdapter
from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_data.sources.tushare.adapters.metal import MetalTushareAdapter
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.etf_index_source import (
    fetch_etf_basic,
    fetch_etf_daily,
    fetch_fund_adj,
    fetch_index_basic,
    fetch_index_daily,
    fetch_sw_industry,
)
from ditto_data.sources.tushare.fundamental_source import (
    fetch_balance_sheet,
    fetch_cash_flow,
    fetch_corporate_actions,
    fetch_dividend,
    fetch_income_statement,
    fetch_margin_trading,
    fetch_pledge_ratio,
    fetch_valuation_metrics,
)
from ditto_data.sources.tushare.macro_source import (
    fetch_commodities,
    fetch_fx_daily,
    fetch_macro_indicators,
    fetch_macro_indicators_range,
    fetch_metal_daily,
)
from ditto_data.sources.tushare.stock_source import (
    fetch_adj_factor,
    fetch_adj_factor_by_ticker,
    fetch_calendar,
    fetch_st_history,
    fetch_stock_basic,
    fetch_stock_daily,
    fetch_stock_limit,
    fetch_stock_status,
)

_DIVIDEND_ANNOUNCEMENT_ATTEMPTS = 3
_DIVIDEND_ANNOUNCEMENT_RETRY_DELAY_SECONDS = 61.0


def _fetch_dividend_announcement_date(
    adapter: FundamentalTushareAdapter,
    announcement_date: str,
) -> pl.DataFrame:
    """Retry one exact announcement date after the client's bounded retries."""
    for attempt in range(1, _DIVIDEND_ANNOUNCEMENT_ATTEMPTS + 1):
        try:
            return adapter.fetch_dividend(ann_date=announcement_date)
        except SourceFetchError:
            if attempt == _DIVIDEND_ANNOUNCEMENT_ATTEMPTS:
                raise
            # Tushare reports business-level quota errors in a successful HTTP
            # response.  The client's short transport retry therefore remains
            # inside the same provider minute window; cross that boundary before
            # retrying the exact natural-date request.
            sleep(_DIVIDEND_ANNOUNCEMENT_RETRY_DELAY_SECONDS)
    raise AssertionError("unreachable dividend retry state")


def _fetch_dividend_announcement_range(
    adapter: FundamentalTushareAdapter,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """Fetch a bounded dividend interval through documented exact ann_date calls."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("dividend range end_date precedes start_date")
    frames: list[pl.DataFrame] = []
    current = start
    while current <= end:
        frames.append(
            _fetch_dividend_announcement_date(
                adapter,
                current.strftime("%Y%m%d"),
            )
        )
        current += timedelta(days=1)
    non_empty = [frame for frame in frames if not frame.is_empty()]
    if non_empty:
        # The provider can repeat an identical plan/implementation row.  Collapse
        # only byte-equivalent business rows; distinct amounts or states remain
        # visible to the append-only downstream contract.
        return pl.concat(non_empty, how="diagonal_relaxed").unique(maintain_order=True)
    return frames[0]


# ── 内部 Facade 类 ───────────────────────────────────────────────────


class _FundamentalFacade:
    """基本面/资金数据域 facade."""

    def __init__(
        self,
        fundamental: FundamentalTushareAdapter,
        capital: CapitalTushareAdapter,
    ) -> None:
        self._fundamental = fundamental
        self._capital = capital

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取资产负债表."""
        return fetch_balance_sheet(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取利润表."""
        return fetch_income_statement(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取现金流量表."""
        return fetch_cash_flow(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取分红数据."""
        return fetch_dividend(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取估值指标."""
        return fetch_valuation_metrics(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取融资融券数据."""
        return fetch_margin_trading(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股权质押数据."""
        return fetch_pledge_ratio(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取 effective-dated 指数成分权重."""
        if start_date is None and end_date is None:
            return self._capital.fetch_index_weight(
                index_code,
                trade_date=trade_date,
            )
        return self._capital.fetch_index_weight(
            index_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """获取公司行为数据."""
        return fetch_corporate_actions(self._fundamental, trade_date)

    def fetch_balance_sheet_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch all balance-sheet announcements in one bounded interval."""
        return self._fundamental.fetch_balance_sheet_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_income_statement_range(
        self, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """Fetch all income-statement announcements in one bounded interval."""
        return self._fundamental.fetch_income_statement_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_cash_flow_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch all cash-flow announcements in one bounded interval."""
        return self._fundamental.fetch_cash_flow_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_dividend_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch dividend announcements in one bounded natural-day interval."""
        return _fetch_dividend_announcement_range(
            self._fundamental,
            start_date,
            end_date,
        )

    def fetch_corporate_actions_range(
        self, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """Fetch corporate-action events in one bounded interval."""
        return self._fundamental.fetch_corporate_actions(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )


class _MacroFacade:
    """宏观/外汇/商品数据域 facade."""

    def __init__(
        self,
        macro: MacroTushareAdapter,
        fx: FxTushareAdapter,
        metal: MetalTushareAdapter,
    ) -> None:
        self._macro = macro
        self._fx = fx
        self._metal = metal

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """获取宏观指标数据."""
        return fetch_macro_indicators(self._macro, trade_date)

    def fetch_macro_indicators_range(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取宏观指标区间数据."""
        return fetch_macro_indicators_range(self._macro, start_date, end_date)

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取外汇日线数据."""
        return fetch_fx_daily(
            self._fx,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """获取贵金属日线数据."""
        return fetch_metal_daily(
            self._metal,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Tushare 不支持商品数据."""
        return fetch_commodities(codes, start_date, end_date)


# ── 主入口 ───────────────────────────────────────────────────────────


class TushareSource:
    """Tushare Pro data source (组合模式入口)."""

    def __init__(
        self,
        settings: DataSourceSettings,
        token: str | None = None,
    ) -> None:
        """
        Initialize Tushare source.

        Args:
            settings: 数据源配置（包含 URL/timeout 等参数）.
            token: API token（可选，优先于 settings 中的 token）。

        """
        # 创建单例 client，所有 adapter 共享
        self._client = TushareClient(token=token, settings=settings)

        # 注入共享 client 到所有 adapter
        self._calendar = CalendarTushareAdapter(_client=self._client)
        self._stock = StockTushareAdapter(_client=self._client)
        self._etf = ETFTushareAdapter(_client=self._client)
        self._index = IndexTushareAdapter(_client=self._client)
        self._industry = IndustryTushareAdapter(_client=self._client)
        self._capital = CapitalTushareAdapter(_client=self._client)
        self._fundamental = FundamentalTushareAdapter(_client=self._client)
        self._macro = MacroTushareAdapter(_client=self._client)
        self._fx = FxTushareAdapter(_client=self._client)
        self._metal = MetalTushareAdapter(_client=self._client)

        # 初始化 facade
        self._stock_facade = _StockFacade(self._calendar, self._stock)
        self._etf_index_facade = _EtfIndexFacade(self._etf, self._index, self._industry)
        self._fundamental_facade = _FundamentalFacade(self._fundamental, self._capital)
        self._macro_facade = _MacroFacade(self._macro, self._fx, self._metal)

    # ── 域分组 property facade ─────────────────────────────────────

    @property
    def stock(self) -> _StockFacade:
        """股票/日历数据域."""
        return self._stock_facade

    @property
    def etf_index(self) -> _EtfIndexFacade:
        """ETF/指数/行业数据域."""
        return self._etf_index_facade

    @property
    def fundamental(self) -> _FundamentalFacade:
        """基本面/资金数据域."""
        return self._fundamental_facade

    @property
    def macro(self) -> _MacroFacade:
        """宏观/外汇/商品数据域."""
        return self._macro_facade

    # ── Calendar + Stock（向后兼容委托）─────────────────────────────

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch trading calendar. 委托给 stock_source.fetch_calendar."""
        return fetch_calendar(self._calendar, start_date, end_date)

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """Fetch stock basic information. 委托给 stock_source.fetch_stock_basic."""
        return fetch_stock_basic(self._stock, source_ticker)

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch stock daily OHLCV bars. 委托给 stock_source.fetch_stock_daily."""
        return fetch_stock_daily(
            self._stock,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock adjustment factors. 委托给 stock_source.fetch_adj_factor."""
        return fetch_adj_factor(self._stock, trade_date)

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch stock adj factors by ticker. 委托给 stock_source."""
        return fetch_adj_factor_by_ticker(self._stock, ts_code, start_date, end_date)

    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock limit up/down prices. 委托给 stock_source.fetch_stock_limit."""
        return fetch_stock_limit(self._stock, trade_date)

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock status information. 委托给 stock_source.fetch_stock_status."""
        return fetch_stock_status(self._stock, trade_date)

    def fetch_st_history(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch ST status change history. 委托给 stock_source.fetch_st_history."""
        return fetch_st_history(
            self._stock,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    # ── ETF + Index + Industry（向后兼容委托）────────────────────────

    def fetch_etf_basic(self) -> pl.DataFrame:
        """Fetch ETF basic information. 委托给 etf_index_source.fetch_etf_basic."""
        return fetch_etf_basic(self._etf)

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch ETF daily OHLCV bars. 委托给 etf_index_source.fetch_etf_daily."""
        return fetch_etf_daily(
            self._etf,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch ETF/fund adjustment factors. 委托给 etf_index_source.fetch_fund_adj."""
        return fetch_fund_adj(
            self._etf,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_basic(self) -> pl.DataFrame:
        """Fetch index basic information. 委托给 etf_index_source.fetch_index_basic."""
        return fetch_index_basic(self._index)

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch index daily OHLCV bars. 委托给 etf_index_source.fetch_index_daily."""
        return fetch_index_daily(
            self._index,
            trade_date=trade_date,
            ts_codes=ts_codes,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类. 委托给 etf_index_source.fetch_sw_industry."""
        return fetch_sw_industry(self._industry, level)

    # ── Fundamental + Capital（向后兼容委托）─────────────────────────

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch balance sheet data. 委托给 fundamental_source.fetch_balance_sheet."""
        return fetch_balance_sheet(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch income statement data. 委托给 fundamental_source."""
        return fetch_income_statement(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch cash flow data. 委托给 fundamental_source.fetch_cash_flow."""
        return fetch_cash_flow(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch dividend data. 委托给 fundamental_source.fetch_dividend."""
        return fetch_dividend(
            self._fundamental,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch valuation metrics data. 委托给 fundamental_source."""
        return fetch_valuation_metrics(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch margin trading data. 委托给 fundamental_source.fetch_margin_trading."""
        return fetch_margin_trading(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch pledge ratio data. 委托给 fundamental_source.fetch_pledge_ratio."""
        return fetch_pledge_ratio(
            self._capital,
            trade_date=trade_date,
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch effective-dated index weights from the capital adapter."""
        if start_date is None and end_date is None:
            return self._capital.fetch_index_weight(
                index_code,
                trade_date=trade_date,
            )
        return self._capital.fetch_index_weight(
            index_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """Fetch corporate actions data. 委托给 fundamental_source."""
        return fetch_corporate_actions(self._fundamental, trade_date)

    def fetch_balance_sheet_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch all balance-sheet announcements in a bounded interval."""
        return self._fundamental.fetch_balance_sheet_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_income_statement_range(
        self, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """Fetch all income-statement announcements in a bounded interval."""
        return self._fundamental.fetch_income_statement_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_cash_flow_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch all cash-flow announcements in a bounded interval."""
        return self._fundamental.fetch_cash_flow_vip(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    def fetch_dividend_range(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch dividend announcements in a bounded natural-day interval."""
        return _fetch_dividend_announcement_range(
            self._fundamental,
            start_date,
            end_date,
        )

    def fetch_corporate_actions_range(
        self, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """Fetch corporate-action events in a bounded interval."""
        return self._fundamental.fetch_corporate_actions(
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )

    # ── Macro + FX + Metal + Commodity（向后兼容委托）────────────────

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """Fetch macro indicators data. 委托给 macro_source.fetch_macro_indicators."""
        return fetch_macro_indicators(self._macro, trade_date)

    def fetch_macro_indicators_range(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch macro indicator observations over a bounded interval."""
        return fetch_macro_indicators_range(self._macro, start_date, end_date)

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch FX daily data. 委托给 macro_source.fetch_fx_daily."""
        return fetch_fx_daily(
            self._fx,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch precious metals daily data. 委托给 macro_source.fetch_metal_daily."""
        return fetch_metal_daily(
            self._metal,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Tushare 不支持商品数据."""
        return fetch_commodities(codes, start_date, end_date)

    def close(self) -> None:
        """
        释放 HTTP 连接资源.

        调用内部 TushareClient 的 close 方法释放网络资源。
        """
        if hasattr(self, "_client") and self._client:
            self._client.close()
