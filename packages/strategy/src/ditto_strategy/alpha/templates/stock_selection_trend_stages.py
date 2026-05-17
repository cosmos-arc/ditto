"""stock_selection_trend Stage 实现 -- MultiFactorSignalStage."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.context import StrategyContext

__all__ = ["MultiFactorSignalStage"]


@dataclass(frozen=True)
class MultiFactorSignalStage:
    """
    多因子加权信号 Stage -- 从多个因子列计算加权综合信号.

    使用 rank-based 标准化: 对每个因子列独立做百分位排名 (0-1)，
    然后加权求和: score = sum(w_i * rank_i) / sum(w_i)

    Attributes:
        signal_factors: 因子列名列表。
        signal_weights: 因子权重列表。
        output_column: 输出列名。

    """

    signal_factors: tuple[str, ...] = ("signal_value",)
    signal_weights: tuple[float, ...] = (1.0,)
    output_column: str = "signal_value"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        计算多因子加权信号并写入 output_column.

        边界处理:
        - 空 frame 或无因子 → 填充 0.0
        - 缺失因子列 → rank 视为 0.0
        """
        if frame.is_empty() or not self.signal_factors:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        weight_sum = sum(self.signal_weights)
        if weight_sum == 0.0:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        result = frame
        weighted_sum = pl.lit(0.0)

        for factor_name, weight in zip(
            self.signal_factors,
            self.signal_weights,
            strict=True,
        ):
            if factor_name not in frame.columns:
                # Missing factor: rank = 0.0 for all instruments
                continue

            col = pl.col(factor_name)
            n = frame.height
            rank_expr = col.rank(method="average", descending=False) / n
            weighted_sum = weighted_sum + pl.lit(weight) * rank_expr

        return result.with_columns(
            (weighted_sum / pl.lit(weight_sum)).alias(self.output_column),
        )
