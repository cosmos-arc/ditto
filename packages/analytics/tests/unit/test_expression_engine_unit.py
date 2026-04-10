"""Tests for the Phase 3 expression compiler and execution planner."""

from __future__ import annotations

import math
from datetime import date

import polars as pl
import pytest
from ditto_analytics.expression import ExpressionCompiler, compute_compile_cache_key
from ditto_analytics.materialization import (
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedRunMode,
    DerivedRunTrigger,
)
from ditto_kernel.specs import DerivedRole, DerivedSpec, MaterializationProfile


def _is_non_finite(v: object) -> bool:
    """Return True if *v* is a non-finite (NaN or Inf) float."""
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _sample_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2],
            "trade_date": [
                date(2026, 3, 8),
                date(2026, 3, 9),
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
                date(2026, 3, 13),
                date(2026, 3, 8),
                date(2026, 3, 9),
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
                date(2026, 3, 13),
            ],
            "close": [
                10.0,
                11.0,
                10.0,
                12.0,
                15.0,
                8.0,
                8.0,
                7.5,
                8.0,
                9.0,
                11.0,
                20.0,
            ],
            "volume": [
                100.0,
                110.0,
                100.0,
                120.0,
                140.0,
                130.0,
                90.0,
                85.0,
                90.0,
                95.0,
                105.0,
                110.0,
            ],
            "alpha_base": [
                0.10,
                0.12,
                0.10,
                0.15,
                0.20,
                0.18,
                -0.05,
                -0.03,
                -0.05,
                0.05,
                0.08,
                0.12,
            ],
            "alpha_state": [
                "pass",
                "pass",
                "pass",
                "halt",
                "pass",
                "pass",
                "pass",
                "pass",
                "pass",
                "halt",
                "pass",
                "pass",
            ],
        }
    )


