"""Capital domain Tushare adapter implementation."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.sources.schemas.capital_schemas import (
    BALANCE_SHEET_SOURCE_SCHEMA,
    CASH_FLOW_SOURCE_SCHEMA,
    CORPORATE_ACTIONS_SOURCE_SCHEMA,
    DIVIDEND_SOURCE_SCHEMA,
    FUTURES_SOURCE_SCHEMA,
    INCOME_STATEMENT_SOURCE_SCHEMA,
    INDEX_COMPOSITION_SOURCE_SCHEMA,
    MARGIN_TRADING_SOURCE_SCHEMA,
    PLEDGE_RATIO_SOURCE_SCHEMA,
    VALUATION_METRICS_SOURCE_SCHEMA,
)
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.transformer import (
    ColumnMapping,
    TushareDataTransformer,
)

# ============================================================================
# Column Mappings
# ============================================================================

# Valuation Metrics (PE/PB) - PIT data
VALUATION_METRICS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "pe": "pe_ratio",
        "pb": "pb_ratio",
        "ps": "ps_ratio",
        "total_mv": "market_cap",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "pe_ratio",
        "pb_ratio",
        "ps_ratio",
        "dividend_yield",
        "market_cap",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Dividend - PIT data
DIVIDEND_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "ex_date": "ex_dividend_date",
        "dividend": "dividend_per_share",
    },
    date_columns={"ex_dividend_date": "%Y%m%d"},
    float_columns=["dividend_per_share", "dividend_yield"],
    computed_columns={
        "knowledge_date": pl.col("ex_dividend_date") + pl.duration(days=1)
    },
    output_columns=(
        "instrument_id",
        "ex_dividend_date",
        "knowledge_date",
        "dividend_per_share",
        "dividend_yield",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Margin Trading - PIT data
MARGIN_TRADING_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "rz_balance": "margin_buy_balance",
        "rz_vol": "margin_buy_volume",
        "rq_balance": "short_sell_balance",
        "rq_vol": "short_sell_volume",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Pledge Ratio - PIT data
# Note: Tushare pledge API does not return report_date, we'll add it in the method
PLEDGE_RATIO_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "pledge_count": "pledge_shares",
        "total_share": "total_shares",
    },
    date_columns={},
    float_columns=["pledge_ratio", "pledge_shares", "total_shares"],
    computed_columns={},
    output_columns=(
        "instrument_id",
        "pledge_ratio",
        "pledge_shares",
        "total_shares",
    ),
    # Will add report_date, knowledge_date, effective_from/effective_to in method
    source_schema=None,
)

# Futures - PIT data
FUTURES_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "oi": "open_interest",
        "settlement": "settlement_price",
        "vol": "volume",
        "amount": "turnover",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["open_interest", "settlement_price", "volume", "turnover"],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "open_interest",
        "settlement_price",
        "volume",
        "turnover",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Index Composition - PIT data
INDEX_COMPOSITION_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id", "index_code": "index_id"},
    date_columns={"in_date": "%Y%m%d"},
    float_columns=["weight"],
    int_columns=("is_new",),
    computed_columns={"effective_from": pl.col("in_date")},
    output_columns=(
        "index_id",
        "instrument_id",
        "weight",
        "effective_from",
    ),
    source_schema=None,  # Will add effective_to in method
)

# Corporate Actions - Non-PIT data
CORPORATE_ACTIONS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "ba_type": "action_type",
        "ann_date": "announcement_date",
        "act_date": "effective_date",
        "name": "description",
    },
    date_columns={"announcement_date": "%Y%m%d", "effective_date": "%Y%m%d"},
    float_columns=[],
    output_columns=(
        "instrument_id",
        "action_type",
        "announcement_date",
        "effective_date",
        "description",
    ),
    source_schema=CORPORATE_ACTIONS_SOURCE_SCHEMA,
)

# Balance Sheet - PIT data (simplified fields)
BALANCE_SHEET_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "total_liab": "total_liabilities",
    },
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_assets",
        "total_liabilities",  # After rename
        "total_hldr_eqy_exc_min_int",
        "total_cur_assets",
        "total_cur_liab",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "net_assets": pl.col("total_hldr_eqy_exc_min_int"),
        "current_assets": pl.col("total_cur_assets"),
        "current_liabilities": pl.col("total_cur_liab"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "total_assets",
        "total_liabilities",
        "net_assets",
        "current_assets",
        "current_liabilities",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Income Statement - PIT data (simplified fields)
INCOME_STATEMENT_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_operating_revenue",
        "operating_profit",
        "net_profit",
        "basic_eps",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "revenue": pl.col("total_operating_revenue"),
        "eps": pl.col("basic_eps"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "revenue",
        "operating_profit",
        "net_profit",
        "eps",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)

# Cash Flow - PIT data (simplified fields)
CASH_FLOW_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "n_cashflow_act",
        "n_cash_flows_inv_act",
        "n_cash_flows_fnc_act",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "operating_cash_flow": pl.col("n_cashflow_act"),
        "investing_cash_flow": pl.col("n_cash_flows_inv_act"),
        "financing_cash_flow": pl.col("n_cash_flows_fnc_act"),
        "net_cash_flow": pl.col("n_cashflow_act")
        + pl.col("n_cash_flows_inv_act")
        + pl.col("n_cash_flows_fnc_act"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
    ),
    source_schema=None,  # Will add effective_from/effective_to in method
)


def _record_metrics(row_count: int, dataset: str) -> None:
    """
    安全地记录数据指标.

    如果 observability 未初始化，静默跳过.

    Args:
        row_count: 数据行数
        dataset: 数据集名称

    """
    try:
        M.data_records.add(
            row_count,
            {"source": "tushare", "dataset": dataset, "status": "success"},
        )
    except (AttributeError, TypeError):
        # Observability 未初始化，静默跳过
        pass


def _add_pit_columns(
    df: pl.DataFrame,
    date_col: str = "knowledge_date",
) -> pl.DataFrame:
    """
    为 PIT 数据添加 effective_from 和 effective_to 列.

    Args:
        df: 输入 DataFrame
        date_col: 用作 effective_from 的日期列名

    Returns:
        添加了 PIT 列的 DataFrame

    """
    return df.with_columns(
        pl.col(date_col).alias("effective_from"),
        pl.lit(None, dtype=pl.Date).alias("effective_to"),
    )


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
            - instrument_id: 股票代码
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

        with tushare_fetch_error_handler("valuation_metrics", "pe_daily"):
            # Tushare API: pe_daily 获取每日市盈率
            # 类似地可以使用 pb_daily 获取市净率
            # 这里先实现 pe_daily，后续可以合并 pb_daily 的数据

            params: dict[str, str] = {
                "api_name": "pe_daily",
                "fields": "ts_code,trade_date,pe,pb,ps,dividend_yield,total_mv",
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

            # 添加 PIT 列
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            VALUATION_METRICS_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare valuation metrics fetched",
                event="tushare_valuation_metrics_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "valuation_metrics")

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
            - instrument_id: 股票代码
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

        with tushare_fetch_error_handler("dividend", "div_oper"):
            params: dict[str, str] = {
                "api_name": "div_oper",
                "fields": "ts_code,ex_date,dividend,dividend_yield",
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
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            DIVIDEND_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare dividend data fetched",
                event="tushare_dividend_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "dividend")

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
            - instrument_id: 股票代码
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

        with tushare_fetch_error_handler("margin_trading", "margin"):
            params: dict[str, str] = {
                "api_name": "margin",
                "fields": "ts_code,trade_date,rz_balance,rz_vol,rq_balance,rq_vol",
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
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            MARGIN_TRADING_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare margin trading data fetched",
                event="tushare_margin_trading_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "margin_trading")

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
            - instrument_id: 股票代码
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

        with tushare_fetch_error_handler("pledge_ratio", "pledge"):
            params: dict[str, str] = {
                "api_name": "pledge",
                "fields": "ts_code,pledge_ratio,pledge_count,total_share",
            }

            if ts_code:
                params["ts_code"] = ts_code

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "pledge_ratio", PLEDGE_RATIO_MAPPING
            )

            # 添加 report_date 和 knowledge_date（使用当前日期）
            # TODO: 在实际使用中，应该从其他数据源获取正确的 report_date
            today = date.today()
            result = result.with_columns(
                pl.lit(today).alias("report_date"),
                pl.lit(today).alias("knowledge_date"),
            )

            # 添加 PIT 列
            result = _add_pit_columns(result, date_col="report_date")

            # 重新排列列顺序以符合 SourceSchema
            result = result.select(
                "instrument_id",
                "report_date",
                "knowledge_date",
                "effective_from",
                "effective_to",
                "pledge_ratio",
                "pledge_shares",
                "total_shares",
            )

            # 验证 SourceSchema
            PLEDGE_RATIO_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare pledge ratio data fetched",
                event="tushare_pledge_ratio_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "pledge_ratio")

            return result

    @traced("source.tushare.fetch_futures")
    def fetch_futures(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取期货数据.

        Args:
            ts_code: 期货代码 (e.g., "IF2401")
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - instrument_id: 期货代码
            - trade_date: 交易日期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - open_interest: 持仓量
            - settlement_price: 结算价
            - volume: 成交量
            - turnover: 成交额

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare futures data",
            event="tushare_futures_fetch_start",
            ts_code=ts_code,
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("futures", "fut"):
            params: dict[str, str] = {
                "api_name": "fut",
                "fields": "ts_code,trade_date,oi,settlement,vol,amount",
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
                response, "futures", FUTURES_MAPPING
            )

            # 添加 PIT 列
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            FUTURES_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare futures data fetched",
                event="tushare_futures_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "futures")

            return result

    @traced("source.tushare.fetch_index_composition")
    def fetch_index_composition(
        self,
        index_code: str,
        asof_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数成分股.

        Args:
            index_code: 指数代码 (e.g., "000001.SH")
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新

        Returns:
            DataFrame with columns:
            - index_id: 指数代码
            - instrument_id: 股票代码
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
                "fields": "ts_code,in_date,is_new",
            }

            if asof_date:
                # 历史查询：指定查询日期
                params["date"] = asof_date.replace("-", "")

            response = self._client.query(**params)

            # 添加 index_code 列（后续会被重命名为 index_id）
            response = response.with_columns(pl.lit(index_code).alias("index_code"))

            # 添加默认权重（Tushare 不提供权重信息，设为 1.0）
            response = response.with_columns(pl.lit(1.0).alias("weight"))

            result = TushareDataTransformer.transform(
                response, "index_composition", INDEX_COMPOSITION_MAPPING
            )

            # 添加 effective_to 列
            result = result.with_columns(
                pl.lit(None, dtype=pl.Date).alias("effective_to")
            )

            # 验证 SourceSchema
            INDEX_COMPOSITION_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare index composition fetched",
                event="tushare_index_composition_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "index_composition")

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
            - instrument_id: 股票代码
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
            _record_metrics(row_count, "corporate_actions")

            return result

    @traced("source.tushare.fetch_balance_sheet")
    def fetch_balance_sheet(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取资产负债表数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - instrument_id: 股票代码
            - report_date: 报告期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - total_assets: 总资产
            - total_liabilities: 总负债
            - net_assets: 净资产
            - current_assets: 流动资产
            - current_liabilities: 流动负债

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare balance sheet",
            event="tushare_balance_sheet_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("balance_sheet", "balancesheet"):
            params: dict[str, str] = {
                "api_name": "balancesheet",
                "fields": (
                    "ts_code,end_date,ann_date,total_assets,total_liab,"
                    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab"
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
                response, "balance_sheet", BALANCE_SHEET_MAPPING
            )

            # 添加 PIT 列
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            BALANCE_SHEET_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare balance sheet fetched",
                event="tushare_balance_sheet_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "balance_sheet")

            return result

    @traced("source.tushare.fetch_income_statement")
    def fetch_income_statement(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取利润表数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - instrument_id: 股票代码
            - report_date: 报告期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - revenue: 营业收入
            - operating_profit: 营业利润
            - net_profit: 净利润
            - eps: 每股收益

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare income statement",
            event="tushare_income_statement_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("income_statement", "income"):
            params: dict[str, str] = {
                "api_name": "income",
                "fields": (
                    "ts_code,end_date,ann_date,total_operating_revenue,"
                    "operating_profit,net_profit,basic_eps"
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
                response, "income_statement", INCOME_STATEMENT_MAPPING
            )

            # 添加 PIT 列
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            INCOME_STATEMENT_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare income statement fetched",
                event="tushare_income_statement_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "income_statement")

            return result

    @traced("source.tushare.fetch_cash_flow")
    def fetch_cash_flow(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取现金流量表数据.

        Args:
            ts_code: 股票代码 (e.g., "000001.SZ")
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            DataFrame with columns:
            - instrument_id: 股票代码
            - report_date: 报告期
            - knowledge_date: 知识日期
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期
            - operating_cash_flow: 经营活动现金流
            - investing_cash_flow: 投资活动现金流
            - financing_cash_flow: 筹资活动现金流
            - net_cash_flow: 现金净增加额

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare cash flow",
            event="tushare_cash_flow_fetch_start",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("cash_flow", "cashflow"):
            params: dict[str, str] = {
                "api_name": "cashflow",
                "fields": (
                    "ts_code,end_date,ann_date,n_cashflow_act,"
                    "n_cash_flows_inv_act,n_cash_flows_fnc_act"
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
                response, "cash_flow", CASH_FLOW_MAPPING
            )

            # 添加 PIT 列
            result = _add_pit_columns(result)

            # 验证 SourceSchema
            CASH_FLOW_SOURCE_SCHEMA.validate(result)

            row_count = len(result)
            logger.info(
                "Tushare cash flow fetched",
                event="tushare_cash_flow_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "cash_flow")

            return result
