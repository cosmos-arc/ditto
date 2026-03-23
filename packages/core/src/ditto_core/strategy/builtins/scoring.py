"""ScoringStage -- 将 signal_value 转换为 score."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import polars as pl

from ditto_core.strategy.context import StrategyContext

__all__ = ["ScoringMethod", "ScoringStage"]


class ScoringMethod(StrEnum):
    """评分方法。"""

    RAW = "raw"  # 直接使用 signal_value
    RANK = "rank"  # 百分位排名 (0-1)
    ZSCORE = "zscore"  # Z-score 标准化


@dataclass(frozen=True)
class ScoringStage:
    """
    Scoring Stage -- 将 signal_value 转换为 score。

    Attributes:
        method: 评分方法。
        ascending: True 表示 signal 值小的得分高（如波动率）。
        output_column: 输出列名。
        input_column: 输入列名。

    """

    method: ScoringMethod = ScoringMethod.RANK
    ascending: bool = False
    output_column: str = "score"
    input_column: str = "signal_value"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """根据 method 转换 signal 为 score。"""
        if self.input_column not in frame.columns:
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(self.output_column),
            )

        col = pl.col(self.input_column)

        if self.method == ScoringMethod.RAW:
            return frame.with_columns(col.alias(self.output_column))

        if self.method == ScoringMethod.RANK:
            rank_expr = col.rank(method="average", descending=not self.ascending)
            count_expr = col.count()
            return frame.with_columns(
                (rank_expr / count_expr).alias(self.output_column),
            )

        # ScoringMethod.ZSCORE
        mean = col.mean()
        std = col.std()
        return frame.with_columns(
            pl.when(std == 0)
            .then(pl.lit(0.0))
            .otherwise((col - mean) / std)
            .alias(self.output_column),
        )
