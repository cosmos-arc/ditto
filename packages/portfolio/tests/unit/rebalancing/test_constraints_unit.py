"""Tests for portfolio constraints module."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_portfolio.rebalancing.constraints import (
    ConstraintChecker,
    ConstraintStage,
    IndustryMaxWeightConstraint,
    LiquidityConstraint,
    MaxPositionsConstraint,
    MaxTurnoverConstraint,
    MaxWeightConstraint,
    MinWeightConstraint,
    TradabilityConstraint,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def weighted_frame() -> pl.DataFrame:
    """5 instruments with pre-assigned weights."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 4, 5],
            "weight": [0.30, 0.25, 0.20, 0.15, 0.10],
        }
    )


def _weights_dict(frame: pl.DataFrame) -> dict[int, float]:
    """Convert weight column to {instrument_id: weight} dict."""
    return dict(
        zip(
            frame["instrument_id"].to_list(),
            frame["weight"].to_list(),
            strict=True,
        )
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

        weights = _weights_dict(result)
        # All weights should be <= 0.20
        for w in weights.values():
            assert w == pytest.approx(0.20, abs=1e-9) or w < 0.20
        # 159915.SZ was 0.30, should be truncated to 0.20
        assert weights[1] == pytest.approx(0.20)
        # 510300.SH was 0.25, should be truncated to 0.20
        assert weights[2] == pytest.approx(0.20)
        # 159949.SZ was exactly 0.20, should be unchanged
        assert weights[3] == pytest.approx(0.20)

    def test_min_weight_zeros_small(self, weighted_frame: pl.DataFrame) -> None:
        constraint = MinWeightConstraint(min_weight=0.18)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        # 159919.SZ had weight 0.10 < 0.18, should be zeroed
        assert weights[5] == pytest.approx(0.0)
        # 510050.SH had weight 0.15 < 0.18, should be zeroed
        assert weights[4] == pytest.approx(0.0)
        # 159949.SZ had weight 0.20 >= 0.18, should be unchanged
        assert weights[3] == pytest.approx(0.20)
        # 159915.SZ had weight 0.30 >= 0.18, should be unchanged
        assert weights[1] == pytest.approx(0.30)

    def test_max_positions_keeps_top_k(self, weighted_frame: pl.DataFrame) -> None:
        constraint = MaxPositionsConstraint(max_positions=3)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        # Top 3 by weight: 159915.SZ (0.30), 510300.SH (0.25), 159949.SZ (0.20)
        assert weights[1] == pytest.approx(0.30)
        assert weights[2] == pytest.approx(0.25)
        assert weights[3] == pytest.approx(0.20)
        # The remaining 2 should be zeroed
        assert weights[4] == pytest.approx(0.0)
        assert weights[5] == pytest.approx(0.0)

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

        weights = _weights_dict(result)
        # 159915.SZ (0.30) was in top 3, then truncated to 0.20
        assert weights[1] == pytest.approx(0.20)
        # 510050.SH and 159919.SZ were removed by max_positions first
        assert weights[4] == pytest.approx(0.0)
        assert weights[5] == pytest.approx(0.0)

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
# Launch portfolio controls
# ---------------------------------------------------------------------------


class TestLaunchPortfolioControls:
    def test_industry_max_weight_caps_available_industry_exposure(self) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4],
                "industry": ["tech", "tech", "finance", None],
                "weight": [0.30, 0.25, 0.20, 0.10],
            },
        )

        checker = ConstraintChecker(
            constraints=[
                IndustryMaxWeightConstraint(
                    max_industry_weight=0.40,
                    industry_column="industry",
                ),
            ],
        )

        result = checker.check(frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.30 / 0.55 * 0.40)
        assert weights[2] == pytest.approx(0.25 / 0.55 * 0.40)
        assert weights[3] == pytest.approx(0.20)
        assert weights[4] == pytest.approx(0.10)
        tech_weight = result.filter(pl.col("industry") == "tech")["weight"].sum()
        assert tech_weight == pytest.approx(0.40)
        assert "max_industry_weight" in " ".join(result["reason_codes"][0])

    def test_minimum_liquidity_filter_zeros_illiquid_positions(self) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "weight": [0.40, 0.35, 0.25],
                "avg_daily_turnover": [20_000_000.0, 4_000_000.0, None],
            },
        )

        checker = ConstraintChecker(
            constraints=[
                LiquidityConstraint(
                    min_liquidity=5_000_000.0,
                    liquidity_column="avg_daily_turnover",
                ),
            ],
        )

        result = checker.check(frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.40)
        assert weights[2] == pytest.approx(0.0)
        assert weights[3] == pytest.approx(0.0)
        assert "min_liquidity" in " ".join(result["reason_codes"][0])

    def test_tradability_excludes_st_and_suspended_instruments(self) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4],
                "weight": [0.30, 0.25, 0.20, 0.15],
                "is_st": [False, True, False, False],
                "is_suspended": [False, False, True, False],
            },
        )

        checker = ConstraintChecker(constraints=[TradabilityConstraint()])

        result = checker.check(frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.30)
        assert weights[2] == pytest.approx(0.0)
        assert weights[3] == pytest.approx(0.0)
        assert weights[4] == pytest.approx(0.15)
        reason_text = " ".join(result["reason_codes"][0])
        assert "st_exclusion" in reason_text
        assert "suspended_exclusion" in reason_text

    def test_max_turnover_limits_changes_from_previous_holdings(self) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "weight": [0.50, 0.20, 0.30],
            },
        )

        checker = ConstraintChecker(
            constraints=[
                MaxTurnoverConstraint(
                    max_turnover=0.20,
                    previous_weights={1: 0.20, 2: 0.40, 3: 0.40},
                ),
            ],
        )

        result = checker.check(frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.30)
        assert weights[2] == pytest.approx(0.3333333333333333)
        assert weights[3] == pytest.approx(0.3666666666666667)
        turnover = sum(
            abs(weights[iid] - previous)
            for iid, previous in {1: 0.20, 2: 0.40, 3: 0.40}.items()
        )
        assert turnover == pytest.approx(0.20)
        assert "max_turnover" in " ".join(result["reason_codes"][0])


