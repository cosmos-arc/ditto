"""Tests for portfolio allocation module."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.portfolio.allocation import (
    AllocationStage,
    EqualWeightAllocator,
    InverseVolAllocator,
    ScoreWeightAllocator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def five_instrument_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 4, 5],
        }
    )


@pytest.fixture
def single_instrument_frame() -> pl.DataFrame:
    return pl.DataFrame({"instrument_id": [1]})


@pytest.fixture
def empty_frame() -> pl.DataFrame:
    return pl.DataFrame({"instrument_id": []})


# ---------------------------------------------------------------------------
# EqualWeightAllocator
# ---------------------------------------------------------------------------


class TestEqualWeightAllocator:
    def test_empty_frame(self, empty_frame: pl.DataFrame) -> None:
        allocator = EqualWeightAllocator()
        result = allocator.allocate(empty_frame)

        assert result.height == 0
        assert "weight" in result.columns

    def test_normal_equal_weight(self, five_instrument_frame: pl.DataFrame) -> None:
        allocator = EqualWeightAllocator()
        result = allocator.allocate(five_instrument_frame)

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.2) for w in weights)
        assert "weight" in result.columns
        assert result.height == 5

    def test_with_cash_target(self, five_instrument_frame: pl.DataFrame) -> None:
        allocator = EqualWeightAllocator(cash_target=0.1)
        result = allocator.allocate(five_instrument_frame)

        weights = result["weight"].to_list()
        expected = 0.9 / 5.0
        assert all(w == pytest.approx(expected) for w in weights)
        assert result.height == 5

    def test_single_instrument(self, single_instrument_frame: pl.DataFrame) -> None:
        allocator = EqualWeightAllocator()
        result = allocator.allocate(single_instrument_frame)

        weights = result["weight"].to_list()
        assert weights[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ScoreWeightAllocator
# ---------------------------------------------------------------------------


class TestScoreWeightAllocator:
    def test_normal_allocation(self, five_instrument_frame: pl.DataFrame) -> None:
        frame = five_instrument_frame.with_columns(
            score=pl.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        )
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert result.height == 5
        # Sum of weights should be 1.0
        assert sum(weights) == pytest.approx(1.0)
        # Higher score -> higher weight
        assert weights[4] > weights[3] > weights[2] > weights[1] > weights[0]

    def test_all_null_scores(self, five_instrument_frame: pl.DataFrame) -> None:
        frame = five_instrument_frame.with_columns(
            score=pl.Series([None, None, None, None, None], dtype=pl.Float64)
        )
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.0) for w in weights)

    def test_single_instrument(self, single_instrument_frame: pl.DataFrame) -> None:
        frame = single_instrument_frame.with_columns(score=pl.lit(42.0))
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert weights[0] == pytest.approx(1.0)

    def test_min_weight(self, five_instrument_frame: pl.DataFrame) -> None:
        # Scores heavily skewed: one very high, others low but distinct
        frame = five_instrument_frame.with_columns(
            score=pl.Series([1.0, 2.0, 3.0, 4.0, 96.0])
        )
        allocator = ScoreWeightAllocator(score_column="score", min_weight=0.05)
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        # Instrument with lowest score gets weight 0 (shifted to 0)
        assert weights[0] == pytest.approx(0.0)
        # Others with positive but small weights should be >= min_weight
        for w in weights[1:]:
            assert w == pytest.approx(0.05) or w > 0.05

    def test_negative_scores(self, five_instrument_frame: pl.DataFrame) -> None:
        # Mix of positive and negative scores
        frame = five_instrument_frame.with_columns(
            score=pl.Series([-10.0, -5.0, 0.0, 5.0, 10.0])
        )
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        # Sum of weights should be 1.0
        assert sum(weights) == pytest.approx(1.0)
        # All weights should be positive
        assert all(w >= 0.0 for w in weights)
        # Higher score -> higher weight
        assert weights[4] > weights[3] > weights[2] > weights[1] > weights[0]


# ---------------------------------------------------------------------------
# EqualWeightAllocator — Boundary
# ---------------------------------------------------------------------------


class TestEqualWeightBoundary:
    def test_cash_target_zero_full_invest(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """cash_target=0 → sum of weights = 1.0 (全仓)。"""
        allocator = EqualWeightAllocator(cash_target=0.0)
        result = allocator.allocate(five_instrument_frame)

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(1.0)
        assert all(w == pytest.approx(0.2) for w in weights)

    def test_cash_target_one_all_zero(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """cash_target=1.0 → all weights = 0.0 (全现金)。"""
        allocator = EqualWeightAllocator(cash_target=1.0)
        result = allocator.allocate(five_instrument_frame)

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.0) for w in weights)
        assert result.height == 5

    def test_cash_target_negative_invests_more(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """cash_target=-0.1 → sum of weights = 1.1 (加杠杆 110%)。"""
        allocator = EqualWeightAllocator(cash_target=-0.1)
        result = allocator.allocate(five_instrument_frame)

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(1.1)
        assert all(w == pytest.approx(0.22) for w in weights)

    def test_large_instrument_count(self) -> None:
        """100 个标的 → 每个权重 = 0.01。"""
        ids = list(range(100))
        frame = pl.DataFrame({"instrument_id": ids})
        allocator = EqualWeightAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert result.height == 100
        assert all(w == pytest.approx(0.01) for w in weights)
        assert sum(weights) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ScoreWeightAllocator — Boundary
# ---------------------------------------------------------------------------


class TestScoreWeightBoundary:
    def test_empty_frame(self, empty_frame: pl.DataFrame) -> None:
        """空 frame → 返回空 frame + weight 列。"""
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(empty_frame)

        assert result.height == 0
        assert "weight" in result.columns

    def test_all_same_scores_equal_weight(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """所有 score 相同 → 非空行等权分配。"""
        frame = five_instrument_frame.with_columns(score=pl.lit(42.0))
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.2) for w in weights)
        assert sum(weights) == pytest.approx(1.0)

    def test_mix_null_and_valid_scores(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """部分 null score → null 得 weight=0，其余按比例分配。

        注意：最低有效 score 映射到 proportional=0，weight 也为 0。
        """
        frame = five_instrument_frame.with_columns(
            score=pl.Series([None, 10.0, 20.0, None, 30.0], dtype=pl.Float64),
        )
        allocator = ScoreWeightAllocator(score_column="score")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        # Null-score rows should have weight=0
        assert weights[0] == pytest.approx(0.0)
        assert weights[3] == pytest.approx(0.0)
        # Minimum valid score maps to 0 after shift → weight=0
        assert weights[1] == pytest.approx(0.0)
        # Remaining valid rows should have positive weights summing to 1.0
        assert sum(weights) == pytest.approx(1.0)
        assert weights[4] > weights[2] > 0.0

    def test_cash_target_reduces_total(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """cash_target=0.2 → sum of weights = 0.8。"""
        frame = five_instrument_frame.with_columns(
            score=pl.Series([10.0, 20.0, 30.0, 40.0, 50.0]),
        )
        allocator = ScoreWeightAllocator(score_column="score", cash_target=0.2)
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(0.8)

    def test_min_weight_larger_than_computed(
        self, five_instrument_frame: pl.DataFrame
    ) -> None:
        """min_weight=0.5，3 个有效标的 → 低分标的被 floor 提升。

        注意：最低有效 score 映射到 proportional=0，weight 也为 0，
        min_weight 仅对 weight > 0 的行生效。
        """
        # 3 valid scores: 1, 2, 100. Score=1 maps to proportional=0 → weight=0.
        # Score=2 maps to proportional=1/99 → small weight, floored to 0.5.
        # Score=100 maps to proportional=1 → large weight, stays above 0.5.
        frame = five_instrument_frame.with_columns(
            score=pl.Series([1.0, 2.0, 100.0, None, None], dtype=pl.Float64),
        )
        allocator = ScoreWeightAllocator(score_column="score", min_weight=0.5)
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        # Null-score rows remain 0
        assert weights[3] == pytest.approx(0.0)
        assert weights[4] == pytest.approx(0.0)
        # Minimum valid score maps to proportional=0 → weight=0, floor skipped
        assert weights[0] == pytest.approx(0.0)
        # Second-lowest gets a small proportional weight, floored to min_weight
        assert weights[1] == pytest.approx(0.5)
        # Highest score gets a large weight, above min_weight
        assert weights[2] > 0.5


# ---------------------------------------------------------------------------
# AllocationStage
# ---------------------------------------------------------------------------


class TestAllocationStage:
    def test_adapter_forwards_to_allocator(
        self,
        five_instrument_frame: pl.DataFrame,
    ) -> None:
        allocator = EqualWeightAllocator()
        stage = AllocationStage(allocator=allocator)
        # AllocationStage.process accepts context but doesn't use it
        result = stage.process(five_instrument_frame, object())

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.2) for w in weights)


# ---------------------------------------------------------------------------
# InverseVolAllocator
# ---------------------------------------------------------------------------


class TestInverseVolAllocator:
    def test_normal_allocation(self, five_instrument_frame: pl.DataFrame) -> None:
        frame = five_instrument_frame.with_columns(
            volatility=pl.Series([0.1, 0.2, 0.3, 0.4, 0.5]),
        )
        allocator = InverseVolAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert result.height == 5
        assert "weight" in result.columns
        assert sum(weights) == pytest.approx(1.0)
        # Lower vol -> higher weight
        assert weights[0] > weights[1] > weights[2] > weights[3] > weights[4]

    def test_weights_are_inverse_vol(self, five_instrument_frame: pl.DataFrame) -> None:
        frame = five_instrument_frame.with_columns(
            volatility=pl.Series([0.1, 0.2, 0.3, 0.4, 0.5]),
        )
        allocator = InverseVolAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        # Manual check: inv_vol = [10, 5, 3.333, 2.5, 2], sum = 22.833
        # w[0] = 10 / 22.833 ≈ 0.4379
        inv_vols = [1.0 / v for v in [0.1, 0.2, 0.3, 0.4, 0.5]]
        inv_sum = sum(inv_vols)
        expected = [iv / inv_sum for iv in inv_vols]
        for w, e in zip(weights, expected, strict=True):
            assert w == pytest.approx(e, rel=1e-6)

    def test_all_zero_volatility(self, five_instrument_frame: pl.DataFrame) -> None:
        """全零波动率 → 等权分配。"""
        frame = five_instrument_frame.with_columns(
            volatility=pl.Series([0.0, 0.0, 0.0, 0.0, 0.0]),
        )
        allocator = InverseVolAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert all(w == pytest.approx(0.2) for w in weights)
        assert sum(weights) == pytest.approx(1.0)

    def test_partial_zero_volatility(self, five_instrument_frame: pl.DataFrame) -> None:
        """部分零波动率 → 零波动率标的权重为 0。"""
        frame = five_instrument_frame.with_columns(
            volatility=pl.Series([0.0, 0.0, 0.3, 0.4, 0.5]),
        )
        allocator = InverseVolAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert weights[0] == pytest.approx(0.0)
        assert weights[1] == pytest.approx(0.0)
        # Remaining 3 instruments should share the full weight
        assert sum(weights) == pytest.approx(1.0)
        # Non-zero vol instruments: weights should be inversely proportional
        inv_vols = [1.0 / v for v in [0.3, 0.4, 0.5]]
        inv_sum = sum(inv_vols)
        expected = [iv / inv_sum for iv in inv_vols]
        for w, e in zip(weights[2:], expected, strict=True):
            assert w == pytest.approx(e, rel=1e-6)

    def test_single_instrument(self, single_instrument_frame: pl.DataFrame) -> None:
        """单标的 → 权重 = (1 - cash_target)。"""
        frame = single_instrument_frame.with_columns(volatility=pl.lit(0.15))
        allocator = InverseVolAllocator()
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert weights[0] == pytest.approx(1.0)

    def test_single_instrument_with_cash_target(
        self, single_instrument_frame: pl.DataFrame
    ) -> None:
        """单标的 + cash_target → 权重 = (1 - cash_target)。"""
        frame = single_instrument_frame.with_columns(volatility=pl.lit(0.15))
        allocator = InverseVolAllocator(cash_target=0.1)
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert weights[0] == pytest.approx(0.9)

    def test_empty_frame(self, empty_frame: pl.DataFrame) -> None:
        """空 frame → 返回空 frame + weight 列。"""
        allocator = InverseVolAllocator()
        result = allocator.allocate(empty_frame)

        assert result.height == 0
        assert "weight" in result.columns

    def test_cash_target(self, five_instrument_frame: pl.DataFrame) -> None:
        """cash_target 控制总权重。"""
        frame = five_instrument_frame.with_columns(
            volatility=pl.Series([0.1, 0.2, 0.3, 0.4, 0.5]),
        )
        allocator = InverseVolAllocator(cash_target=0.2)
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(0.8)
        # Proportions should be the same as no cash_target
        assert weights[0] > weights[1] > weights[2] > weights[3] > weights[4]

    def test_custom_vol_column(self, five_instrument_frame: pl.DataFrame) -> None:
        """支持自定义波动率列名。"""
        frame = five_instrument_frame.with_columns(
            custom_vol=pl.Series([0.1, 0.2, 0.3, 0.4, 0.5]),
        )
        allocator = InverseVolAllocator(vol_column="custom_vol")
        result = allocator.allocate(frame)

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(1.0)
        assert weights[0] > weights[1] > weights[2] > weights[3] > weights[4]

    def test_frozen_dataclass(self) -> None:
        """InverseVolAllocator 应为 frozen dataclass。"""
        allocator = InverseVolAllocator()
        with pytest.raises(AttributeError):
            allocator.vol_column = "custom"  # type: ignore[misc]
