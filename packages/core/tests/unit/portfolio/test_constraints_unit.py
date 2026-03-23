"""Tests for portfolio constraints module."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_core.portfolio.constraints import (
    ConstraintChecker,
    ConstraintStage,
    MaxPositionsConstraint,
    MaxWeightConstraint,
    MinWeightConstraint,
)
from ditto_core.strategy.protocols import DecisionStage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def weighted_frame() -> pl.DataFrame:
    """5 instruments with pre-assigned weights."""
    return pl.DataFrame(
        {
            "instrument_id": [
                "159915.SZ",
                "510300.SH",
                "159949.SZ",
                "510050.SH",
                "159919.SZ",
            ],
            "weight": [0.30, 0.25, 0.20, 0.15, 0.10],
        }
    )


# ---------------------------------------------------------------------------
# ConstraintChecker
# ---------------------------------------------------------------------------


class TestConstraintChecker:
    def test_no_constraints(self, weighted_frame: pl.DataFrame) -> None:
        checker = ConstraintChecker(constraints=[])
        result = checker.check(weighted_frame)

        weights = result["weight"].to_list()
        original = weighted_frame["weight"].to_list()
        assert all(
            w == pytest.approx(o) for w, o in zip(weights, original, strict=True)
        )

    def test_max_weight_truncates(self, weighted_frame: pl.DataFrame) -> None:
        constraint = MaxWeightConstraint(max_weight=0.20)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            )
        )
        # All weights should be <= 0.20
        for w in weights.values():
            assert w == pytest.approx(0.20, abs=1e-9) or w < 0.20
        # 159915.SZ was 0.30, should be truncated to 0.20
        assert weights["159915.SZ"] == pytest.approx(0.20)
        # 510300.SH was 0.25, should be truncated to 0.20
        assert weights["510300.SH"] == pytest.approx(0.20)
        # 159949.SZ was exactly 0.20, should be unchanged
        assert weights["159949.SZ"] == pytest.approx(0.20)

    def test_min_weight_zeros_small(self, weighted_frame: pl.DataFrame) -> None:
        constraint = MinWeightConstraint(min_weight=0.18)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            )
        )
        # 159919.SZ had weight 0.10 < 0.18, should be zeroed
        assert weights["159919.SZ"] == pytest.approx(0.0)
        # 510050.SH had weight 0.15 < 0.18, should be zeroed
        assert weights["510050.SH"] == pytest.approx(0.0)
        # 159949.SZ had weight 0.20 >= 0.18, should be unchanged
        assert weights["159949.SZ"] == pytest.approx(0.20)
        # 159915.SZ had weight 0.30 >= 0.18, should be unchanged
        assert weights["159915.SZ"] == pytest.approx(0.30)

    def test_max_positions_keeps_top_k(self, weighted_frame: pl.DataFrame) -> None:
        constraint = MaxPositionsConstraint(max_positions=3)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            )
        )
        # Top 3 by weight: 159915.SZ (0.30), 510300.SH (0.25), 159949.SZ (0.20)
        assert weights["159915.SZ"] == pytest.approx(0.30)
        assert weights["510300.SH"] == pytest.approx(0.25)
        assert weights["159949.SZ"] == pytest.approx(0.20)
        # The remaining 2 should be zeroed
        assert weights["510050.SH"] == pytest.approx(0.0)
        assert weights["159919.SZ"] == pytest.approx(0.0)

    def test_priority_ordering(self, weighted_frame: pl.DataFrame) -> None:
        # max_positions (priority=30) first, then max_weight (priority=10)
        # After max_positions: top 3 kept, rest zeroed
        # After max_weight: 0.30 truncated to 0.20
        constraints = [
            MaxWeightConstraint(max_weight=0.20),
            MaxPositionsConstraint(max_positions=3),
        ]
        checker = ConstraintChecker(constraints=constraints)
        result = checker.check(weighted_frame)

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            )
        )
        # 159915.SZ (0.30) was in top 3, then truncated to 0.20
        assert weights["159915.SZ"] == pytest.approx(0.20)
        # 510050.SH and 159919.SZ were removed by max_positions first
        assert weights["510050.SH"] == pytest.approx(0.0)
        assert weights["159919.SZ"] == pytest.approx(0.0)

    def test_reason_codes_accumulation(self, weighted_frame: pl.DataFrame) -> None:
        constraints = [
            MaxWeightConstraint(constraint_id="max_w", max_weight=0.20),
            MaxPositionsConstraint(constraint_id="max_pos", max_positions=3),
        ]
        checker = ConstraintChecker(constraints=constraints)
        result = checker.check(weighted_frame)

        assert "reason_codes" in result.columns
        reasons: list[str] = result["reason_codes"][0]
        # max_weight (priority=10) fires first, then max_positions (priority=30)
        # max_weight: 159915.SZ (0.30>0.20) and 510300.SH (0.25>0.20)
        # max_positions: 510050.SH and 159919.SZ removed
        assert len(reasons) >= 2
        reason_text = " ".join(reasons)
        assert "max_w" in reason_text
        assert "max_pos" in reason_text


# ---------------------------------------------------------------------------
# ConstraintStage
# ---------------------------------------------------------------------------


class TestConstraintStage:
    def test_adapter_forwards_to_checker(
        self,
        weighted_frame: pl.DataFrame,
    ) -> None:
        checker = ConstraintChecker(constraints=[MaxWeightConstraint(max_weight=0.20)])
        stage = ConstraintStage(checker=checker)
        # ConstraintStage.process accepts context but doesn't use it
        result = stage.process(weighted_frame, object())

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            )
        )
        assert weights["159915.SZ"] == pytest.approx(0.20)

        # ConstraintStage should satisfy DecisionStage Protocol
        assert isinstance(stage, DecisionStage)
