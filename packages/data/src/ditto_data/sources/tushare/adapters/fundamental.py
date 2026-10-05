"""Fundamental domain Tushare adapter implementation."""

from __future__ import annotations

from datetime import date

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
# 披露锚 = f_ann_date（实际公告日，ADR 红线 4）；ann_date 可被 Tushare
# 事后加工改写，不作为 PIT knowledge date。
# report_type/update_flag 为 #482 行身份列（过滤/去重在 _fetch_financial，
# 不进输出帧）
_BALANCE_SHEET_FIELDS = (
    "ts_code,end_date,f_ann_date,report_type,update_flag,total_assets,total_liab,"
    "total_hldr_eqy_exc_min_int,total_cur_assets,total_cur_liab,"
    "inventory,fixed_assets,cash_equivalents,accounts_receivable,"
    "short_term_debt,long_term_debt,money_cap,total_share"
)
# revenue=营业收入（与 fuyao operating_income 同科目，跨源对账可比字段）；
# total_revenue=营业总收入（含利息收入等金融科目）沿旧义存 revenue 列。
_INCOME_STATEMENT_FIELDS = (
    "ts_code,end_date,f_ann_date,report_type,update_flag,total_revenue,revenue,"
    "operate_cost,sale_exp,admin_exp,fin_exp,rd_exp,"
    "operate_profit,total_profit,income_tax,n_income,"
    "basic_eps,diluted_eps"
)
# 官方字段名为 n_cashflow_inv_act/n_cashflow_fnc_act（doc_id=44）；
# 旧的 n_cash_flows_* 拼写取不回值。depreciation/interest_paid/tax_paid
# 在官方端点已无同名字段且无消费者，不再请求。
_CASH_FLOW_FIELDS = (
    "ts_code,end_date,f_ann_date,report_type,update_flag,"
    "n_cashflow_act,n_cashflow_inv_act,n_cashflow_fnc_act"
)

# 业绩预告（doc_id=45）：上下界型预告，净利润上下限单位万元。
# 同日同标的同类型可同时存在 update_flag 0/1 两行（2026-10-05 实测
# 000017.SZ 2026-01-30 预增两行），修订身份必须进主键，不能去重。
_FORECAST_FIELDS = (
    "ts_code,ann_date,end_date,type,p_change_min,p_change_max,"
    "net_profit_min,net_profit_max,first_ann_date,update_flag"
)

# 业绩快报（doc_id=46）：金额字段单位为元。与 forecast（万元）不可共
# 用一条换算规则，两侧均按原始值存储。
_EXPRESS_FIELDS = (
    "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,"
    "n_income,total_assets,audit_status"
)

EARNINGS_FORECAST_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source_ticker": pl.String,
    "ann_date": pl.Date,
    "report_date": pl.Date,
    "forecast_type": pl.String,
    "p_change_min": pl.Float64,
    "p_change_max": pl.Float64,
    "net_profit_min": pl.Float64,
    "net_profit_max": pl.Float64,
    "first_ann_date": pl.Date,
    "update_flag": pl.String,
    "knowledge_date": pl.Date,
}

EARNINGS_EXPRESS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source_ticker": pl.String,
    "ann_date": pl.Date,
    "report_date": pl.Date,
    "revenue": pl.Float64,
    "operate_profit": pl.Float64,
    "total_profit": pl.Float64,
    "n_income": pl.Float64,
    "total_assets": pl.Float64,
    "audit_status": pl.String,
    "knowledge_date": pl.Date,
}


def _today() -> date:
    return date.today()


