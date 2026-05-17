"""Capital domain Tushare adapter — facade."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.adapters.capital_corporate import (
    fetch_corporate_actions,
    fetch_rights_issue,
    fetch_share_buyback,
)
from ditto_data.sources.tushare.adapters.capital_index import (
    fetch_index_composition,
    fetch_index_weight,
)
from ditto_data.sources.tushare.adapters.capital_market import (
    fetch_dividend,
    fetch_margin_trading,
    fetch_pledge_ratio,
    fetch_valuation_metrics,
)


class CapitalTushareAdapter(BaseTushareAdapter):
    """
    Capital domain Tushare adapter.

    专门处理 Capital 域相关数据获取，包括：
    - 估值指标 (PE/PB/PS)
    - 股息分红
    - 融资融券
    - 股权质押
    - 指数成分股
    - 公司行为
    - 限售解禁
    - 配股

    """

    # --- market: valuation / dividend / margin / pledge ---

    def fetch_valuation_metrics(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取估值指标 (PE/PB/PS)."""
        return fetch_valuation_metrics(
            self._client,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_dividend(
        self,
        ts_code: str | None = None,
        ex_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股息分红数据."""
        return fetch_dividend(
            self._client,
            ts_code=ts_code,
            ex_date=ex_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_margin_trading(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取融资融券数据."""
        return fetch_margin_trading(
            self._client,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_pledge_ratio(
        self,
        ts_code: str | None = None,
        report_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股权质押数据."""
        return fetch_pledge_ratio(
            self._client,
            ts_code=ts_code,
            report_date=report_date,
            start_date=start_date,
            end_date=end_date,
        )

    # --- index: weight & composition ---

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
    ) -> pl.DataFrame:
        """获取指数权重数据."""
        return fetch_index_weight(self._client, index_code, trade_date=trade_date)

    def fetch_index_composition(
        self,
        index_code: str,
        asof_date: str | None = None,
        with_weight: bool = False,
    ) -> pl.DataFrame:
        """获取指数成分股."""
        return fetch_index_composition(
            self._client,
            index_code,
            asof_date=asof_date,
            with_weight=with_weight,
        )

    # --- corporate: actions / buyback / rights issue ---

    def fetch_corporate_actions(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取公司行为数据."""
        return fetch_corporate_actions(
            self._client,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_share_buyback(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取限售解禁数据."""
        return fetch_share_buyback(
            self._client,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_rights_issue(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取配股数据."""
        return fetch_rights_issue(
            self._client,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
