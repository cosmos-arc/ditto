"""
共享 StrategyInputBundle 构建函数.

提取自 engine.py 和 strategy.py 中近乎相同的 _build_input_bundle 逻辑，
统一为纯函数，供 EngineLoop 和 StrategyStep 共同调用。

子类覆盖 EngineLoop._build_input_bundle 时，可直接调用此函数并传入
extra_instrument_columns 来注入额外列（如 sector_id / is_sector）。
"""

from __future__ import annotations

import polars as pl
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.pipeline import StrategyInputBundle

from ditto_backtest.data_feed import MarketSnapshot

__all__ = ["build_input_bundle"]


def build_input_bundle(
    trade_date: str,
    strategy_id: str,
    run_id: str,
    bars: dict[InstrumentId, MarketSnapshot],
    benchmark_close: float | None = None,
    *,
    extra_instrument_columns: dict[str, list[object]] | None = None,
) -> StrategyInputBundle:
    """
    从 bars 构建 StrategyInputBundle.

    Args:
        trade_date: 交易日期 (YYYY-MM-DD)
        strategy_id: 策略 ID
        run_id: 运行 ID
        bars: instrument_id → MarketSnapshot 映射
        benchmark_close: 基准收盘价（可选）
        extra_instrument_columns: instruments DataFrame 的额外列，
            键为列名，值为与 bars 顺序一致的列表。

    Returns:
        构建完成的 StrategyInputBundle。

    """
    instrument_ids = list(bars.keys())

    # 构建 instruments DataFrame，可选合并额外列
    if extra_instrument_columns is not None:
        # 合并基础列和额外列
        column_data: dict[str, list[object]] = {"instrument_id": list(instrument_ids)}
        for col_name, col_values in extra_instrument_columns.items():
            column_data[col_name] = col_values
        instruments = pl.DataFrame(column_data)
    else:
        instruments = pl.DataFrame({"instrument_id": instrument_ids})

    market_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    for iid, bar in bars.items():
        market_rows.append(
            {
                "instrument_id": iid,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        )
        signal_rows.append(
            {
                "instrument_id": iid,
                "signal_value": (
                    (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                ),
            },
        )

    return StrategyInputBundle(
        trade_date=trade_date,
        strategy_id=strategy_id,
        run_id=run_id,
        instruments=instruments,
        market_data=pl.DataFrame(market_rows),
        signal_values=pl.DataFrame(signal_rows),
        benchmark_close=benchmark_close,
    )