def _empty_with_schema(
    schema: dict[str, pl.DataType | type[pl.DataType]],
) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


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

            # #482（2026-10-05 实测）：财务窗口响应含同披露 update_flag=0/1
            # 两行——字段清单不含该列时值相同的两行字节级一致，触发翻页
            # 重复键守卫拒绝（守卫语义保持不变）。请求列显式携带身份后：
            # 只保留合并报表（report_type=1；调整/更正类 vintage 排除，
            # 有消费需求再扩），同一披露键（ts_code, end_date, f_ann_date）
            # 取 update_flag=1（最新）行。
            if "report_type" in response.columns:
                response = response.filter(
                    pl.col("report_type").is_null() | (pl.col("report_type") == "1")
                )
            if "update_flag" in response.columns:
                response = response.sort("update_flag").unique(
                    subset=["ts_code", "end_date", "f_ann_date"], keep="last"
                )

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

    @traced("source.tushare.fetch_earnings_forecast")
    def fetch_earnings_forecast(
        self,
        ann_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取业绩预告（上下界型，净利润上下限万元）.

        按公告日全市场使用 forecast_vip；按标的回填使用 forecast
        （非 VIP 端点要求必填 ts_code，2026-10-05 实测）。预告区间允许
        单边为空；同日修订行按 update_flag 保留为独立版本。

        Args:
            ann_date: 公告日期 (YYYY-MM-DD)，全市场按公告日抓取.
            source_ticker: 股票代码 (e.g., "000017.SZ").
            start_date: 公告开始日期 (YYYY-MM-DD).
            end_date: 公告结束日期 (YYYY-MM-DD).

        Returns:
            DataFrame with EARNINGS_FORECAST_SCHEMA columns.

        """
        api_name = "forecast_vip" if ann_date else "forecast"
        params: dict[str, str] = {
            "api_name": api_name,
            "fields": _FORECAST_FIELDS,
        }
        if ann_date:
            params["ann_date"] = ann_date.replace("-", "")
        else:
            if not source_ticker:
                msg = "按标的查询 forecast 必须指定 source_ticker"
                raise ValueError(msg)
            params["ts_code"] = source_ticker
            params["start_date"] = (start_date or "").replace("-", "")
            params["end_date"] = (end_date or "").replace("-", "")

        with tushare_fetch_error_handler("earnings_forecast", api_name):
            response = self._client.query(**params)

        if response.is_empty():
            return _empty_with_schema(EARNINGS_FORECAST_SCHEMA)

        result = (
            response.rename(
                {
                    "ts_code": "source_ticker",
                    "end_date": "report_date",
                    "type": "forecast_type",
                }
            )
            .with_columns(
                pl.col("ann_date").cast(pl.String).str.to_date("%Y%m%d", strict=False),
                pl.col("report_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False),
                pl.col("first_ann_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False),
                pl.col("update_flag").cast(pl.String),
                *(
                    pl.col(column).cast(pl.Float64, strict=False)
                    for column in (
                        "p_change_min",
                        "p_change_max",
                        "net_profit_min",
                        "net_profit_max",
                    )
                ),
                pl.lit(_today()).alias("knowledge_date"),
            )
            .filter(
                pl.col("ann_date").is_not_null() & pl.col("report_date").is_not_null()
            )
        )

        Metrics.data_records.add(
            result.height,
            {"source": "tushare", "dataset": "earnings_forecast", "status": "success"},
        )
        return result.select(*EARNINGS_FORECAST_SCHEMA)

    @traced("source.tushare.fetch_earnings_express")
    def fetch_earnings_express(
        self,
        ann_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取业绩快报（金额单位元，含审计状态）.

        按公告日全市场使用 express_vip；按标的回填使用 express。
        快报不是正式审计财报，audit_status 保留原值。

        Args:
            ann_date: 公告日期 (YYYY-MM-DD).
            source_ticker: 股票代码.
            start_date: 公告开始日期 (YYYY-MM-DD).
            end_date: 公告结束日期 (YYYY-MM-DD).

        Returns:
            DataFrame with EARNINGS_EXPRESS_SCHEMA columns.

        """
        api_name = "express_vip" if ann_date else "express"
        params: dict[str, str] = {
            "api_name": api_name,
            "fields": _EXPRESS_FIELDS,
        }
        if ann_date:
            params["ann_date"] = ann_date.replace("-", "")
        else:
            if not source_ticker:
                msg = "按标的查询 express 必须指定 source_ticker"
                raise ValueError(msg)
            params["ts_code"] = source_ticker
            params["start_date"] = (start_date or "").replace("-", "")
            params["end_date"] = (end_date or "").replace("-", "")

        with tushare_fetch_error_handler("earnings_express", api_name):
            response = self._client.query(**params)

        if response.is_empty():
            return _empty_with_schema(EARNINGS_EXPRESS_SCHEMA)

        result = (
            response.rename({"ts_code": "source_ticker", "end_date": "report_date"})
            .with_columns(
                pl.col("ann_date").cast(pl.String).str.to_date("%Y%m%d", strict=False),
                pl.col("report_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False),
                pl.col("audit_status").cast(pl.String),
                *(
                    pl.col(column).cast(pl.Float64, strict=False)
                    for column in (
                        "revenue",
                        "operate_profit",
                        "total_profit",
                        "n_income",
                        "total_assets",
                    )
                ),
                pl.lit(_today()).alias("knowledge_date"),
            )
            .filter(
                pl.col("ann_date").is_not_null() & pl.col("report_date").is_not_null()
            )
        )

        Metrics.data_records.add(
            result.height,
            {"source": "tushare", "dataset": "earnings_express", "status": "success"},
        )
        return result.select(*EARNINGS_EXPRESS_SCHEMA)

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
