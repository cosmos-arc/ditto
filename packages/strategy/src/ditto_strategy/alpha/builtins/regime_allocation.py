"""
RegimeAwareAllocationStage -- Regime 感知仓位缩放 DecisionStage.

根据 regime_score 和 regime_label 对权重进行缩放:
- BEAR + score < bear_cutoff → 完全空仓 (weight = 0)
- 其他 → weight *= position_ratio
- 缺失 regime 列 → 不缩放
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.builtins.regime import RegimeLabel
from ditto_strategy.alpha.context import StrategyContext

__all__ = ["RegimeAwareAllocationStage"]


@dataclass(frozen=True)
class RegimeAwareAllocationStage:
    """
    Regime 感知仓位缩放 Stage.

    读取 frame 中的 regime_score / regime_label 列，根据市场状态
    缩放已有权重:
    - BEAR + score < bear_cutoff → weight = 0 (完全空仓)
    - 其他 → weight *= position_ratio

    Attributes:
        regime_score_column: regime 评分列名。
        regime_label_column: regime 标签列名。
        bear_cutoff: BEAR 状态下完全空仓的分数阈值。
        default_regime: 缺失 regime 列时的默认标签。

    """

    regime_score_column: str = "regime_score"
    regime_label_column: str = "regime_label"
    bear_cutoff: float = 20.0
    default_regime: RegimeLabel = RegimeLabel.NEUTRAL

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """根据 regime 缩放权重."""
        if frame.is_empty():
            return frame

        # 缺失 regime 列 → 不缩放
        if (
            self.regime_score_column not in frame.columns
            or self.regime_label_column not in frame.columns
            or "weight" not in frame.columns
            or "position_ratio" not in frame.columns
        ):
            return frame

        score_col = pl.col(self.regime_score_column)
        label_col = pl.col(self.regime_label_column)
        position_ratio_col = pl.col("position_ratio")
        weight_col = pl.col("weight")

        # null regime → 保持原始 weight
        # BEAR + score < cutoff → weight = 0
        # 其他 → weight *= position_ratio
        is_null = (
            score_col.is_null() | label_col.is_null() | position_ratio_col.is_null()
        )

        scaled_weight = weight_col * position_ratio_col

        new_weight = (
            pl.when(is_null)
            .then(weight_col)
            .when(
                (label_col == RegimeLabel.BEAR) & (score_col < self.bear_cutoff),
            )
            .then(pl.lit(0.0))
            .otherwise(scaled_weight)
        )

        return frame.with_columns(new_weight.alias("weight"))
