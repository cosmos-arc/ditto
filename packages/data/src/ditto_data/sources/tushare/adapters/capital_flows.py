"""
Capital flow adapters: moneyflow, cyq_perf, hk_hold, hsgt_top10, top_list, top_inst.

#518/#519/#520/#523 六接口共用形状：日频全市场帧（按 trade_date）或
单标的区间（按 ts_code + start/end），mapping 各自带 kd=T+1。
"""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters._guards import assert_single_trade_date
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
    TOP10_FLOATHOLDERS_MAPPING,
    TOP10_HOLDERS_MAPPING,
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
_TOP10_HOLDERS_FIELDS = (
    "ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,"
    "hold_float_ratio,hold_change,holder_type"
)


def _collapse_same_key_rows(
    dataset: str,
    frame: pl.DataFrame,
    dedupe_subset: tuple[str, ...],
) -> pl.DataFrame:
    """
    同披露键多行确定性收敛（#482/#519 先例，#626 扩到四个事件接口）.

    源端两类同键多行形态（2026-11-01 探针实证）：
    - 冗余重复：top_list 同 (标的, 日, 原因) 多行仅 float_values null/有值
      差异（2020-02-03 600825.SH ×6）；
    - 多持有者代码：hk_hold 季度末快照同标的两行 vol/ratio 各异
      （2026-06-30 243 键；存储键无持有者维度，语义上不可分——两行
      ratio 分母不一致，求和不可辩护，按先例单行留档损失）。
    收敛规则：行内空值数降序（最完整行最后=keep-last 胜出）+ 整行哈希
    平局——同一行集合无论源端返回顺序如何都选出同一行（重试幂等）。
    平局哈希是 polars 版本敏感的（<2 pin 内构建确定）；hk_hold 季度末
    两全值持有者行属主导形态，胜者由哈希定，polars 升级后重拉同日可能
    换行（correctness #626 F4 留档，升级后复跑存量季度日核对）。
    同键行非空值互异（真冲突而非冗余）时 WARN 留痕可观测，不静默择一
    （correctness #626 F2）。
    """
    if frame.is_empty():
        return frame
    rows_before = frame.height
    _warn_conflicting_same_key_values(dataset, frame, dedupe_subset)
    collapsed = (
        frame.with_columns(
            _row_nulls=pl.sum_horizontal(pl.all().is_null().cast(pl.UInt32)),
        )
        .with_columns(_dedupe_hash=pl.struct(pl.all()).hash())
        .sort(
            [pl.col("_row_nulls"), pl.col("_dedupe_hash")],
            descending=[True, False],
        )
        .unique(subset=list(dedupe_subset), keep="last")
        .drop("_row_nulls", "_dedupe_hash")
    )
    if collapsed.height < rows_before:
        logger.info(
            f"Tushare {dataset} collapsed same-key rows",
            event=f"tushare_{dataset}_key_dedupe",
            rows_before=rows_before,
            rows_after=collapsed.height,
        )
    return collapsed


