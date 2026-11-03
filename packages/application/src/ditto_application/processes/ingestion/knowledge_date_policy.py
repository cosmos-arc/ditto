"""
可知时间策略：两融/北向 knowledge_date 按披露制度与适用日历修正（#658 批次1E）.

此前 margin_trading/hk_hold/hsgt_top10 的映射层用自然日 T+1 伪造可知时间。
自然日 T+1 对日行情是保守方向（T 日数据次日才"可知"），但两融的交易所
规则是「每个交易日开市前公布前一交易日数据」（深交所投资者问答；
tushare doc_id=59 特别说明深市/北交所周五数据下周一上午更新）——周五/
节前数据的自然日 T+1 早于真实发布，构成 PIT 泄漏。北向 hk_hold 在
2024-08-19 起改制为季度披露（HKEX：前一季度数据在季末后第 5 个北向
交易日公布），自然日 T+1 同样泄漏。

修正在写入路径统一校准（DataWriter 分发前），映射层的自然日 T+1 仅作
schema 占位、写入前必然被本策略覆写：

- ``NEXT_TRADING_DAY``：knowledge_date = trade_date 之后的下一个 A 股
  交易日（周末、长假自然跨过；适用 margin_trading/hsgt_top10 与
  hk_hold 日频制度段）。这不是机械的「普通交易日 T+1」——它以交易所
  开市前发布制度为依据（#653：不把自然日 T+1 换成无依据的日历规则）。
- ``hk_hold`` 季度制度段（trade_date >= 2024-08-19）：真实发布日=
  季末后第 5 个北向交易日，北向交易日历尚未入库，无发布日证据时
  fail-safe 取 run_date（上海时区观察日）——宁可保守推迟可知时间，
  不伪造早于发布的可知性。**已知边界（correctness F1，批次2 根修）**：
  run_date 随墙钟变化，同一 retained payload 跨日重放会使 canonical
  checksum 漂移、触发 SNAPSHOT_CANONICAL_DRIFT 响亮失败（不静默污染），
  且按 (instrument, trade_date, knowledge_date) 新键追加版本行——
  同日重试（常规路径）确定性成立，跨日 force 重取/中断重放会阻断该
  分区直至批次2 以北向日历/发布日证据重算存量并出新版本。北向日历
  入库后应按制度重算并走存量纠正（批次2）。

存量已落库的错误 knowledge_date 不在本模块处理（#653：先盘点受影响
行，保留原证据、新身份纠正——批次2）。
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date
from typing import Literal

import polars as pl
from ditto_platform.foundation import logger

__all__ = [
    "CALENDAR_LOOKAHEAD_DAYS",
    "HK_HOLD_QUARTERLY_REGIME_START",
    "KnowledgeDatePolicy",
    "calibrate_knowledge_dates",
    "knowledge_date_policy_for",
]

KnowledgeDatePolicy = Literal["next_trading_day", "hk_hold_segmented"]

# hk_hold 制度分段（#626 裁决留档：2024-08-19 起北向改季度披露）。
HK_HOLD_QUARTERLY_REGIME_START = date(2024, 8, 19)

# 日频发布制度数据集：交易日开市前公布前一交易日数据。
_NEXT_TRADING_DAY_DATASETS: frozenset[str] = frozenset(
    {
        "margin_trading",
        "hsgt_top10",
    }
)

# 查找下一交易日时的日历前瞻缓冲（覆盖春节/国庆长假），超出仍找不到
# 则 fail closed（日历本身覆盖到 2027，属摄取边界错误）。
CALENDAR_LOOKAHEAD_DAYS = 31


def knowledge_date_policy_for(dataset: str) -> KnowledgeDatePolicy | None:
    """数据集的可知时间策略；None=维持映射层既有值，不校准."""
    if dataset in _NEXT_TRADING_DAY_DATASETS:
        return "next_trading_day"
    if dataset == "hk_hold":
        return "hk_hold_segmented"
    return None


def calibrate_knowledge_dates(
    df: pl.DataFrame,
    *,
    dataset: str,
    trading_days: tuple[date, ...],
    run_date: date,
) -> pl.DataFrame:
    """
    按策略重算 knowledge_date（及随动的 effective_from）.

    Args:
        df: 源层帧，须含 trade_date 与 knowledge_date 列（Date 型）。
        dataset: 数据集名。
        trading_days: 升序交易日序列（含 trade_date 之后足够的日历覆盖）。
        run_date: 本次写入的观察日（hk_hold 季度段的知识日下界）。

    Raises:
        ValueError: 需要 next_trading_day 但日历无法给出 trade_date 之后
            的交易日（日历覆盖不足），fail closed 拒绝写入错误可知时间。

    """
    if df.is_empty() or "knowledge_date" not in df.columns:
        return df
    policy = knowledge_date_policy_for(dataset)
    if policy is None:
        return df

    trade_dates = df["trade_date"].cast(pl.Date)
    if policy == "next_trading_day":
        new_knowledge = _next_trading_days(
            trade_dates, dataset=dataset, trading_days=trading_days
        )
    else:  # hk_hold 分段：日频段=下一交易日；季度段=观察日
        new_knowledge = pl.Series(
            [
                _next_trading_day_one(d, dataset=dataset, trading_days=trading_days)
                if d < HK_HOLD_QUARTERLY_REGIME_START
                else run_date
                for d in trade_dates.to_list()
            ],
            dtype=pl.Date,
        )

    df = df.with_columns(new_knowledge.alias("knowledge_date"))
    if "effective_from" in df.columns:
        # 适配层约定 effective_from = knowledge_date（margin 等资金面事实）。
        df = df.with_columns(pl.col("knowledge_date").alias("effective_from"))
    logger.info(
        "knowledge_date calibrated by disclosure policy",
        event="ingestion_knowledge_date_calibrated",
        dataset=dataset,
        policy=policy,
        rows=df.height,
    )
    return df


def _next_trading_days(
    trade_dates: pl.Series,
    *,
    dataset: str,
    trading_days: tuple[date, ...],
) -> pl.Series:
    return pl.Series(
        [
            _next_trading_day_one(d, dataset=dataset, trading_days=trading_days)
            for d in trade_dates.to_list()
        ],
        dtype=pl.Date,
    )


def _next_trading_day_one(
    trade_date: date,
    *,
    dataset: str,
    trading_days: tuple[date, ...],
) -> date:
    index = bisect_right(trading_days, trade_date)
    if index >= len(trading_days):
        raise ValueError(
            f"{dataset}: no trading day after {trade_date} in calendar "
            + f"(lookahead {CALENDAR_LOOKAHEAD_DAYS}d) — refusing to write "
            + "unverifiable knowledge_date (#658 B1E)"
        )
    return trading_days[index]
