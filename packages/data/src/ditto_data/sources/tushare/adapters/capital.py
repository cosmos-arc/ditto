"""Capital domain Tushare adapter -- facade."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.config import DataSourceSettings
from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.adapters.capital_corporate import (
    CapitalCorporateTushareAdapter,
)
from ditto_data.sources.tushare.adapters.capital_index import (
    CapitalIndexTushareAdapter,
)
from ditto_data.sources.tushare.adapters.capital_market import (
    CapitalMarketTushareAdapter,
)
from ditto_data.sources.tushare.client import TushareClient


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

    通过组合三个子适配器实现：
    - CapitalMarketTushareAdapter: 估值/分红/融资融券/质押
    - CapitalIndexTushareAdapter: 指数成分/权重
    - CapitalCorporateTushareAdapter: 公司行为/限售解禁/配股

    """

    def __init__(
        self,
        token: str | None = None,
        settings: DataSourceSettings | None = None,
        *,
        _client: TushareClient | None = None,
    ) -> None:
        super().__init__(token=token, settings=settings, _client=_client)
        self._market = CapitalMarketTushareAdapter(_client=self._client)
        self._index = CapitalIndexTushareAdapter(_client=self._client)
        self._corporate = CapitalCorporateTushareAdapter(_client=self._client)
        logger.debug(
            f"{self.__class__.__name__} sub-adapters initialized",
            event="tushare_capital_facade_init",
        )

    # --- market: valuation / dividend / margin / pledge ---

    def fetch_valuation_metrics(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取估值指标 (PE/PB/PS)."""
        return self._market.fetch_valuation_metrics(
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
        return self._market.fetch_dividend(
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
        return self._market.fetch_margin_trading(
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
        return self._market.fetch_pledge_ratio(
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
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取指数权重数据."""
        if start_date is None and end_date is None:
            return self._index.fetch_index_weight(
                index_code,
                trade_date=trade_date,
            )
        return self._index.fetch_index_weight(
            index_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_index_composition(
        self,
        index_code: str,
        asof_date: str | None = None,
        with_weight: bool = False,
    ) -> pl.DataFrame:
        """获取指数成分股."""
        return self._index.fetch_index_composition(
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
        return self._corporate.fetch_corporate_actions(
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
        return self._corporate.fetch_share_buyback(
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
        return self._corporate.fetch_rights_issue(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