# ---------------------------------------------------------------------------
# ConstraintChecker -- Boundary Tests
# ---------------------------------------------------------------------------


class TestConstraintCheckerBoundary:
    """Boundary / edge-case tests for ConstraintChecker."""

    def test_empty_frame(self) -> None:
        """Empty frame with constraints -- should return empty, no crash."""
        frame = pl.DataFrame(
            schema={"instrument_id": pl.Int64, "weight": pl.Float64},
        )
        checker = ConstraintChecker(
            constraints=[
                MaxWeightConstraint(max_weight=0.20),
                MinWeightConstraint(min_weight=0.10),
                MaxPositionsConstraint(max_positions=3),
            ],
        )
        result = checker.check(frame)
        assert result.shape[0] == 0
        assert "weight" in result.columns
        assert "reason_codes" in result.columns

    def test_max_positions_zero_zeros_all(
        self,
        weighted_frame: pl.DataFrame,
    ) -> None:
        """max_positions=0 keeps nothing -- all weights zeroed."""
        constraint = MaxPositionsConstraint(max_positions=0)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        for w in weights.values():
            assert w == pytest.approx(0.0)

    def test_max_weight_zero_zeros_all_positive(
        self,
        weighted_frame: pl.DataFrame,
    ) -> None:
        """max_weight=0.0 -- all positive weights become 0."""
        constraint = MaxWeightConstraint(max_weight=0.0)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        for w in weights.values():
            assert w == pytest.approx(0.0)

    def test_min_weight_one_zeros_all_below_one(
        self,
        weighted_frame: pl.DataFrame,
    ) -> None:
        """min_weight=1.0 with all weights < 1.0 -- all zeroed."""
        constraint = MinWeightConstraint(min_weight=1.0)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        for w in weights.values():
            assert w == pytest.approx(0.0)

    def test_single_constraint_single_instrument(self) -> None:
        """Single instrument with max_weight -- correct truncation."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1],
                "weight": [0.50],
            },
        )
        constraint = MaxWeightConstraint(max_weight=0.25)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(frame)

        weights = _weights_dict(result)
        assert weights[1] == pytest.approx(0.25)

    def test_all_zero_weights_unchanged(self) -> None:
        """All weights already 0 -- constraints produce no changes."""
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "weight": [0.0, 0.0, 0.0],
            },
        )
        checker = ConstraintChecker(
            constraints=[
                MaxWeightConstraint(max_weight=0.20),
                MinWeightConstraint(min_weight=0.05),
                MaxPositionsConstraint(max_positions=1),
            ],
        )
        result = checker.check(frame)

        weights = _weights_dict(result)
        for w in weights.values():
            assert w == pytest.approx(0.0)

    def test_negative_weights_preserved_by_min(self) -> None:
        """MinWeightConstraint only zeros 0 < w < min; negative and 0 pass through."""
        frame = pl.DataFrame(
            {
                "instrument_id": [10, 11, 12, 13],
                "weight": [-0.10, 0.0, 0.05, 0.20],
            },
        )
        constraint = MinWeightConstraint(min_weight=0.10)
        checker = ConstraintChecker(constraints=[constraint])
        result = checker.check(frame)

        weights = _weights_dict(result)
        # Negative weight unchanged
        assert weights[10] == pytest.approx(-0.10)
        # Exactly zero unchanged
        assert weights[11] == pytest.approx(0.0)
        # 0 < 0.05 < 0.10 => zeroed
        assert weights[12] == pytest.approx(0.0)
        # 0.20 >= 0.10 => unchanged
        assert weights[13] == pytest.approx(0.20)

    def test_combined_max_positions_and_min_weight(
        self,
        weighted_frame: pl.DataFrame,
    ) -> None:
        """max_positions removes some, min_weight zeros remaining small ones.

        Priority order: min_weight (20) runs before max_positions (30).
        Step 1 -- min_weight=0.18 zeros 510050.SH (0.15) and 159919.SZ (0.10).
        Step 2 -- max_positions=2 keeps top 2 of remaining:
                  159915.SZ (0.30) and 510300.SH (0.25), zeros 159949.SZ (0.20).
        """
        constraints = [
            MaxPositionsConstraint(max_positions=2),
            MinWeightConstraint(min_weight=0.18),
        ]
        checker = ConstraintChecker(constraints=constraints)
        result = checker.check(weighted_frame)

        weights = _weights_dict(result)
        # 159915.SZ (0.30) -- passes min_weight, in top 2 => kept
        assert weights[1] == pytest.approx(0.30)
        # 510300.SH (0.25) -- passes min_weight, in top 2 => kept
        assert weights[2] == pytest.approx(0.25)
        # 159949.SZ (0.20) -- passes min_weight, but NOT in top 2 => zeroed
        assert weights[3] == pytest.approx(0.0)
        # 510050.SH (0.15) -- zeroed by min_weight
        assert weights[4] == pytest.approx(0.0)
        # 159919.SZ (0.10) -- zeroed by min_weight
        assert weights[5] == pytest.approx(0.0)


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

        weights = _weights_dict(result)
        assert weights[1] == pytest.approx(0.20)
