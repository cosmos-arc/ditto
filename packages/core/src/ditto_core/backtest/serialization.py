"""
BacktestReportSerializer — 将 BacktestReport 序列化为 JSON + Parquet.

输出文件:
  - backtest_report.json: 报告元数据 (run_id, period, stats 等)
  - nav.parquet: NAV 时间序列
  - trade_log.parquet: 交易记录
  - fill_log.parquet: 成交记录
  - portfolio_stats.parquet: 每日组合统计

空列表的 tabular 数据不产生对应文件。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import orjson
import polars as pl
from ditto_infra.foundation.util.io import atomic_bytes_write, atomic_write

from ditto_core.backtest.statistics import BacktestReport

__all__ = ["serialize"]


def serialize(report: BacktestReport, output_dir: Path) -> Path:
    """
    将 BacktestReport 序列化为 JSON + Parquet 文件.

    Args:
        report: 回测报告.
        output_dir: 输出目录（不存在则自动创建）.

    Returns:
        主文件路径 (backtest_report.json).

    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 写 JSON 元数据
    json_data = {
        "run_id": report.run_id,
        "period": list(report.period),
        "initial_cash": report.initial_cash,
        "final_nav": report.final_nav,
        "aggregated_trade_stats": dataclasses.asdict(report.aggregated_trade_stats),
        "alpha_stats": dataclasses.asdict(report.alpha_stats),
    }
    json_bytes = orjson.dumps(json_data, option=orjson.OPT_INDENT_2)
    json_path = output_dir / "backtest_report.json"
    atomic_bytes_write(json_bytes, json_path)

    # 2. 写 nav.parquet
    if report.nav_series:
        _write_parquet(
            output_dir / "nav.parquet",
            [{"trade_date": d, "nav": v} for d, v in report.nav_series],
        )

    # 3. 写 portfolio_stats.parquet
    if report.portfolio_stats:
        _write_parquet(
            output_dir / "portfolio_stats.parquet",
            [dataclasses.asdict(r) for r in report.portfolio_stats],
        )

    # 4. 写 trade_log.parquet
    if report.trade_log:
        _write_parquet(
            output_dir / "trade_log.parquet",
            [dataclasses.asdict(r) for r in report.trade_log],
        )

    # 5. 写 fill_log.parquet
    if report.fill_log:
        _write_parquet(
            output_dir / "fill_log.parquet",
            [dataclasses.asdict(r) for r in report.fill_log],
        )

    return json_path


def _write_parquet(path: Path, records: list[dict[str, object]]) -> None:
    """将记录列表写入 Parquet 文件。"""
    df = pl.DataFrame(records)
    atomic_write(df, path)
