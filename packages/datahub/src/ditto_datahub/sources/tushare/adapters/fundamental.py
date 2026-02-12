"""Fundamental domain Tushare adapter implementation."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.adapters.capital import (
    BALANCE_SHEET_MAPPING,
    CASH_FLOW_MAPPING,
    CORPORATE_ACTIONS_MAPPING,
    DIVIDEND_MAPPING,
    INCOME_STATEMENT_MAPPING,
)
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_datahub.sources.tushare.processors.transformer import TushareDataTransformer


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


class FundamentalTushareAdapter(BaseTushareAdapter):
    """
    Fundamental domain Tushare adapter implementation.

    提供企业基本面数据的 Tushare API 访问，包括：
    - 财务报表：资产负债表、利润表、现金流量表
    - 分红数据：股息分红
    - 公司行为：分红、配股、拆股等
    """

    @traced("source.tushare.fetch_dividend")
    def fetch_dividend(
        self,
        ts_code: str | None = None,
        ex_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股息分红数据."""
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

            result = _add_pit_columns(result)

            row_count = len(result)
            logger.info(
                "Tushare dividend data fetched",
                event="tushare_dividend_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "dividend")

            return result

    @traced("source.tushare.fetch_corporate_actions")
    def fetch_corporate_actions(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取公司行为数据."""
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
        """获取资产负债表数据."""
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

            result = _add_pit_columns(result)

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
        """获取利润表数据."""
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

            result = _add_pit_columns(result)

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
        """获取现金流量表数据."""
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

            result = _add_pit_columns(result)

            row_count = len(result)
            logger.info(
                "Tushare cash flow fetched",
                event="tushare_cash_flow_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "cash_flow")

            return result
