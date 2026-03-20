"""Capital domain Tushare adapter implementation."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.mappings import (
    CORPORATE_ACTIONS_MAPPING,
    DIVIDEND_MAPPING,
    INDEX_COMPOSITION_MAPPING,
    MARGIN_TRADING_MAPPING,
    PLEDGE_RATIO_MAPPING,
    RIGHTS_ISSUE_MAPPING,
    SHARE_BUYBACK_MAPPING,
    VALUATION_METRICS_MAPPING,
)
from ditto_datahub.sources.tushare.processors.transformer import TushareDataTransformer


class CapitalTushareAdapter(BaseTushareAdapter):
    """
    Capital domain Tushare adapter.

    专门处理 Capital 域相关数据获取，包括：
    - 财务报表 (Balance Sheet, Income Statement, Cash Flow)
    - 估值指标 (PE/PB/PS)
    - 股息分红
    - 融资融券
    - 股权质押
    - 期货
    - 指数成分股
    - 公司行为
    - 限售解禁
    - 配股

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
                {"source": "tushare", "dataset": "margin_trading", "status": "success"},
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
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

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

    @traced("source.tushare.fetch_index_weight")
    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数权重数据.

        Args:
            index_code: 指数代码 (e.g., "000001.SH").
            trade_date: 交易日期 (YYYYMMDD), None 表示最新.

        Returns:
            DataFrame with raw Tushare columns (con_code, weight, trade_date, etc.).

        Raises:
            SourceFetchError: If fetch fails.

        """
        params: dict[str, str] = {
            "api_name": "index_weight",
            "index_code": index_code,
            "fields": "con_code,weight",
        }
        if trade_date:
            params["trade_date"] = trade_date

        with tushare_fetch_error_handler("index_weight", "index_weight"):
            df = self._client.query(**params)

        if df.is_empty():
            logger.warning(
                "index_weight_empty",
                index_code=index_code,
                trade_date=trade_date,
            )

        Metrics.data_records.add(
            df.height,
            {
                "source": "tushare",
                "dataset": "index_weight",
                "status": "success",
            },
        )
        return df

    @traced("source.tushare.fetch_index_composition")
    def fetch_index_composition(
        self,
        index_code: str,
        asof_date: str | None = None,
        with_weight: bool = False,
    ) -> pl.DataFrame:
        """
        获取指数成分股.

        Args:
            index_code: 指数代码 (e.g., "000001.SH")
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新
            with_weight: 是否获取权重数据（需要额外 API 调用）

        Returns:
            DataFrame with columns:
            - index_id: 指数代码
            - source_ticker: 股票代码
            - weight: 权重
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare index composition",
            event="tushare_index_composition_fetch_start",
            index_code=index_code,
            asof_date=asof_date,
        )

        with tushare_fetch_error_handler("index_composition", "index_member"):
            params: dict[str, str] = {
                "api_name": "index_member",
                "index_code": index_code,
                "fields": "ts_code,in_date,out_date,is_new",
            }

            if asof_date:
                params["date"] = asof_date.replace("-", "")

            response = self._client.query(**params)

            # 添加 index_code 列和默认权重
            response = response.with_columns(
                pl.lit(index_code).alias("index_code"),
                pl.lit(1.0).alias("weight"),
            )

            result = TushareDataTransformer.transform(
                response, "index_composition", INDEX_COMPOSITION_MAPPING
            )

            # 如果需要真实权重，获取并替换默认值
            if with_weight and not result.is_empty():
                weight_df = self.fetch_index_weight(
                    index_code,
                    asof_date.replace("-", "") if asof_date else None,
                )
                if not weight_df.is_empty():
                    weight_df = weight_df.select("con_code", "weight").rename(
                        {"con_code": "source_ticker"}
                    )
                    result = result.drop("weight").join(
                        weight_df,
                        on="source_ticker",
                        how="left",
                    )

            row_count = len(result)
            logger.info(
                "Tushare index composition fetched",
                event="tushare_index_composition_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "index_composition",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_corporate_actions")
    def fetch_corporate_actions(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取公司行为数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - action_type: 行为类型
            - announcement_date: 公告日期
            - effective_date: 生效日期
            - description: 描述

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare corporate actions",
            event="tushare_corporate_actions_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("corporate_actions", "ba"):
            params: dict[str, str] = {
                "api_name": "ba",
                "fields": "ts_code,ann_date,act_date,ba_type,name",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "corporate_actions", CORPORATE_ACTIONS_MAPPING
            )

            row_count = len(result)
            logger.info(
                "Tushare corporate actions fetched",
                event="tushare_corporate_actions_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "corporate_actions",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_share_buyback")
    def fetch_share_buyback(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取限售解禁数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - announcement_date: 公告日期
            - effective_date: 解禁日期
            - float_shares: 解禁股数
            - float_ratio: 解禁比例

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare share buyback data",
            event="tushare_share_buyback_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("share_buyback", "share_float"):
            params: dict[str, str] = {
                "api_name": "share_float",
                "fields": "ts_code,ann_date,float_date,float_share,float_ratio",
            }

            if ts_code:
                params["ts_code"] = ts_code
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "share_buyback", SHARE_BUYBACK_MAPPING
            )

            row_count = len(result)
            logger.info(
                "Tushare share buyback data fetched",
                event="tushare_share_buyback_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "share_buyback",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_rights_issue")
    def fetch_rights_issue(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取配股数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - rights_type: 配股类型
            - announcement_date: 公告日期
            - record_date: 股权登记日
            - ex_rights_date: 除权日
            - rights_price: 配股价
            - rights_ratio: 配股比例

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare rights issue data",
            event="tushare_rights_issue_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("rights_issue", "rights"):
            params: dict[str, str] = {
                "api_name": "rights",
                "fields": (
                    "ts_code,rights_type,ann_date,reg_date,"
                    "ex_date,rights_price,rights_ratio"
                ),
            }

            if ts_code:
                params["ts_code"] = ts_code
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "rights_issue", RIGHTS_ISSUE_MAPPING
            )

            row_count = len(result)
            logger.info(
                "Tushare rights issue data fetched",
                event="tushare_rights_issue_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "rights_issue",
                    "status": "success",
                },
            )

            return result