def _warn_conflicting_same_key_values(
    dataset: str,
    frame: pl.DataFrame,
    dedupe_subset: tuple[str, ...],
) -> None:
    """同键行有互异非空值（真冲突）时告警——与良性冗余可区分（F2）."""
    key_counts = frame.group_by(list(dedupe_subset)).len()
    dup_keys = key_counts.filter(pl.col("len") > 1).drop("len")
    if dup_keys.is_empty():
        return
    value_columns = [c for c in frame.columns if c not in dedupe_subset]
    conflicts = (
        frame.join(dup_keys, on=list(dedupe_subset), how="semi")
        .group_by(list(dedupe_subset))
        .agg(pl.col(name).drop_nulls().n_unique().alias(name) for name in value_columns)
        .filter(pl.any_horizontal(pl.col(name) > 1 for name in value_columns))
    )
    for row in conflicts.iter_rows(named=True):
        key = {k: row[k] for k in dedupe_subset}
        differing = sorted(name for name in value_columns if row[name] > 1)
        logger.warning(
            f"Tushare {dataset} same-key rows carry conflicting values",
            event=f"tushare_{dataset}_key_conflict",
            key=key,
            differing_columns=differing,
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
        dedupe_subset: tuple[str, ...] = (),
    ) -> pl.DataFrame:
        """
        共用形状：单日全市场 / 单标的区间，mapping 统一 kd=T+1.

        ``dedupe_subset`` 非空时对事件接口做同披露键确定性收敛
        （``_collapse_same_key_rows``）；moneyflow/cyq_perf 逐标的
        单行契约不收敛，真重复交 DQ unique 响亮失败。
        """
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
            # 单日全市场形态（trade_date 且无区间）守卫响应日=请求日（#585）；
            # 单标的区间形态天然跨日，不守卫。
            requested_day = query.get("trade_date")
            if requested_day and not (query.get("start_date") or query.get("end_date")):
                assert_single_trade_date(
                    response,
                    expected=requested_day.replace("-", ""),
                    dataset=dataset,
                )
            result = TushareDataTransformer.transform(response, dataset, mapping)
            if dedupe_subset:
                result = _collapse_same_key_rows(dataset, result, dedupe_subset)
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
        """
        沪深港通持股（vol 股/ratio %；北向 SH/SZ 入库，#520）.

        季度末快照同标的可因多个北向持有者代码出现多行（#626 实证
        2026-06-30 243 键）——存储键无持有者维度，确定性收敛为单行，
        损失在 mapping 头注释留档。
        """
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
            dedupe_subset=("source_ticker", "trade_date"),
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
            dedupe_subset=("source_ticker", "trade_date", "market_type"),
        )

    @traced("source.tushare.fetch_top_list")
    def fetch_top_list(
        self,
        ts_code: str | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        龙虎榜个股明细（金额元；reason 进主键，#519）.

        同 (标的, 日, 原因) 冗余多行仅 float_values null/有值差异
        （#626 实证 2020-02-03 600825.SH ×6）——确定性收敛，最完整
        行胜出。
        """
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
            dedupe_subset=("source_ticker", "trade_date", "reason"),
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
        原因) 可出现多行；存储主键无席位 ID 维度，按身份键去重
        （#482 同披露键去重先例；#626 下沉为四事件接口共用收敛），
        同名多机构的合并损失在 mapping 头注释留档。
        """
        return self._fetch_daily_frame(
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
            dedupe_subset=(
                "source_ticker",
                "trade_date",
                "exalter",
                "side",
                "reason",
            ),
        )

    @traced("source.tushare.fetch_top10_holders")
    def fetch_top10_holders(
        self,
        ts_code: str | None = None,
        ann_date: str | None = None,
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        前十大股东（#627，公告日驱动）.

        市场级按 ann_date/period 单请求（2026-11-01 代理实测文档标 ts_code
        必选但市场级可用）；单标的按 ts_code + 报告期区间。hold_amount 股、
        hold_ratio/hold_float_ratio %、hold_change 股（0=不变 null=新进）；
        修订=新 ann_date 版本行。跨期名单跌出不等于清仓。
        """
        return self._fetch_daily_frame(
            "top10_holders",
            "top10_holders",
            _TOP10_HOLDERS_FIELDS,
            TOP10_HOLDERS_MAPPING,
            {
                "ts_code": ts_code,
                "ann_date": ann_date,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
            },
            dedupe_subset=(
                "source_ticker",
                "report_date",
                "knowledge_date",
                "holder_name",
            ),
        )

    @traced("source.tushare.fetch_top10_floatholders")
    def fetch_top10_floatholders(
        self,
        ts_code: str | None = None,
        ann_date: str | None = None,
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        前十大流通股东（#627，字段同 top10_holders，名单口径为流通股东榜）.

        两榜同名行值可一致（2026-11-01 实测 000002.SZ 2026Q1），语义
        不同各存一行，不互推；不推导整体持仓。
        """
        return self._fetch_daily_frame(
            "top10_floatholders",
            "top10_floatholders",
            _TOP10_HOLDERS_FIELDS,
            TOP10_FLOATHOLDERS_MAPPING,
            {
                "ts_code": ts_code,
                "ann_date": ann_date,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
            },
            dedupe_subset=(
                "source_ticker",
                "report_date",
                "knowledge_date",
                "holder_name",
            ),
        )
