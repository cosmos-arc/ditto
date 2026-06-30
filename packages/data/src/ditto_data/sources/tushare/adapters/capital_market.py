"""Capital market data: valuation, dividend, margin trading, pledge ratio."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    DIVIDEND_MAPPING,
    MARGIN_TRADING_MAPPING,
    PLEDGE_RATIO_MAPPING,
    VALUATION_METRICS_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


class CapitalMarketTushareAdapter(BaseTushareAdapter):
    """
    Capital market data Tushare adapter.

    提供资本市场数据的 Tushare API 访问，包括：
    - 估值指标 (PE/PB/PS)
    - 股息分红
    - 融资融券
    - 股权质押

    """

    @traced("source.tushare.fetch_valuation_metrics")
    def fetch_valuation_metrics(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取估值指标 (PE/PB/PS).

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - trade_date: 交易日期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - pe_ratio: 市盈率
            - pb_ratio: 市净率
            - ps_ratio: 市销率
            - dividend_yield: 股息率
            - market_cap: 总市值

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare valuation metrics",
            event="tushare_valuation_metrics_fetch_start",
            ts_code=ts_code,
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("valuation_metrics", "daily_basic"):
            params: dict[str, str] = {
                "api_name": "daily_basic",
                "fields": "ts_code,trade_date,pe,pb,ps,dv_ratio,total_mv",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if trade_date:
                params["trade_date"] = trade_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "valuation_metrics", VALUATION_METRICS_MAPPING
            )

            # 添加 PIT 列（内联 _add_pit_columns）
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare valuation metrics fetched",
                event="tushare_valuation_metrics_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "valuation_metrics",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_dividend")
    def fetch_dividend(
        self,
        ts_code: str | None = None,
        ex_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取股息分红数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            ex_date: 除权除息日 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - ex_dividend_date: 除权除息日
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - dividend_per_share: 每股股利
            - dividend_yield: 股息率

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare dividend data",
            event="tushare_dividend_fetch_start",
            ts_code=ts_code,
            ex_date=ex_date,
        )

        with tushare_fetch_error_handler("dividend", "dividend"):
            params: dict[str, str] = {
                "api_name": "dividend",
                "fields": "ts_code,ex_date,cash_div,record_date,ann_date",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if ex_date:
                params["ex_date"] = ex_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "dividend", DIVIDEND_MAPPING
            )

            # 添加 PIT 列
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare dividend data fetched",
                event="tushare_dividend_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "dividend", "status": "success"},
            )

            return result

    @traced("source.tushare.fetch_margin_trading")
    def fetch_margin_trading(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取融资融券数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - trade_date: 交易日期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - margin_buy_balance: 融资余额
            - short_sell_balance: 融券余额
            - margin_buy_volume: 融资买入量
            - short_sell_volume: 融券卖出量

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare margin trading data",
            event="tushare_margin_trading_fetch_start",
            ts_code=ts_code,
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("margin_trading", "margin_detail"):
            params: dict[str, str] = {
                "api_name": "margin_detail",
                "fields": "ts_code,trade_date,rzye,rqye,rzmre,rqmcl",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if trade_date:
                params["trade_date"] = trade_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "margin_trading", MARGIN_TRADING_MAPPING
            )

            # 添加 PIT 列
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare margin trading data fetched",
                event="tushare_margin_trading_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "margin_trading",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_pledge_ratio")
    def fetch_pledge_ratio(
        self,
        ts_code: str | None = None,
        report_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取股权质押数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            report_date: 报告期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD) — 未使用，保留接口兼容
            end_date: 结束日期 (YYYYMMDD) — 未使用，保留接口兼容

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - report_date: 报告期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - pledge_ratio: 质押比例
            - pledge_shares: 质押股数
            - total_shares: 总股本

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare pledge ratio data",
            event="tushare_pledge_ratio_fetch_start",
            ts_code=ts_code,
            report_date=report_date,
        )

        with tushare_fetch_error_handler("pledge_ratio", "pledge_stat"):
            params: dict[str, str] = {
                "api_name": "pledge_stat",
                "fields": "ts_code,end_date,pledge_ratio,total_share",
            }

            if ts_code:
                params["ts_code"] = ts_code

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "pledge_ratio", PLEDGE_RATIO_MAPPING
            )

            # 添加 PIT 列（使用 report_date 作为 effective_from）
            result = result.with_columns(
                pl.col("report_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            # 重新排列列顺序以符合 SourceSchema
            result = result.select(
                "source_ticker",
                "report_date",
                "knowledge_date",
                "effective_from",
                "effective_to",
                "pledge_ratio",
                "total_shares",
            )

            row_count = len(result)
            logger.info(
                "Tushare pledge ratio data fetched",
                event="tushare_pledge_ratio_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "pledge_ratio", "status": "success"},
            )

            return result
