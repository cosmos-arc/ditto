"""Tests for CompositeDecisionStage -- 多信号聚合 Stage.

Covers rank-based score fusion, weight normalization, edge cases
(fewer than 2 stages, empty frame, zero weights) with AAA pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest
from ditto_strategy.alpha.builtins.composite import (
    CompositeDecisionStage,
    FusionMethod,
)
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.protocols import DecisionStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ScoringStub:
    """测试用: 给每个 instrument 附一个固定 score。"""

    scores: dict[int, float]

    def process(self, frame: pl.DataFrame, _context: StrategyContext) -> pl.DataFrame:
        return frame.with_columns(
            pl.col("instrument_id")
            .map_elements(
                lambda x: self.scores.get(x, 0.0),
                return_dtype=pl.Float64,
            )
            .alias("score"),
        )


@dataclass(frozen=True)
class _SignalValueStub:
    """测试用: 给每个 instrument 附一个 signal_value（不产出 score 列）。"""

    signals: dict[int, float]

    def process(self, frame: pl.DataFrame, _context: StrategyContext) -> pl.DataFrame:
        return frame.with_columns(
            pl.col("instrument_id")
            .map_elements(
                lambda x: self.signals.get(x, 0.0),
                return_dtype=pl.Float64,
            )
            .alias("signal_value"),
        )


@pytest.fixture
def ctx() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def three_instruments() -> pl.DataFrame:
    """3-row DecisionFrame with instrument_id."""
    return pl.DataFrame({"instrument_id": [1, 2, 3]})


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestCompositeDecisionStage:
    """CompositeDecisionStage 测试套件。"""

    def test_composite_two_stages_weighted_merge(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """2 个 stage 加权合并，验证 composite score 排序正确。

        Stage A (w=0.7): id=1 -> 0.9, id=2 -> 0.1, id=3 -> 0.5
        Stage B (w=0.3): id=1 -> 0.1, id=2 -> 0.9, id=3 -> 0.5

        rank normalization 后各自 [0.333, 1.0, 0.667]
        composite = 0.7*rank_A + 0.3*rank_B
        - id=1: 0.7*1.0  + 0.3*0.333 ≈ 0.8
        - id=2: 0.7*0.333+ 0.3*1.0  ≈ 0.533
        - id=3: 0.7*0.667+ 0.3*0.667 = 0.667
        """
        stage_a = _ScoringStub(scores={1: 0.9, 2: 0.1, 3: 0.5})
        stage_b = _ScoringStub(scores={1: 0.1, 2: 0.9, 3: 0.5})

        composite = CompositeDecisionStage(
            stages=(stage_a, stage_b),
            weights=(0.7, 0.3),
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        # id=1 应该得分最高（stage A 的偏好占主导）
        assert scores[0] > scores[1]
        # id=3 排名相同，composite score 相等
        assert abs(scores[2] - (2.0 / 3.0)) < 1e-6

    def test_composite_weight_normalization(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """权重 [2, 1] 归一化为 [0.667, 0.333]。

        两个 stage 输出完全不同，验证权重效果。
        """
        stage_a = _ScoringStub(scores={1: 1.0, 2: 0.0, 3: 0.5})
        stage_b = _ScoringStub(scores={1: 0.0, 2: 1.0, 3: 0.5})

        composite = CompositeDecisionStage(
            stages=(stage_a, stage_b),
            weights=(2.0, 1.0),
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        # id=1 rank=1.0, id=2 rank=0.333, id=3 rank=0.667 for stage_a
        # id=1 rank=0.333, id=2 rank=1.0, id=3 rank=0.667 for stage_b
        # w_a = 2/3, w_b = 1/3
        # id=1: 2/3*1.0 + 1/3*0.333 ≈ 0.778
        # id=2: 2/3*0.333 + 1/3*1.0 ≈ 0.556
        # id=3: 2/3*0.667 + 1/3*0.667 = 0.667
        expected_id1 = (2.0 / 3.0) * 1.0 + (1.0 / 3.0) * (1.0 / 3.0)
        assert abs(scores[0] - expected_id1) < 1e-6
        # id=1 依然高于 id=2（因为 stage_a 权重更大）
        assert scores[0] > scores[1]

    def test_composite_all_zero_weights_falls_back_to_equal(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """全零权重退化为等权合并。"""
        stage_a = _ScoringStub(scores={1: 1.0, 2: 0.0, 3: 0.5})
        stage_b = _ScoringStub(scores={1: 0.0, 2: 1.0, 3: 0.5})

        composite = CompositeDecisionStage(
            stages=(stage_a, stage_b),
            weights=(0.0, 0.0),
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        # 等权: id=3 两个 stage rank 都是 0.667 → composite = 0.667
        assert abs(scores[2] - (2.0 / 3.0)) < 1e-6
        # id=1 和 id=2 互为镜像，等权下应该相等
        assert abs(scores[0] - scores[1]) < 1e-6

    def test_composite_empty_frame(
        self,
        ctx: StrategyContext,
    ) -> None:
        """空 frame 直接返回，不处理。"""
        empty = pl.DataFrame({"instrument_id": []})
        stage = _ScoringStub(scores={})
        composite = CompositeDecisionStage(
            stages=(stage,),
            weights=(1.0,),
        )
        result = composite.process(empty, ctx)
        assert result.is_empty()
        assert "instrument_id" in result.columns

    def test_composite_isinstance_decision_stage(
        self,
    ) -> None:
        """CompositeDecisionStage 满足 DecisionStage Protocol。"""
        stage_a = _ScoringStub(scores={})
        composite = CompositeDecisionStage(
            stages=(stage_a,),
            weights=(1.0,),
        )
        assert isinstance(composite, DecisionStage)

    def test_composite_single_stage_pass_through(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """单个 stage 直接返回其输出，无需合并。"""
        stage = _ScoringStub(scores={1: 0.8, 2: 0.4, 3: 0.6})
        composite = CompositeDecisionStage(
            stages=(stage,),
            weights=(1.0,),
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        assert scores == [0.8, 0.4, 0.6]

    def test_composite_equal_method(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """FusionMethod.EQUAL 行为正确 — 等价于全等权。"""
        stage_a = _ScoringStub(scores={1: 1.0, 2: 0.0, 3: 0.5})
        stage_b = _ScoringStub(scores={1: 0.0, 2: 1.0, 3: 0.5})

        composite = CompositeDecisionStage(
            stages=(stage_a, stage_b),
            weights=(99.0, 1.0),  # 权重应被忽略
            method=FusionMethod.EQUAL,
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        # id=1 和 id=2 互为镜像，等权下 score 应相等
        assert abs(scores[0] - scores[1]) < 1e-6
        # id=3 恒为中间 rank
        assert abs(scores[2] - (2.0 / 3.0)) < 1e-6

    def test_composite_no_score_column_falls_back_to_signal_value(
        self,
        three_instruments: pl.DataFrame,
        ctx: StrategyContext,
    ) -> None:
        """子 stage 无 score 列时使用 signal_value 作为 fallback。"""
        stage_a = _ScoringStub(scores={1: 1.0, 2: 0.0, 3: 0.5})
        stage_b = _SignalValueStub(signals={1: 0.0, 2: 1.0, 3: 0.5})

        composite = CompositeDecisionStage(
            stages=(stage_a, stage_b),
            weights=(1.0, 1.0),
        )
        result = composite.process(three_instruments, ctx)

        scores = result["score"].to_list()
        # stage_b 没有 score 列，fallback 到 signal_value
        # 两个 stage rank 结果镜像，等权下 id=1 和 id=2 score 相等
        assert abs(scores[0] - scores[1]) < 1e-6
        assert "score" in result.columns
