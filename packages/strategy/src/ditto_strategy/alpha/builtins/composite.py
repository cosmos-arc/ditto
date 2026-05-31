"""
CompositeDecisionStage -- 多信号聚合 Stage.

基于业界 Score Fusion + Rank-Based Normalization，将多个 DecisionStage
的输出合并为统一评分。
"""

from dataclasses import dataclass
from enum import StrEnum

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol
from ditto_strategy.alpha.protocols import DecisionStage

__all__ = ["CompositeDecisionStage", "FusionMethod"]

# 近零阈值，用于权重归一化退化为等权判断。
_EPS = 1e-10


class FusionMethod(StrEnum):
    """信号聚合方法。"""

    RANK_WEIGHTED = "rank_weighted"  # Rank 标准化后加权（默认）
    EQUAL = "equal"  # 等权（Rank 后简单平均）


def _extract_score_column(frame: pl.DataFrame) -> pl.Series:
    """
    从子 stage 输出中提取评分列。

    优先使用 ``score`` 列，fallback 到 ``signal_value``，
    都不存在则用 0.0 填充。
    """
    if FrameCol.SCORE in frame.columns:
        return frame[FrameCol.SCORE]
    if FrameCol.SIGNAL in frame.columns:
        return frame[FrameCol.SIGNAL]
    return pl.Series(FrameCol.SCORE, [0.0] * frame.height, dtype=pl.Float64)


def _rank_normalize(series: pl.Series) -> pl.Series:
    """将一列评分 rank 标准化到 [0, 1]。"""
    count = series.count()
    if count == 0:
        return series
    ranked = series.rank(method="average")
    return ranked / count


@dataclass(frozen=True)
class CompositeDecisionStage:
    """
    多信号聚合 Stage，将多个 DecisionStage 的输出合并为统一评分。

    Attributes:
        stages: 子 stage 元组。
        weights: 每个子 stage 的权重，长度须与 stages 一致。
        method: 聚合方法，默认 rank_weighted。

    """

    stages: tuple[DecisionStage, ...]
    weights: tuple[float, ...]
    method: FusionMethod = FusionMethod.RANK_WEIGHTED

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        对每个子 stage 独立执行后 rank 标准化、加权求和，输出统一 score。

        Args:
            frame: 输入 DecisionFrame。
            context: 策略上下文。

        Returns:
            合并后的 DecisionFrame，score 列为加权 rank 融合评分。

        """
        # 空 frame 直接返回
        if frame.is_empty():
            return frame

        # 单个 stage 直接返回其输出
        if len(self.stages) == 1:
            return self.stages[0].process(frame, context)

        # ---- 并行独立执行各子 stage ----
        score_columns: list[pl.Series] = []
        for stage in self.stages:
            result = stage.process(frame.clone(), context)
            score_columns.append(_extract_score_column(result))

        # ---- Rank 标准化 ----
        ranked_columns = [_rank_normalize(col) for col in score_columns]

        # ---- 权重归一化 ----
        normalized_weights = self._normalize_weights()

        # ---- 加权求和 ----
        composite_score = pl.Series(
            FrameCol.SCORE,
            [0.0] * frame.height,
            dtype=pl.Float64,
        )
        for rank_col, w in zip(ranked_columns, normalized_weights, strict=True):
            composite_score = composite_score + rank_col * w

        return frame.with_columns(composite_score.alias(FrameCol.SCORE))

    def _normalize_weights(self) -> tuple[float, ...]:
        """L1 范数权重归一化，全零或近零退化等权。"""
        if self.method == FusionMethod.EQUAL:
            n = len(self.stages)
            return tuple(1.0 / n for _ in range(n))

        total = sum(abs(w) for w in self.weights)
        if total < _EPS:
            # 全零退化等权
            n = len(self.stages)
            return tuple(1.0 / n for _ in range(n))
        return tuple(abs(w) / total for w in self.weights)
