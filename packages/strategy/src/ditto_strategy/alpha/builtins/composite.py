"""
CompositeDecisionStage -- 多信号聚合 Stage.

基于业界 Score Fusion + Rank-Based Normalization，将多个 DecisionStage
的输出合并为统一评分。
"""

from __future__ import annotations

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


def _extract_aligned_scores(
    frame: pl.DataFrame,
    result: pl.DataFrame,
) -> pl.Series:
    """
    从子 stage 输出中提取评分，按 ``instrument_id`` 对齐回原始 frame。

    子 stage 可能过滤或重排行，因此必须按 key join 而非位置对齐。
    缺失的 instrument 以 0.0 填充（表示该子 stage 未对其评分）。

    Args:
        frame: 原始输入 frame（对齐基准）。
        result: 子 stage 返回的结果 frame。

    Returns:
        与原始 frame 等长、按 instrument_id 对齐的 score Series。

    """
    # 确定子 stage 产出的评分列
    if FrameCol.SCORE in result.columns:
        score_col = FrameCol.SCORE
    elif FrameCol.SIGNAL in result.columns:
        score_col = FrameCol.SIGNAL
    else:
        return pl.Series(FrameCol.SCORE, [0.0] * frame.height, dtype=pl.Float64)

    # 按 instrument_id left join 回原始 frame，缺失填 0.0
    aligned = (
        frame.select(FrameCol.INSTRUMENT_ID)
        .join(
            result.select(
                FrameCol.INSTRUMENT_ID,
                pl.col(score_col).alias(FrameCol.SCORE),
            ),
            on=FrameCol.INSTRUMENT_ID,
            how="left",
        )
        .fill_null(0.0)
    )
    return aligned[FrameCol.SCORE]


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

        # ---- 独立执行各子 stage ----
        score_columns: list[pl.Series] = []
        for stage in self.stages:
            result = stage.process(frame.clone(), context)
            score_columns.append(_extract_aligned_scores(frame, result))

        # ---- Rank 标准化 ----
        ranked_columns = [_rank_normalize(col) for col in score_columns]

        # ---- 权重归一化 ----
        normalized_weights = self._normalize_weights()

        # ---- 加权求和 ----
        composite_score: pl.Series = pl.Series(
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