class TestExpressionCompiler:
    """Tests for the unified expression compiler."""

    def test_compile_collects_dependencies_and_operator_names(self) -> None:
        """Compiler should expose dependencies, operators, and lookback metadata."""
        spec = DerivedSpec(
            id="factor.alpha_simple",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression=(
                "cs_rank(ts_delta(market.close, 2) / ts_mean(market.volume, 2)) "
                "+ @alpha_base"
            ),
        )
        compiler = ExpressionCompiler()

        compiled = compiler.compile(spec)

        assert compiled.analysis.dependencies == (
            "market.close",
            "market.volume",
            "alpha_base",
        )
        assert compiled.analysis.operator_names == ("cs_rank", "ts_delta", "ts_mean")
        assert compiled.analysis.lookback == 3
        assert compiled.analysis.requires_full_day is True
        assert compiled.analysis.scope == "mixed"
        assert compiled.analysis.output_schema == ("value",)
        assert compiled.compile_identity.operator_fingerprint
        assert compiled.compile_identity.compiler_fingerprint

    def test_codegen_runs_against_polars_dataframe(self) -> None:
        """Compiled polars expression should run on a sorted dataframe."""
        spec = DerivedSpec(
            id="factor.alpha_simple",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="cs_rank(ts_delta(market.close, 1))",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)

        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height == 10
        assert non_null["value"].min() >= 0.0
        assert non_null["value"].max() <= 1.0

    def test_codegen_supports_scalar_conditionals_and_math(self) -> None:
        """Compiler should support scalar math branches used by derived formulas."""
        spec = DerivedSpec(
            id="feature.scalar_math",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression=(
                "if_else(abs(market.close) > 10, "
                "clip(power(market.close, 2), 0, 200), "
                "min2(exp(log(market.close)), sqrt(market.close)))"
            ),
        )
        compiler = ExpressionCompiler()

        compiled = compiler.compile(spec)
        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert result["value"].null_count() == 0
        assert result["value"].max() == 200.0

    def test_codegen_supports_unary_grouping(self) -> None:
        """Unary minus and grouped arithmetic should compile cleanly."""
        spec = DerivedSpec(
            id="feature.unary_grouping",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="(-market.close + 1) / 2",
        )
        compiler = ExpressionCompiler()

        compiled = compiler.compile(spec)
        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert result["value"][0] == -4.5

    def test_codegen_supports_logical_ops_and_string_literals(self) -> None:
        """Logical operators and string branches should compile to Polars cleanly."""
        spec = DerivedSpec(
            id="feature.state_gate",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression=(
                'if_else(@alpha_state == "halt" or '
                "(market.close > 10 and not market.volume < 95), "
                '"block", "pass")'
            ),
        )
        compiler = ExpressionCompiler()

        compiled = compiler.compile(spec)
        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert result["value"].to_list() == [
            "pass",
            "block",
            "pass",
            "block",
            "block",
            "pass",
            "pass",
            "pass",
            "pass",
            "block",
            "block",
            "block",
        ]

    def test_codegen_ts_rank(self) -> None:
        """ts_rank should produce per-group percentile rank over shifted window."""
        spec = DerivedSpec(
            id="factor.ts_rank",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_rank(market.close, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)

        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        # 4 per instrument (rolling_rank includes null slots)
        assert non_null.height == 8
        assert non_null["value"].min() >= 0.0
        assert non_null["value"].max() <= 1.0

    def test_codegen_ts_argmax(self) -> None:
        """ts_argmax should return the position of the maximum in the window."""
        spec = DerivedSpec(
            id="factor.ts_argmax",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_argmax(market.close, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)

        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height == 6
        # arg_max should return integer indices (0-based from the shifted window)
        assert set(non_null["value"].cast(pl.Int64).to_list()).issubset({0, 1, 2})

    def test_codegen_ts_argmin(self) -> None:
        """ts_argmin should return the position of the minimum in the window."""
        spec = DerivedSpec(
            id="factor.ts_argmin",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_argmin(market.close, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)

        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )

        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height == 6
        assert set(non_null["value"].cast(pl.Int64).to_list()).issubset({0, 1, 2})


class TestPhase1P0Fixes:
    """Tests for P0 correctness fixes: divide-by-zero, ts_corr/ts_cov, lookback."""

    # --- 1A: Divide-by-zero fixes (E-3, E-4, E-5) ---

    def test_codegen_cs_zscore_zero_std(self) -> None:
        """cs_zscore on a constant column (std=0) should return 0.0, not Inf/NaN."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "x": [5.0, 5.0, 5.0, 5.0],
            }
        )
        spec = DerivedSpec(
            id="feature.cs_zscore_const",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="cs_zscore(x)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        values = result["value"].to_list()
        assert all(v is None or not _is_non_finite(v) for v in values), (
            f"Expected finite values, got {values}"
        )

    def test_codegen_cs_scale_zero_values(self) -> None:
        """cs_scale on an all-zero column should not produce Inf/NaN."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "x": [0.0, 0.0, 0.0, 0.0],
            }
        )
        spec = DerivedSpec(
            id="feature.cs_scale_zero",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="cs_scale(x)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        values = result["value"].to_list()
        assert all(v is None or not _is_non_finite(v) for v in values), (
            f"Expected finite values, got {values}"
        )

    def test_codegen_ts_pct_change_zero_denominator(self) -> None:
        """ts_pct_change should return 0.0 when the shifted value is 0, not Inf."""
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 4,
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                    date(2026, 3, 13),
                ],
                "x": [5.0, 0.0, 0.0, 3.0],
            }
        )
        spec = DerivedSpec(
            id="feature.pct_change_zero",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="ts_pct_change(x, 1)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        non_null = result.drop_nulls("value")
        assert non_null.height > 0
        for v in non_null["value"].to_list():
            assert not _is_non_finite(v)

    # --- 1B: ts_corr/ts_cov codegen (E-1) ---

    def test_codegen_ts_corr(self) -> None:
        """ts_corr should compute rolling correlation between two expressions."""
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 6,
                "trade_date": [
                    date(2026, 3, 8),
                    date(2026, 3, 9),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                    date(2026, 3, 13),
                ],
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
            }
        )
        spec = DerivedSpec(
            id="factor.ts_corr",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_corr(a, b, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height > 0
        # Perfectly correlated data should yield correlation near 1.0
        corr_values = non_null["value"].to_list()
        assert all(abs(v - 1.0) < 0.01 for v in corr_values if v is not None), (
            f"Expected ~1.0 correlation, got {corr_values}"
        )

    def test_codegen_ts_cov(self) -> None:
        """ts_cov should compute rolling covariance between two expressions."""
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 6,
                "trade_date": [
                    date(2026, 3, 8),
                    date(2026, 3, 9),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                    date(2026, 3, 13),
                ],
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
            }
        )
        spec = DerivedSpec(
            id="factor.ts_cov",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_cov(a, b, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height > 0
        # Covariance of perfectly correlated data should be positive
        cov_values = non_null["value"].to_list()
        assert all(v > 0 for v in cov_values if v is not None), (
            f"Expected positive covariance, got {cov_values}"
        )

    # --- 1C: Lookback off-by-1 (E-2) ---

    def test_lookback_rolling_adds_one(self) -> None:
        """Rolling fns (ts_mean, ts_std) should have lookback = window + 1."""
        spec = DerivedSpec(
            id="factor.rolling_lookback",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(market.close, 20)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        assert compiled.analysis.lookback == 21

    def test_lookback_shift_only(self) -> None:
        """Shift-only fns (ts_delay, ts_delta, etc.) should have lookback = window."""
        spec = DerivedSpec(
            id="factor.shift_lookback",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delay(market.close, 5)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        assert compiled.analysis.lookback == 5

    def test_lookback_two_expr_rolling(self) -> None:
        """ts_corr/ts_cov (two-expr rolling) should have lookback = window + 1."""
        spec = DerivedSpec(
            id="factor.corr_lookback",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_corr(a, b, 10)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        assert compiled.analysis.lookback == 11


class TestPhase2NewOperators:
    """Tests for P1 new ops: ts_ema, ts_decay_linear, coalesce, group ops."""

    def test_codegen_ts_ema(self) -> None:
        """ts_ema should produce exponential moving average with PIT protection."""
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 6,
                "trade_date": [
                    date(2026, 3, 8),
                    date(2026, 3, 9),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                    date(2026, 3, 13),
                ],
                "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            }
        )
        spec = DerivedSpec(
            id="factor.ts_ema",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_ema(x, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height > 0
        # EMA should be finite
        for v in non_null["value"].to_list():
            assert not _is_non_finite(v)

    def test_codegen_ts_decay_linear(self) -> None:
        """ts_decay_linear should produce linearly weighted moving average."""
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 5,
                "trade_date": [
                    date(2026, 3, 8),
                    date(2026, 3, 9),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                ],
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )
        spec = DerivedSpec(
            id="factor.ts_decay_linear",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_decay_linear(x, 3)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        non_null = result.drop_nulls("value")
        assert non_null.height == 2
        # After shift(1): [null,1,2,3,4] → rolling_map with window=3, min_samples=3
        # Window 1: [null,1,2] → only 2 valid → null (min_samples=3)
        # Window 2: [1,2,3], WMA = (1*1+2*2+3*3)/6 = 14/6 ≈ 2.333
        # Window 3: [2,3,4], WMA = (1*2+2*3+3*4)/6 = 20/6 ≈ 3.333
        values = non_null["value"].to_list()
        assert abs(values[0] - 14.0 / 6.0) < 0.01
        assert abs(values[1] - 20.0 / 6.0) < 0.01

    def test_codegen_coalesce(self) -> None:
        """coalesce should return the first non-null argument."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "a": [1.0, None, None, 4.0],
                "b": [None, 2.0, 3.0, None],
                "c": [0.0, 0.0, 0.0, 0.0],
            }
        )
        spec = DerivedSpec(
            id="feature.coalesce_test",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="coalesce(a, b, c)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert result["value"].to_list() == [1.0, 2.0, 3.0, 4.0]

    def test_codegen_group_rank(self) -> None:
        """group_rank should compute rank within a group column."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2, 3, 3],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "sector": ["A", "A", "B", "B", "A", "A"],
                "x": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            }
        )
        spec = DerivedSpec(
            id="factor.group_rank",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="group_rank(x, sector)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        values = result["value"].to_list()
        # Sector A has x=[10,20,50,60], rank within A
        # Sector B has x=[30,40], rank within B
        assert all(v is not None and 0 < v <= 1.0 for v in values)

    def test_codegen_group_zscore(self) -> None:
        """group_zscore should compute z-score within a group, handling std=0."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2, 3, 3],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "sector": ["A", "A", "B", "B", "A", "A"],
                "x": [10.0, 20.0, 5.0, 5.0, 50.0, 60.0],
            }
        )
        spec = DerivedSpec(
            id="factor.group_zscore",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="group_zscore(x, sector)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert "value" in result.columns
        values = result["value"].to_list()
        # Sector B has constant x=[5.0, 5.0], std=0, should return 0.0
        assert values[2] == 0.0
        assert values[3] == 0.0
        # Sector A has x=[10,20,50,60] with non-zero std
        assert values[0] is not None
        # All values should be finite
        for v in values:
            if v is not None:
                assert not _is_non_finite(v)


class TestDerivedExecutionPlanner:
    """Tests for execution planning rules."""

    def test_incremental_plan_uses_earliest_invalidation_and_lookback(self) -> None:
        """Incremental plans should warm up from the earliest invalidation boundary."""
        spec = DerivedSpec(
            id="factor.alpha_simple",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(market.close, 5)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        planner = DerivedExecutionPlanner()
        request = DerivedMaterializationRequest(
            derived_id="factor.alpha_simple",
            version=3,
            mode=DerivedRunMode.INCREMENTAL,
            request_start="2026-03-10",
            request_end="2026-03-13",
            trigger=DerivedRunTrigger.CASCADE,
            source_snapshot_id="market:20260313-001",
        )

        plan = planner.plan(
            spec=spec,
            compiled=compiled,
            request=request,
            earliest_pending_invalidation_start="2026-03-08",
        )

        # ts_mean(window=5) → lookback=6 trading days → ceil(6*365/250)=9 calendar days
        # anchor 2026-03-08 - 9 days = 2026-02-27
        assert plan.compute_start == "2026-02-27"
        assert plan.compute_end == "2026-03-13"
        assert plan.partitions == ("2026",)
        assert plan.profile == MaterializationProfile.SERIES


class TestPhase4ScalarAndValidation:
    """Tests for Phase 4: scalar ops, window validation, cs_winsorize sigma."""

    def test_codegen_log10(self) -> None:
        """log10 should compute base-10 logarithm."""
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="log10(market.close)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )
        assert result["value"].null_count() == 0

    def test_codegen_round(self) -> None:
        """round should round to specified decimal places."""
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="round(market.close, 0)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = (
            _sample_frame()
            .sort(["instrument_id", "trade_date"])
            .with_columns(compiled.expr.alias("value"))
        )
        assert result["value"].null_count() == 0

    def test_negative_window_rejected(self) -> None:
        """Negative window size should raise compile error E033."""
        from ditto_analytics.expression.diagnostics import ExpressionCompileError

        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="ts_mean(market.close, -5)",
        )
        compiler = ExpressionCompiler()
        with pytest.raises(ExpressionCompileError):
            compiler.compile(spec)

    def test_zero_window_rejected(self) -> None:
        """Zero window size should raise compile error E033."""
        from ditto_analytics.expression.diagnostics import ExpressionCompileError

        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="ts_mean(market.close, 0)",
        )
        compiler = ExpressionCompiler()
        with pytest.raises(ExpressionCompileError):
            compiler.compile(spec)

    def test_cs_winsorize_custom_sigma(self) -> None:
        """cs_winsorize should accept custom sigma parameter."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "x": [1.0, 2.0, 100.0, 200.0],
            }
        )
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="cs_winsorize(x, 1)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        assert result["value"].null_count() == 0

    def test_cs_winsorize_default_sigma_produces_finite_values(self) -> None:
        """cs_winsorize(x) with default sigma=3 should clip extreme outliers."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1, 1, 2, 2, 2, 2],
                "trade_date": [date(2026, 3, 10)] * 4 + [date(2026, 3, 10)] * 4,
                "x": [1.0, 2.0, 3.0, 1000.0, 5.0, 6.0, 7.0, -999.0],
            }
        )
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="cs_winsorize(x)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        values = result["value"].to_list()
        assert all(v is not None and not _is_non_finite(v) for v in values)

    def test_cs_winsorize_quantile_mode(self) -> None:
        """cs_winsorize(x, 'quantile', 0.1, 0.9) clips at 10th/90th percentiles."""
        # 10 instruments, same date → cross-section
        df = pl.DataFrame(
            {
                "instrument_id": list(range(1, 11)),
                "trade_date": [date(2026, 3, 10)] * 10,
                "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            }
        )
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression='cs_winsorize(x, "quantile", 0.1, 0.9)',
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        values = result["value"].to_list()
        # 5th percentile of [1..10] with linear interpolation ≈ 1.45
        # 95th percentile ≈ 9.55
        # min should be clipped up, max should be clipped down
        assert min(values) >= 1.0
        assert max(values) <= 10.0
        # No NaN or Inf
        assert all(v is not None and not _is_non_finite(v) for v in values)

    def test_cs_winsorize_quantile_with_outliers(self) -> None:
        """Quantile winsorize should clip extreme outliers to percentile bounds."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1, 1, 1, 2, 2, 2, 2, 2],
                "trade_date": [date(2026, 3, 10)] * 5 + [date(2026, 3, 10)] * 5,
                "x": [-1000.0, 1.0, 2.0, 3.0, 1000.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            }
        )
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression='cs_winsorize(x, "quantile", 0.1, 0.9)',
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        result = df.sort(["instrument_id", "trade_date"]).with_columns(
            compiled.expr.alias("value")
        )
        values = result["value"].to_list()
        # -1000 and 1000 should be clipped to the 10th/90th percentile bounds
        assert all(v is not None and not _is_non_finite(v) for v in values)
        # The clipped values should be much closer to the median than original
        assert max(values) < 500.0
        assert min(values) > -500.0


class TestPhase6TypeChecking:
    """Tests for Phase 6: ts_* argument type validation."""

    def test_ts_rejects_string_argument(self) -> None:
        """ts_* operators should reject StringNode arguments with E031."""
        from ditto_analytics.expression.diagnostics import ExpressionCompileError

        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression='ts_mean("hello", 5)',
        )
        compiler = ExpressionCompiler()
        with pytest.raises(ExpressionCompileError, match="must be numeric"):
            compiler.compile(spec)

    def test_ts_corr_rejects_string_in_second_arg(self) -> None:
        """ts_corr should reject StringNode in the series argument position."""
        from ditto_analytics.expression.diagnostics import ExpressionCompileError

        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression='ts_corr(market.close, "bad", 3)',
        )
        compiler = ExpressionCompiler()
        with pytest.raises(ExpressionCompileError, match="must be numeric"):
            compiler.compile(spec)

    def test_ts_allows_column_ref_and_number(self) -> None:
        """ts_* operators should accept ColumnRefNode and NumberNode arguments."""
        spec = DerivedSpec(
            id="f",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.DERIVE,
            expression="ts_mean(market.close, 5)",
        )
        compiler = ExpressionCompiler()
        compiled = compiler.compile(spec)
        assert compiled is not None


class TestPhase5CacheOptimization:
    """Tests for Phase 5: LRU cache and pre-parsed AST optimisation."""

    def test_lru_cache_max_size(self) -> None:
        """SQLiteCompileCache should accept max_cache_size parameter."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()

        from ditto_analytics.compile_cache import SQLiteCompileCache

        cache = SQLiteCompileCache(mock_client, max_cache_size=128)
        assert cache is not None

    def test_l2_hit_uses_prefetched_ast(self) -> None:
        """L2 cache hit should avoid double parsing by using pre-parsed AST."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.execute.return_value = (1,)

        from ditto_analytics.compile_cache import SQLiteCompileCache
        from ditto_analytics.expression.ast import CallNode

        cache = SQLiteCompileCache(mock_client, max_cache_size=128)
        assert cache._memory_cache.maxsize == 128
        spec = DerivedSpec(
            id="factor.test",
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(market.close, 5)",
        )
        # compute_compile_cache_key should return 4-tuple including AST
        result = compute_compile_cache_key(spec)
        assert len(result) == 4
        _, _, _, ast = result
        assert isinstance(ast, CallNode)
