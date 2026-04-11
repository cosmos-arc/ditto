"""SignalStage -- 将预计算信号值 attach 到 DecisionFrame."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.frame import FrameCol, validate_frame

__all__ = ["SignalStage"]


@dataclass(frozen=True)
class SignalStage:
    """
    Signal Stage -- 将预计算信号值 attach 到 DecisionFrame。

    模式 1: source_column 不为 None -- 从 frame 中已有列提取并重命名为
            signal_column。
    模式 2: source_column=None -- signal_column 已在 frame 中则原样返回；
            不在则填充 null。

    Attributes:
        signal_column: 输出列名。
        source_column: 输入列名。None 表示 signal_column 已在 frame 中。

    """

    signal_column: str = "signal_value"
    source_column: str | None = None

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """处理信号列。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        if self.source_column is not None:
            return frame.with_columns(
                pl.col(self.source_column).alias(self.signal_column),
            )
        if self.signal_column not in frame.columns:
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(self.signal_column),
            )
        return frame
