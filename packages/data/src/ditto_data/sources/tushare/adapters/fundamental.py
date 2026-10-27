"""Fundamental domain Tushare adapter implementation."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced
from ditto_platform.foundation.storage import CORRECTION_FLAG_COLUMN

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
    FINA_INDICATOR_MAPPING,
    FUND_PORTFOLIO_MAPPING,
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


_FINA_PAGE_SIZE = 2000

# fina_indicator 显式请求字段集（#591）。源端默认列集（fields 省略）不含
# update_flag，须显式点名才能拿到同披露键的版本判别列。列序对齐历史
# 存量帧（server 默认序：ts_code,ann_date,end_date + 指标序），否则
# parquet 追加 vstack 因列序不一致拒收；update_flag 附尾，选版后即弃。
# 上游新增指标列不会自动透传，出现时在此追加（透传换确定性的既定取舍）。
_FINA_INDICATOR_REQUEST_FIELDS = (
    "ts_code,ann_date,end_date,eps,dt_eps,total_revenue_ps,revenue_ps,"
    "capital_rese_ps,surplus_rese_ps,undist_profit_ps,extra_item,profit_dedt,"
    "gross_margin,current_ratio,quick_ratio,cash_ratio,ar_turn,ca_turn,fa_turn,"
    "assets_turn,op_income,ebit,ebitda,fcff,fcfe,current_exint,noncurrent_exint,"
    "interestdebt,netdebt,tangible_asset,working_capital,networking_capital,"
    "invest_capital,retained_earnings,diluted2_eps,bps,ocfps,retainedps,cfps,"
    "ebit_ps,fcff_ps,fcfe_ps,netprofit_margin,grossprofit_margin,cogs_of_sales,"
    "expense_of_sales,profit_to_gr,saleexp_to_gr,adminexp_of_gr,finaexp_of_gr,"
    "impai_ttm,gc_of_gr,op_of_gr,ebit_of_gr,roe,roe_waa,roe_dt,roa,npta,roic,"
    "roe_yearly,roa2_yearly,debt_to_assets,assets_to_eqt,dp_assets_to_eqt,"
    "ca_to_assets,nca_to_assets,tbassets_to_totalassets,int_to_talcap,"
    "eqt_to_talcapital,currentdebt_to_debt,longdeb_to_debt,ocf_to_shortdebt,"
    "debt_to_eqt,eqt_to_debt,eqt_to_interestdebt,tangibleasset_to_debt,"
    "tangasset_to_intdebt,tangibleasset_to_netdebt,ocf_to_debt,turn_days,"
    "roa_yearly,roa_dp,fixed_assets,profit_to_op,q_saleexp_to_gr,q_gc_to_gr,"
    "q_roe,q_dt_roe,q_npta,q_ocf_to_sales,basic_eps_yoy,dt_eps_yoy,cfps_yoy,"
    "op_yoy,ebt_yoy,netprofit_yoy,dt_netprofit_yoy,ocf_yoy,roe_yoy,bps_yoy,"
    "assets_yoy,eqt_yoy,tr_yoy,or_yoy,q_sales_yoy,q_op_qoq,equity_yoy,"
    "update_flag"
)


def _normalize_fina_numeric_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """
    118 指标列统一 Float64（correctness review #4）.

    透传列的 dtype 由响应推断（Int64/Float64/Null 随当日值漂移）；
    不归一则日更全窗口重拉在 VERIFY_IDENTICAL 下因 dtype 漂移硬失败。
    身份/日期列之外全部 cast Float64（strict 容忍偶发字符串）。
    update_flag 是选版判别列（#591），显式 cast String——透传 dtype 由
    响应推断，源端改送数值 0/1 时字符串比较会 ComputeError 硬失败
    （correctness F2；防御先例见 fetch_earnings_forecast）。
    """
    if frame.is_empty():
        return frame
    identity = {"source_ticker", "report_date", "knowledge_date", "update_flag"}
    casts = [
        pl.col(name).cast(pl.Float64, strict=False)
        for name, dtype in frame.schema.items()
        if name not in identity and dtype != pl.Float64
    ]
    flag_casts = (
        [pl.col("update_flag").cast(pl.String)]
        if "update_flag" in frame.columns
        else []
    )
    return frame.with_columns([*casts, *flag_casts]) if casts or flag_casts else frame


def _dedupe_fina_disclosure_key(frame: pl.DataFrame) -> pl.DataFrame:
    """
    同披露键（标的, 报告期, 公告日）多版本行去重（#484 先例）.

    #591 选版语义（2026-10-23 探针实证 period=20260331：值不同的同键行
    1022/1022 为 update_flag 0/1 版本共存，旧行 null 新行有值，真同键
    改值为 0）：**update_flag='1' 优先**；同 flag 平局按整行哈希排序
    keep-last——同一行集合无论源端返回顺序如何都选出同一行（重试幂等，
    correctness review #6）。
    选版后 update_flag 转为 CORRECTION_FLAG_COLUMN 布尔列保留（#613 G：
    修正行经写入层 KEEP_LAST_FLAGGED 单调升级存量，防数据源两代快照
    翻转；列由写入层剥离，不进存量 schema）。update_flag 列缺失时回退
    纯哈希排序并置 False（旧行为）。
    """
    if frame.is_empty():
        return frame
    work = frame.with_columns(_row_hash_expr(frame).alias("_dedupe_hash"))
    if "update_flag" in frame.columns:
        work = work.sort(
            [
                (pl.col("update_flag") == "1").cast(pl.UInt8).fill_null(0),
                pl.col("_dedupe_hash"),
            ]
        )
        drop_cols = ["_dedupe_hash", "update_flag"]
        winner_is_correction = (pl.col("update_flag") == "1").fill_null(False)
    else:
        # 正常请求恒含 update_flag（显式字段集）；缺列意味着源端/代理
        # 行为漂移，选版退化为纯哈希——告警可见，不静默（correctness F3）。
        logger.warning(
            "update_flag missing in fina response; hash-only dedup fallback",
            event="fina_dedupe_update_flag_missing",
        )
        work = work.sort("_dedupe_hash")
        drop_cols = ["_dedupe_hash"]
        winner_is_correction = pl.lit(False)
    return (
        work.unique(
            subset=["source_ticker", "report_date", "knowledge_date"],
            keep="last",
        )
        .with_columns(winner_is_correction.alias(CORRECTION_FLAG_COLUMN))
        .drop(drop_cols)
    )


def _row_hash_expr(frame: pl.DataFrame) -> pl.Expr:
    """整行确定性哈希（列序固定于调用时的 schema）."""
    return pl.struct(pl.all()).hash()


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
            # #591：本块仅适用财务三表（披露锚 f_ann_date）；fina_indicator
            # 披露锚是 ann_date 且选版由 _dedupe_fina_disclosure_key 承担，
            # 不经此块。
            if "report_type" in response.columns:
                response = response.filter(
                    pl.col("report_type").is_null() | (pl.col("report_type") == "1")
                )
            if "update_flag" in response.columns and "f_ann_date" in response.columns:
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

    @traced("source.tushare.fetch_fina_indicator")
    def fetch_fina_indicator(
        self,
        ts_code: str | None = None,
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取官方口径财务指标 (#521).

        三表衍生指标的官方对照源：指标列透传（mapping 无 output_columns），
        kd=ann_date（公告锚）。同披露键多版本共存：跨公告日的修订以新
        ann_date 版本呈现；**同披露键**（同 ts_code/end_date/ann_date）的
        update_flag 0/1 版本行按 #591 选版语义去重（'1' 优先，见
        _dedupe_fina_disclosure_key）。
        单位：每股指标元/股、比率 %、绝对额元。

        Args:
            ts_code: 股票代码 (e.g., "600519.SH")
            period: 报告期 (YYYYMMDD，如 "20240331")，全市场批量
            start_date: 公告开始日期 (YYYYMMDD，配 ts_code)
            end_date: 公告结束日期 (YYYYMMDD，配 ts_code)

        """
        # 显式字段集（含 update_flag）：源端默认列集不含选版判别列（#591）；
        # 全字段请求还让同披露键的多版本行彼此可区分，避免翻页守卫把同键
        # 行折叠成 in-page 重复而拒收（2026-10-06 实测 in-page 重复 875 行）。
        result = self._fetch_financial(
            dataset="fina_indicator",
            api_name="fina_indicator",
            fields=_FINA_INDICATOR_REQUEST_FIELDS,
            mapping=FINA_INDICATOR_MAPPING,
            log_name="fina indicator",
            extra_params={
                "ts_code": ts_code,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
            },
            add_pit=False,
        )
        return _dedupe_fina_disclosure_key(_normalize_fina_numeric_columns(result))

    @traced("source.tushare.fetch_fina_indicator_vip")
    def fetch_fina_indicator_vip(
        self,
        period: str | None = None,
        ann_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取官方口径财务指标——VIP 批量端点 (#521).

        代理 transport 的非 VIP fina_indicator 必填 ts_code（2026-10-06
        实测 code=「必填参数, 标的」），日更披露增量走本端点按 period
        全市场批量（与 forecast/express 的 vip 形态一致）。
        """
        # 源端存在字节级重复行（2026-10-06 实测同 period 响应 in-page 重复
        # 875+ 行，且与请求字段集无关）——自动翻页的重复守卫会拒收。fina
        # 端点走调用方自管分页（单页语义），取尽后统一按披露键去重
        # （#591 显式字段集含 update_flag，选版 '1' 优先）。
        params: dict[str, str | None] = {
            "period": period,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
        }
        active = {k: v for k, v in params.items() if v}
        with tushare_fetch_error_handler("fina_indicator", "fina_indicator_vip"):
            pages: list[pl.DataFrame] = []
            offset = 0
            while True:
                page = self._client.query(
                    api_name="fina_indicator_vip",
                    fields=_FINA_INDICATOR_REQUEST_FIELDS,
                    limit=_FINA_PAGE_SIZE,
                    offset=offset,
                    **active,
                )
                if page.height > 0:
                    # 终页（总行数恰为页宽整数倍时）是 all-String 空 schema，
                    # 进 concat 会把数值列拉成 String——空页丢弃。
                    pages.append(page)
                if page.height < _FINA_PAGE_SIZE:
                    break
                offset += _FINA_PAGE_SIZE
            raw = pl.concat(pages, how="diagonal_relaxed") if pages else pl.DataFrame()
            logger.info(
                "Tushare fina indicator (VIP) fetched",
                event="tushare_fina_indicator_fetch_complete",
                row_count=raw.height,
            )
            Metrics.data_records.add(
                raw.height,
                {"source": "tushare", "dataset": "fina_indicator", "status": "success"},
            )
        result = TushareDataTransformer.transform(
            raw, "fina_indicator", FINA_INDICATOR_MAPPING
        )
        return _dedupe_fina_disclosure_key(_normalize_fina_numeric_columns(result))

    @traced("source.tushare.fetch_fund_portfolio")
    def fetch_fund_portfolio(
        self,
        ts_code: str | None = None,
        ann_date: str | None = None,
        period: str | None = None,
    ) -> pl.DataFrame:
        """
        获取基金持仓 (#522，公告日驱动).

        季度持仓披露，修订以新 ann_date 行呈现（#452 观察事实语义）；
        market_value 元、holding_shares 股、比率 %。响应含全部基金类型
        （含 .OF 场外），未注册身份在写入层过滤留痕。

        Args:
            ts_code: 基金代码 (e.g., "510300.SH")
            ann_date: 公告日期 (YYYYMMDD)，全市场按披露日抓取
            period: 报告期 (YYYYMMDD)

        """
        logger.info(
            "Fetching Tushare fund portfolio",
            event="tushare_fund_portfolio_fetch_start",
            ts_code=ts_code,
            ann_date=ann_date,
            period=period,
        )
        with tushare_fetch_error_handler("fund_portfolio", "fund_portfolio"):
            params: dict[str, str] = {
                "api_name": "fund_portfolio",
                "fields": (
                    "ts_code,ann_date,end_date,symbol,mkv,amount,"
                    "stk_mkv_ratio,stk_float_ratio"
                ),
            }
            if ts_code:
                params["ts_code"] = ts_code
            if ann_date:
                params["ann_date"] = ann_date
            if period:
                params["period"] = period
            response = self._client.query(**params)
            result = TushareDataTransformer.transform(
                response, "fund_portfolio", FUND_PORTFOLIO_MAPPING
            )
            Metrics.data_records.add(
                len(result),
                {
                    "source": "tushare",
                    "dataset": "fund_portfolio",
                    "status": "success",
                },
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
