"""Tests for the Phase 3 expression compiler and execution planner."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_core.engine.expression import ExpressionCompiler
from ditto_core.engine.materialization import (
    DerivedExecutionPlanner,
    DerivedMaterializationRequest,
    DerivedRole,
    DerivedRunMode,
    DerivedRunTrigger,
    DerivedSpec,
    MaterializationProfile,
)


def _sample_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 1, 2, 2, 2],
            "trade_date": [
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
            ],
            "close": [10.0, 12.0, 15.0, 8.0, 9.0, 11.0],
            "volume": [100.0, 120.0, 140.0, 90.0, 95.0, 105.0],
            "alpha_base": [0.10, 0.15, 0.20, -0.05, 0.05, 0.08],
            "alpha_state": ["pass", "halt", "pass", "pass", "halt", "pass"],
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
        assert compiled.analysis.lookback == 2
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
        assert non_null.height == 4
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
            "block",
            "pass",
            "block",
            "block",
        ]


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

        assert plan.compute_start == "2026-03-03"
        assert plan.compute_end == "2026-03-13"
        assert plan.partitions == ("2026",)
        assert plan.profile == MaterializationProfile.SERIES
