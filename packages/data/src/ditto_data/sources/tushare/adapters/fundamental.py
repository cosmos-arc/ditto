"""Fundamental domain Tushare adapter implementation."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    BALANCE_SHEET_MAPPING,
    CASH_FLOW_MAPPING,
    CORPORATE_ACTIONS_MAPPING,
    DIVIDEND_MAPPING,
    INCOME_STATEMENT_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


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

        with tushare_fetch_error_handler("dividend", "dividend"):
            # P015: 添加 div_proc 字段区分预案/实施
            params: dict[str, str] = {
                "api_name": "dividend",
                "fields": "ts_code,ex_date,cash_div,record_date,ann_date,div_proc",
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
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "corporate_actions",
                    "status": "success",
                },
            )

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
                    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,"
                    "inventory,fixed_assets,cash_equivalents,accounts_receivable,"
                    "short_term_debt,long_term_debt,money_cap,total_share"
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
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare balance sheet fetched",
                event="tushare_balance_sheet_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "balance_sheet", "status": "success"},
            )

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
                    "ts_code,end_date,ann_date,total_revenue,"
                    "operate_cost,sale_exp,admin_exp,fin_exp,rd_exp,"
                    "operate_profit,total_profit,income_tax,n_income,"
                    "basic_eps,diluted_eps"
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
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare income statement fetched",
                event="tushare_income_statement_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "income_statement",
                    "status": "success",
                },
            )

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
                    "n_cash_flows_inv_act,n_cash_flows_fnc_act,"
                    "depreciation,interest_paid,tax_paid"
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
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare cash flow fetched",
                event="tushare_cash_flow_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "cash_flow", "status": "success"},
            )

            return result

    # ========== VIP API 方法（需要 5000+ 积分）==========
    # VIP API 可以按 period 或 ann_date 批量获取全部股票数据，无需 ts_code

    @traced("source.tushare.fetch_balance_sheet_vip")
    def fetch_balance_sheet_vip(
        self,
        period: str | None = None,
        ann_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        使用 VIP API 批量获取资产负债表数据.

        VIP API (balancesheet_vip) 无需 ts_code，可按 period 或 ann_date
        获取全部股票数据。需要 5000+ 积分。

        Args:
            period: 报告期 (YYYYMMDD，如 "20231231" 表示年报)
            ann_date: 公告日期 (YYYYMMDD)
            start_date: 公告开始日期 (YYYYMMDD)
            end_date: 公告结束日期 (YYYYMMDD)

        Returns:
            全部股票的资产负债表数据

        """
        logger.info(
            "Fetching Tushare balance sheet (VIP)",
            event="tushare_balance_sheet_vip_fetch_start",
            period=period,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("balance_sheet_vip", "balancesheet_vip"):
            params: dict[str, str] = {
                "api_name": "balancesheet_vip",
                "fields": (
                    "ts_code,end_date,ann_date,total_assets,total_liab,"
                    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,"
                    "inventory,fixed_assets,cash_equivalents,accounts_receivable,"
                    "short_term_debt,long_term_debt,money_cap,total_share"
                ),
            }
            if period:
                params["period"] = period
            if ann_date:
                params["ann_date"] = ann_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "balance_sheet", BALANCE_SHEET_MAPPING
            )

            # 添加 PIT 列
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare balance sheet (VIP) fetched",
                event="tushare_balance_sheet_vip_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "balance_sheet_vip",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_income_statement_vip")
    def fetch_income_statement_vip(
        self,
        period: str | None = None,
        ann_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        使用 VIP API 批量获取利润表数据.

        VIP API (income_vip) 无需 ts_code，可按 period 或 ann_date
        获取全部股票数据。需要 5000+ 积分。

        Args:
            period: 报告期 (YYYYMMDD，如 "20231231" 表示年报)
            ann_date: 公告日期 (YYYYMMDD)
            start_date: 公告开始日期 (YYYYMMDD)
            end_date: 公告结束日期 (YYYYMMDD)

        Returns:
            全部股票的利润表数据

        """
        logger.info(
            "Fetching Tushare income statement (VIP)",
            event="tushare_income_statement_vip_fetch_start",
            period=period,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("income_statement_vip", "income_vip"):
            params: dict[str, str] = {
                "api_name": "income_vip",
                "fields": (
                    "ts_code,end_date,ann_date,total_revenue,"
                    "operate_cost,sale_exp,admin_exp,fin_exp,rd_exp,"
                    "operate_profit,total_profit,income_tax,n_income,"
                    "basic_eps,diluted_eps"
                ),
            }
            if period:
                params["period"] = period
            if ann_date:
                params["ann_date"] = ann_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "income_statement", INCOME_STATEMENT_MAPPING
            )

            # 添加 PIT 列
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare income statement (VIP) fetched",
                event="tushare_income_statement_vip_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "income_statement_vip",
                    "status": "success",
                },
            )

            return result

    @traced("source.tushare.fetch_cash_flow_vip")
    def fetch_cash_flow_vip(
        self,
        period: str | None = None,
        ann_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        使用 VIP API 批量获取现金流量表数据.

        VIP API (cashflow_vip) 无需 ts_code，可按 period 或 ann_date
        获取全部股票数据。需要 5000+ 积分。

        Args:
            period: 报告期 (YYYYMMDD，如 "20231231" 表示年报)
            ann_date: 公告日期 (YYYYMMDD)
            start_date: 公告开始日期 (YYYYMMDD)
            end_date: 公告结束日期 (YYYYMMDD)

        Returns:
            全部股票的现金流量表数据

        """
        logger.info(
            "Fetching Tushare cash flow (VIP)",
            event="tushare_cash_flow_vip_fetch_start",
            period=period,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("cash_flow_vip", "cashflow_vip"):
            params: dict[str, str] = {
                "api_name": "cashflow_vip",
                "fields": (
                    "ts_code,end_date,ann_date,n_cashflow_act,"
                    "n_cash_flows_inv_act,n_cash_flows_fnc_act,"
                    "depreciation,interest_paid,tax_paid"
                ),
            }
            if period:
                params["period"] = period
            if ann_date:
                params["ann_date"] = ann_date
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(
                response, "cash_flow", CASH_FLOW_MAPPING
            )

            # 添加 PIT 列
            result = result.with_columns(
                pl.col("knowledge_date").alias("effective_from"),
                pl.lit(None, dtype=pl.Date).alias("effective_to"),
            )

            row_count = len(result)
            logger.info(
                "Tushare cash flow (VIP) fetched",
                event="tushare_cash_flow_vip_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": "cash_flow_vip", "status": "success"},
            )

            return result
