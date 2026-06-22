"""
BacktestReportSerializer — 将 BacktestReport 序列化为 JSON + Parquet.

纯计算模块（零 I/O）：
  - serialize_report() 返回 JSON bytes + Parquet DataFrame 字典
  - 文件写入由 App 层负责
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import orjson
import polars as pl
from ditto_backtest.manifest import RunManifest
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_backtest.statistics import BacktestReport

__all__ = ["serialize_report"]


def serialize_report(
    report: BacktestReport,
    *,
    rebalance_freq: str = "daily",
    manifest: RunManifest | None = None,
    resume_provenance: Mapping[str, object] | None = None,
    strategy_promotion: Mapping[str, object] | None = None,
) -> tuple[bytes, dict[str, pl.DataFrame]]:
    """
    将 BacktestReport 序列化为 JSON bytes + Parquet DataFrame 字典.

    Args:
        report: 回测报告.
        rebalance_freq: 调仓频率 (daily / weekly / monthly).
            写入 JSON 供 replay 反序列化时恢复配置，默认 "daily".
        manifest: 可选运行清单，用于将 PIT policy 等审计字段写入报告 JSON。
        resume_provenance: 可选 checkpoint 恢复来源证据。
        strategy_promotion: 可选策略晋级证据 block，写入报告 JSON。

    Returns:
        (json_bytes, parquet_tables) 二元组.
        json_bytes: 报告元数据的 JSON 字节.
        parquet_tables: 名称到 DataFrame 的映射.
            键: nav / portfolio_stats / trade_log / fill_log.

    """
    # 1. JSON 元数据
    json_data = {
        "run_id": report.run_id,
        "period": {"start": report.period[0], "end": report.period[1]},
        "initial_cash": report.initial_cash,
        "final_nav": report.final_nav,
        "aggregated_trade_stats": dataclasses.asdict(report.aggregated_trade_stats),
        "alpha_stats": dataclasses.asdict(report.alpha_stats),
        "rebalance_freq": rebalance_freq,
        "nav_series": (
            [v for _, v in report.nav_series] if report.nav_series else None
        ),
    }
    if manifest is not None:
        json_data["pit_policy"] = {
            "time_column": manifest.pit_time_column,
            "policy": manifest.pit_policy,
            "unsafe_time_policy": manifest.unsafe_time_policy,
            "knowledge_lag_days": manifest.knowledge_lag_days,
        }
    if resume_provenance is not None:
        json_data["resume_provenance"] = dict(resume_provenance)
    if strategy_promotion is not None:
        json_data["strategy_promotion"] = dict(strategy_promotion)
    if report.final_account_state is not None:
        json_data["final_account_state"] = (
            BacktestAccountStateSnapshot.from_account_view(
                report.final_account_state,
            ).to_payload()
        )
    json_bytes = orjson.dumps(json_data, option=orjson.OPT_INDENT_2)

    # 2. Parquet 表
    parquet_tables: dict[str, pl.DataFrame] = {}

    if report.nav_series:
        parquet_tables["nav"] = pl.DataFrame(
            [{"trade_date": d, "nav": v} for d, v in report.nav_series],
        )

    if report.portfolio_stats:
        parquet_tables["portfolio_stats"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.portfolio_stats],
        )

    if report.trade_log:
        parquet_tables["trade_log"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.trade_log],
        )

    if report.fill_log:
        parquet_tables["fill_log"] = pl.DataFrame(
            [dataclasses.asdict(r) for r in report.fill_log],
        )

    return json_bytes, parquet_tables
