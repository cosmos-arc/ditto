"""Unit tests for materialization/planner.py.

Tests DerivedExecutionPlanner.plan() with various run modes, lookback
handling, and partition key generation.
"""

from __future__ import annotations

from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression.contracts import (
    Analysis,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.materialization.contracts import DerivedMaterializationRequest
from ditto_features.materialization.models import DerivedRunMode, DerivedRunTrigger
from ditto_features.materialization.planner import (
    DerivedExecutionPlanner,
    _partition_years,
    _trading_days_to_calendar_days,
)


def _make_spec(
    profile: MaterializationProfile = MaterializationProfile.SERIES,
) -> DerivedSpec:
    return DerivedSpec(
        id="test_feature",
        version=1,
        role=DerivedRole.FEATURE,
        materialization_profile=profile,
        expression="market.close + 1",
    )


def _make_compiled(lookback: int = 0) -> CompiledDerivedExpression:
    import polars as pl

    return CompiledDerivedExpression(
        derived_id="test_feature",
        version=1,
        expr=pl.col("close"),
        analysis=Analysis(
            lookback=lookback,
            requires_full_day=False,
            dependencies=("market.close",),
            operator_names=(),
            scope="default",
        ),
        compile_identity=CompileIdentity(
            compile_input_hash="abc123",
            operator_fingerprint="fp1",
            compiler_fingerprint="fp2",
            cache_key="key1",
            engine_codegen_version="1.0",
            analysis_version="1.0",
            polars_version="1.0",
            expr_serialization_format="json",
        ),
    )


def _make_request(
    mode: DerivedRunMode = DerivedRunMode.FULL,
    start: str = "2024-01-01",
    end: str = "2024-12-31",
) -> DerivedMaterializationRequest:
    return DerivedMaterializationRequest(
        derived_id="test_feature",
        version=1,
        mode=mode,
        request_start=start,
        request_end=end,
        trigger=DerivedRunTrigger.MANUAL,
        source_snapshot_id=None,
    )


# ---------------------------------------------------------------------------
# _trading_days_to_calendar_days
# ---------------------------------------------------------------------------


class TestTradingDaysToCalendarDays:
    """Tests for _trading_days_to_calendar_days."""

    def test_zero_days(self) -> None:
        """Zero trading days converts to zero calendar days."""
        assert _trading_days_to_calendar_days(0) == 0

    def test_rounding_up(self) -> None:
        """Non-integer results are rounded up."""
        result = _trading_days_to_calendar_days(1)
        assert result == 2  # ceil(1 * 365/250) = ceil(1.46) = 2

    def test_exact_multiple(self) -> None:
        """250 trading days = 365 calendar days."""
        result = _trading_days_to_calendar_days(250)
        assert result == 365

    def test_large_value(self) -> None:
        """Large trading days convert correctly."""
        result = _trading_days_to_calendar_days(500)
        assert result == 730  # ceil(500 * 365/250) = ceil(730) = 730


# ---------------------------------------------------------------------------
# _partition_years
# ---------------------------------------------------------------------------


class TestPartitionYears:
    """Tests for _partition_years."""

    def test_single_year(self) -> None:
        """Date range within one year produces one partition."""
        assert _partition_years("2024-01-01", "2024-12-31") == ("2024",)

    def test_spanning_two_years(self) -> None:
        """Date range spanning two years produces two partitions."""
        assert _partition_years("2023-07-01", "2024-06-30") == ("2023", "2024")

    def test_spanning_multiple_years(self) -> None:
        """Date range spanning multiple years produces correct partitions."""
        assert _partition_years("2022-01-01", "2024-12-31") == (
            "2022",
            "2023",
            "2024",
        )

    def test_same_day(self) -> None:
        """Single day produces one partition."""
        assert _partition_years("2024-06-15", "2024-06-15") == ("2024",)


# ---------------------------------------------------------------------------
# DerivedExecutionPlanner
# ---------------------------------------------------------------------------


class TestDerivedExecutionPlanner:
    """Tests for DerivedExecutionPlanner.plan()."""

    def test_full_mode_no_lookback(self) -> None:
        """FULL mode with no lookback: compute_start == request_start."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=0)
        request = _make_request(mode=DerivedRunMode.FULL)

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.derived_id == "test_feature"
        assert plan.version == 1
        assert plan.mode == DerivedRunMode.FULL
        assert plan.compute_start == "2024-01-01"
        assert plan.compute_end == "2024-12-31"
        assert plan.partitions == ("2024",)

    def test_full_mode_with_lookback(self) -> None:
        """FULL mode with lookback: compute_start is before request_start."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=10)
        request = _make_request(mode=DerivedRunMode.FULL)

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        # FULL mode does not apply lookback extension
        assert plan.compute_start == "2024-01-01"

    def test_incremental_mode_with_lookback(self) -> None:
        """INCREMENTAL mode with lookback extends compute_start backward."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=10)
        request = _make_request(mode=DerivedRunMode.INCREMENTAL)

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        # compute_start should be before request_start
        assert plan.compute_start < "2024-01-01"

    def test_incremental_mode_no_lookback(self) -> None:
        """INCREMENTAL mode with no lookback: compute_start == request_start."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=0)
        request = _make_request(mode=DerivedRunMode.INCREMENTAL)

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.compute_start == "2024-01-01"

    def test_incremental_with_earlier_invalidation(self) -> None:
        """INCREMENTAL mode with earlier invalidation adjusts anchor_start."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=0)
        request = _make_request(mode=DerivedRunMode.INCREMENTAL, start="2024-06-01")

        plan = planner.plan(
            spec=spec,
            compiled=compiled,
            request=request,
            earliest_pending_invalidation_start="2024-03-01",
        )

        # anchor_start should be the earlier invalidation date
        assert plan.compute_start == "2024-03-01"

    def test_incremental_with_later_invalidation(self) -> None:
        """INCREMENTAL mode with later invalidation uses request_start."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=0)
        request = _make_request(mode=DerivedRunMode.INCREMENTAL, start="2024-06-01")

        plan = planner.plan(
            spec=spec,
            compiled=compiled,
            request=request,
            earliest_pending_invalidation_start="2024-08-01",
        )

        # Invalidations after request_start don't affect anchor
        assert plan.compute_start == "2024-06-01"

    def test_partitions_for_multi_year(self) -> None:
        """Multi-year request produces correct partitions."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=0)
        request = _make_request(start="2023-07-01", end="2024-06-30")

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.partitions == ("2023", "2024")

    def test_profile_propagated(self) -> None:
        """Materialization profile is propagated to plan."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec(profile=MaterializationProfile.STATE)
        compiled = _make_compiled(lookback=0)
        request = _make_request()

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.profile == MaterializationProfile.STATE

    def test_lookback_propagated(self) -> None:
        """Lookback value is propagated to plan."""
        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = _make_compiled(lookback=20)
        request = _make_request()

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.lookback == 20

    def test_requires_full_day_propagated(self) -> None:
        """requires_full_day flag is propagated to plan."""
        import polars as pl

        planner = DerivedExecutionPlanner()
        spec = _make_spec()
        compiled = CompiledDerivedExpression(
            derived_id="test_feature",
            version=1,
            expr=pl.col("close"),
            analysis=Analysis(
                lookback=5,
                requires_full_day=True,
                dependencies=("market.close",),
                operator_names=(),
                scope="default",
            ),
            compile_identity=CompileIdentity(
                compile_input_hash="abc",
                operator_fingerprint="fp1",
                compiler_fingerprint="fp2",
                cache_key="key1",
                engine_codegen_version="1.0",
                analysis_version="1.0",
                polars_version="1.0",
                expr_serialization_format="json",
            ),
        )
        request = _make_request()

        plan = planner.plan(spec=spec, compiled=compiled, request=request)

        assert plan.requires_full_day is True
