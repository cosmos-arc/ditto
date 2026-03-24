"""
StrategyInputAssembler — 从 Slice 组装 StrategyInputBundle.

从 EngineLoop._build_input_bundle() 提取为独立类，可复用于
BACKTEST / RESEARCH / RECOMMENDATION 等模式。

职责:
  - 将 Slice 中的 MarketSnapshot 转换为 market_data DataFrame
  - 计算默认动量信号 (close / prev_close - 1)
  - 组装完整的 StrategyInputBundle
"""

from __future__ import annotations

import polars as pl
from ditto_core.backtest.data_feed import Slice
from ditto_core.strategy.pipeline import StrategyInputBundle

__all__ = ["StrategyInputAssembler"]


class StrategyInputAssembler:
    """
    从 Slice 组装 StrategyInputBundle.

    封装 strategy_id / run_id / parameters 等策略级别配置，
    ``assemble()`` 接收日期级别的 Slice 数据并产出完整的 bundle。

    可复用于 BACKTEST / RESEARCH / RECOMMENDATION 等模式。

    Parameters
    ----------
        strategy_id: 策略 ID
        run_id: 运行 ID
        parameters: 参数覆盖

    """

    def __init__(
        self,
        strategy_id: str = "default",
        run_id: str = "",
        parameters: dict[str, object] | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._run_id = run_id
        self._parameters = parameters or {}

    @property
    def strategy_id(self) -> str:
        """策略 ID。"""
        return self._strategy_id

    @property
    def run_id(self) -> str:
        """运行 ID。"""
        return self._run_id

    @property
    def parameters(self) -> dict[str, object]:
        """参数覆盖。"""
        return dict(self._parameters)

    def assemble(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        valid_until: str | None = None,
    ) -> StrategyInputBundle:
        """
        从 Slice 构建 StrategyInputBundle.

        从 bars 中提取 market_data (OHLCV) 和 signal_values
        (动量信号: close / prev_close - 1)。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            slice_: 当日市场数据切片
            valid_until: 信号有效期截止日期 (YYYY-MM-DD)，若早于
                trade_date 则视为过期，bundle 中 signal_values 为 None

        Returns:
            包含标的列表、市场数据、信号值的 StrategyInputBundle

        """
        instrument_ids = list(slice_.bars.keys())
        instruments = pl.DataFrame({"instrument_id": instrument_ids})

        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []

        for iid, bar in slice_.bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                }
            )

        # 信号过期检查：valid_until < trade_date 时信号无效
        signals_expired = valid_until is not None and valid_until < trade_date

        return StrategyInputBundle(
            trade_date=trade_date,
            strategy_id=self._strategy_id,
            run_id=self._run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=None if signals_expired else pl.DataFrame(signal_rows),
            parameters=self._parameters,
            benchmark_close=slice_.benchmark_close,
        )
