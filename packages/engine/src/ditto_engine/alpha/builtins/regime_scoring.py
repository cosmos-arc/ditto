"""
RegimeScoringStep -- Regime 评分 DecisionStage.

在 Allocate 之后、RegimeAware 之前插入。
委托 RegimeScoreEngine.score(frame) 获取 RegimeResult，
将 score / label / position_ratio 写为 scalar 列。
空 frame 原样返回。
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_engine.alpha.builtins.regime import RegimeConfig, RegimeScoreEngine
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.protocols import DecisionFrame

__all__ = ["RegimeScoringStep"]


@dataclass(frozen=True)
class RegimeScoringStep:
    """
    Regime 评分 Step — 在 Allocate 之后、RegimeAware 之前插入.

    委托 RegimeScoreEngine.score(frame) 获取 RegimeResult，
    将 score / label / position_ratio 写为 scalar 列。
    空 frame 原样返回。

    Attributes:
        config: Regime 评分引擎配置。

    """

    config: RegimeConfig

    def process(
        self,
        frame: DecisionFrame,
        context: StrategyContext,
    ) -> DecisionFrame:
        """计算 regime 评分并附加到 frame."""
        if frame.is_empty():
            return frame

        engine = RegimeScoreEngine(self.config)
        result = engine.score(frame)

        return frame.with_columns(
            [
                pl.lit(result.score).alias("regime_score"),
                pl.lit(result.label.value).alias("regime_label"),
                pl.lit(result.position_ratio).alias("position_ratio"),
            ],
        )
