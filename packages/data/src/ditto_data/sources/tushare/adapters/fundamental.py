"""Fundamental domain Tushare adapter implementation."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.adapters.capital_corporate import (
    CapitalCorporateTushareAdapter,
)
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    BALANCE_SHEET_MAPPING,
    CASH_FLOW_MAPPING,
    DIVIDEND_MAPPING,
    INCOME_STATEMENT_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import (
    ColumnMapping,
    TushareDataTransformer,
)

# ── 财务报表字段定义 ──────────────────────────────────────────────
_BALANCE_SHEET_FIELDS = (
    "ts_code,end_date,ann_date,total_assets,total_liab,"
    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,"
    "inventory,fixed_assets,cash_equivalents,accounts_receivable,"
    "short_term_debt,long_term_debt,money_cap,total_share"
)
_INCOME_STATEMENT_FIELDS = (
    "ts_code,end_date,ann_date,total_revenue,"
    "operate_cost,sale_exp,admin_exp,fin_exp,rd_exp,"
    "operate_profit,total_profit,income_tax,n_income,"
    "basic_eps,diluted_eps"
)
_CASH_FLOW_FIELDS = (
    "ts_code,end_date,ann_date,n_cashflow_act,"
    "n_cash_flows_inv_act,n_cash_flows_fnc_act,"
    "depreciation,interest_paid,tax_paid"
)


class FundamentalTushareAdapter(BaseTushareAdapter):
    """
    Fundamental domain Tushare adapter implementation.

    提供企业基本面数据的 Tushare API 访问，包括：
    - 财务报表：资产负债表、利润表、现金流量表
    - 分红数据：股息分红
    - 公司行为：分红、配股、拆股等
    """

    # ── 通用财报获取 ──────────────────────────────────────────────

    def _fetch_financial(
        self,
        *,
        dataset: str,
        api_name: str,
        fields: str,
        mapping: ColumnMapping,
        log_name: str,
        extra_params: dict[str, str | None] | None = None,
        add_pit: bool = True,
    ) -> pl.DataFrame:
        """
        通用财报数据获取方法.

        统一处理参数构建、API 调用、列映射、PIT 列添加、日志和指标记录。
        公开方法（标准 + VIP）通过传入不同的 api_name/params 复用此方法。

        Args:
            dataset: 数据集名称（用于日志、指标、error handler）
            api_name: Tushare API 名称（如 "balancesheet"、"balancesheet_vip"）
            fields: 请求字段列表（逗号分隔字符串）
            mapping: 列名映射字典
            log_name: 日志标识（如 "balance sheet"、"income statement (VIP)"）
            extra_params: 额外查询参数（ts_code/period/ann_date/start_date/end_date）
            add_pit: 是否添加 PIT 列（effective_from/effective_to）

        Returns:
            转换后的 Polars DataFrame

        """
        # 构建日志上下文
        log_ctx = {}
        if extra_params:
            log_ctx = {k: v for k, v in extra_params.items() if v}

        logger.info(
            f"Fetching Tushare {log_name}",
            event=f"tushare_{dataset}_fetch_start",
            **log_ctx,
        )

        with tushare_fetch_error_handler(dataset, api_name):
            params: dict[str, str] = {
                "api_name": api_name,
                "fields": fields,
            }
            if extra_params:
                params.update({k: v for k, v in extra_params.items() if v})

            response = self._client.query(**params)

            result = TushareDataTransformer.transform(response, dataset, mapping)

            # 添加 PIT 列
            if add_pit:
                result = result.with_columns(
                    pl.col("knowledge_date").alias("effective_from"),
                    pl.lit(None, dtype=pl.Date).alias("effective_to"),
                )

            row_count = len(result)
            logger.info(
                f"Tushare {log_name} fetched",
                event=f"tushare_{dataset}_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": dataset, "status": "success"},
            )

            return result

    # ── 非财报方法（结构差异大，不复用 _fetch_financial）─────────

    @traced("source.tushare.fetch_dividend")
    def fetch_dividend(
        self,
        ts_code: str | None = None,
        ann_date: str | None = None,
        ex_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取股息分红数据."""
        logger.info(
            "Fetching Tushare dividend data",
            event="tushare_dividend_fetch_start",
            ts_code=ts_code,
            ann_date=ann_date,
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
            if ann_date:
                params["ann_date"] = ann_date
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
        ann_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取公司行为数据."""
        return CapitalCorporateTushareAdapter(
            _client=self._client
        ).fetch_corporate_actions(
            ts_code=ts_code,
            ann_date=ann_date,
            start_date=start_date,
            end_date=end_date,
        )

    # ── 标准财报方法 ────────────────────────────────────────────

    @traced("source.tushare.fetch_balance_sheet")
    def fetch_balance_sheet(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取资产负债表数据."""
        return self._fetch_financial(
            dataset="balance_sheet",
            api_name="balancesheet",
            fields=_BALANCE_SHEET_FIELDS,
            mapping=BALANCE_SHEET_MAPPING,
            log_name="balance sheet",
            extra_params={
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_income_statement")
    def fetch_income_statement(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取利润表数据."""
        return self._fetch_financial(
            dataset="income_statement",
            api_name="income",
            fields=_INCOME_STATEMENT_FIELDS,
            mapping=INCOME_STATEMENT_MAPPING,
            log_name="income statement",
            extra_params={
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_cash_flow")
    def fetch_cash_flow(
        self,
        ts_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """获取现金流量表数据."""
        return self._fetch_financial(
            dataset="cash_flow",
            api_name="cashflow",
            fields=_CASH_FLOW_FIELDS,
            mapping=CASH_FLOW_MAPPING,
            log_name="cash flow",
            extra_params={
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

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
        return self._fetch_financial(
            dataset="balance_sheet_vip",
            api_name="balancesheet_vip",
            fields=_BALANCE_SHEET_FIELDS,
            mapping=BALANCE_SHEET_MAPPING,
            log_name="balance sheet (VIP)",
            extra_params={
                "period": period,
                "ann_date": ann_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

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
        return self._fetch_financial(
            dataset="income_statement_vip",
            api_name="income_vip",
            fields=_INCOME_STATEMENT_FIELDS,
            mapping=INCOME_STATEMENT_MAPPING,
            log_name="income statement (VIP)",
            extra_params={
                "period": period,
                "ann_date": ann_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

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
        return self._fetch_financial(
            dataset="cash_flow_vip",
            api_name="cashflow_vip",
            fields=_CASH_FLOW_FIELDS,
            mapping=CASH_FLOW_MAPPING,
            log_name="cash flow (VIP)",
            extra_params={
                "period": period,
                "ann_date": ann_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
