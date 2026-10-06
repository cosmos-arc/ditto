"""Capital market data: valuation, dividend, margin trading, pledge ratio."""

from __future__ import annotations

from datetime import date

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

# 指数每日估值（index_dailybasic）：市值元、股本股（doc_id=128）。
INDEX_VALUATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source_ticker": pl.String,
    "trade_date": pl.Date,
    "total_mv": pl.Float64,
    "float_mv": pl.Float64,
    "pe": pl.Float64,
    "pe_ttm": pl.Float64,
    "pb": pl.Float64,
    "turnover_rate": pl.Float64,
    "knowledge_date": pl.Date,
}


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
            report_date: 周快照日 (YYYYMMDD，通常为周五；pledge_stat 的
                end_date 参数为精确匹配语义，非快照日请求返回空——
                2026-10-06 代理 t.xiaodefa.top 实测：end_date=周五返回
                当周全市场快照，end_date=下周一返回 0 行)
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
            if report_date:
                # #512：透传快照日过滤。此前 report_date 被静默丢弃，
                # 「按期拉取」退化为全表翻页（且被单次 1000 行上限截断）。
                params["end_date"] = report_date

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

    @traced("source.tushare.fetch_index_valuation")
    def fetch_index_valuation(
        self,
        trade_date: str | None = None,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数每日估值（index_dailybasic，社区计算指标）.

        单位合同与个股 daily_basic 不同：市值单位元、股本单位股，
        不能套用万元/万股换算（doc_id=128）。端点仅覆盖部分大盘指数
        （2026-10-05 实测日覆盖 15 个代码）；空结果如实报告，不填零、
        不承诺所有 ETF 跟踪指数估值。价格指数水平与估值指标分别存储。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD).
            ts_code: 指数代码 (e.g., "000300.SH").
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).

        Returns:
            DataFrame with INDEX_VALUATION_SCHEMA columns.

        """
        logger.info(
            "Fetching Tushare index valuation",
            event="tushare_index_valuation_fetch_start",
            trade_date=trade_date,
            ts_code=ts_code,
        )
        params: dict[str, str] = {
            "api_name": "index_dailybasic",
            "fields": (
                "ts_code,trade_date,total_mv,float_mv,pe,pe_ttm,pb,turnover_rate"
            ),
        }
        if trade_date:
            params["trade_date"] = trade_date.replace("-", "")
        if ts_code:
            params["ts_code"] = ts_code
        if start_date:
            params["start_date"] = start_date.replace("-", "")
        if end_date:
            params["end_date"] = end_date.replace("-", "")

        with tushare_fetch_error_handler("index_valuation", "index_dailybasic"):
            response = self._client.query(**params)

        if response.is_empty():
            return pl.DataFrame(schema=INDEX_VALUATION_SCHEMA)

        result = (
            response.rename({"ts_code": "source_ticker"})
            .with_columns(
                pl.col("trade_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False),
                *(
                    pl.col(column).cast(pl.Float64, strict=False)
                    for column in (
                        "total_mv",
                        "float_mv",
                        "pe",
                        "pe_ttm",
                        "pb",
                        "turnover_rate",
                    )
                ),
                pl.lit(date.today()).alias("knowledge_date"),
            )
            .filter(pl.col("trade_date").is_not_null())
        )

        row_count = len(result)
        logger.info(
            "Tushare index valuation fetched",
            event="tushare_index_valuation_fetch_complete",
            row_count=row_count,
        )
        Metrics.data_records.add(
            row_count,
            {"source": "tushare", "dataset": "index_valuation", "status": "success"},
        )
        return result.select(*INDEX_VALUATION_SCHEMA)
