"""
Capital flow adapters: moneyflow, cyq_perf, hk_hold, hsgt_top10, top_list, top_inst.

#518/#519/#520/#523 六接口共用形状：日频全市场帧（按 trade_date）或
单标的区间（按 ts_code + start/end），mapping 各自带 kd=T+1。
"""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.column_mapping import ColumnMapping
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import (
    CYQ_PERF_MAPPING,
    HK_HOLD_MAPPING,
    HSGT_TOP10_MAPPING,
    MONEYFLOW_MAPPING,
    TOP_INST_MAPPING,
    TOP_LIST_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer

_MONEYFLOW_FIELDS = (
    "trade_date,ts_code,buy_elg_amount,buy_elg_vol,buy_lg_amount,buy_lg_vol,"
    "buy_md_amount,buy_md_vol,buy_sm_amount,buy_sm_vol,net_mf_amount,net_mf_vol,"
    "sell_elg_amount,sell_elg_vol,sell_lg_amount,sell_lg_vol,sell_md_amount,"
    "sell_md_vol,sell_sm_amount,sell_sm_vol"
)
_CYQ_PERF_FIELDS = (
    "ts_code,trade_date,cost_5pct,cost_15pct,cost_50pct,cost_85pct,cost_95pct,"
    "his_high,his_low,weight_avg,winner_rate"
)
_HK_HOLD_FIELDS = "code,trade_date,ts_code,name,vol,ratio,exchange"
_HSGT_TOP10_FIELDS = (
    "trade_date,ts_code,name,close,change,rank,market_type,amount,net_amount,buy,sell"
)
_TOP_LIST_FIELDS = (
    "trade_date,ts_code,name,close,pct_change,turnover_rate,amount,l_sell,"
    "l_buy,l_amount,net_amount,net_rate,amount_rate,float_values,reason"
)
_TOP_INST_FIELDS = (
    "trade_date,ts_code,exalter,side,buy,buy_rate,sell,sell_rate,net_buy,reason"
)


class CapitalFlowsTushareAdapter(BaseTushareAdapter):
    """资金面/情绪/席位六接口 Tushare 适配器."""

    def _fetch_daily_frame(
        self,
        dataset: str,
        api_name: str,
        fields: str,
        mapping: ColumnMapping,
        query: dict[str, str | None],
    ) -> pl.DataFrame:
        """共用形状：单日全市场 / 单标的区间，mapping 统一 kd=T+1."""
        logger.info(
            f"Fetching Tushare {dataset}",
            event=f"tushare_{dataset}_fetch_start",
            **{k: v for k, v in query.items() if v},
        )
        with tushare_fetch_error_handler(dataset, api_name):
            params: dict[str, str] = {
                "api_name": api_name,
                "fields": fields,
            }
            params.update({k: v.replace("-", "") for k, v in query.items() if v})
            response = self._client.query(**params)
            result = TushareDataTransformer.transform(response, dataset, mapping)
            row_count = len(result)
            logger.info(
                f"Tushare {dataset} fetched",
                event=f"tushare_{dataset}_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {"source": "tushare", "dataset": dataset, "status": "success"},
            )
            return result

    @traced("source.tushare.fetch_moneyflow")
    def fetch_moneyflow(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """个股资金流向（金额万元/量手，#518）."""
        return self._fetch_daily_frame(
            "moneyflow",
            "moneyflow",
            _MONEYFLOW_FIELDS,
            MONEYFLOW_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_cyq_perf")
    def fetch_cyq_perf(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """每日筹码及胜率（价格元/winner_rate %，#523）."""
        return self._fetch_daily_frame(
            "cyq_perf",
            "cyq_perf",
            _CYQ_PERF_FIELDS,
            CYQ_PERF_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_hk_hold")
    def fetch_hk_hold(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """沪深港通持股（vol 股/ratio %；北向 SH/SZ 入库，#520）."""
        return self._fetch_daily_frame(
            "hk_hold",
            "hk_hold",
            _HK_HOLD_FIELDS,
            HK_HOLD_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_hsgt_top10")
    def fetch_hsgt_top10(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """沪深港通十大成交股（金额元；改制后 buy/sell/net 停披，#520）."""
        return self._fetch_daily_frame(
            "hsgt_top10",
            "hsgt_top10",
            _HSGT_TOP10_FIELDS,
            HSGT_TOP10_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_top_list")
    def fetch_top_list(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """龙虎榜个股明细（金额元；reason 进主键，#519）."""
        return self._fetch_daily_frame(
            "top_list",
            "top_list",
            _TOP_LIST_FIELDS,
            TOP_LIST_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @traced("source.tushare.fetch_top_inst")
    def fetch_top_inst(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        龙虎榜席位明细（金额元；exalter+side 进主键，#519）.

        源端「机构专用」是多家机构的共用席位名，同 (标的, 日, 席位, 方向,
        原因) 可出现多行；存储主键无席位 ID 维度，按身份键去重保末行
        （#482 同披露键去重先例），同名多机构的合并损失在 mapping 头注释
        留档。
        """
        frame = self._fetch_daily_frame(
            "top_inst",
            "top_inst",
            _TOP_INST_FIELDS,
            TOP_INST_MAPPING,
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        if frame.is_empty():
            return frame
        return frame.unique(
            subset=[
                "source_ticker",
                "trade_date",
                "exalter",
                "side",
                "reason",
            ],
            keep="last",
            maintain_order=True,
        )
