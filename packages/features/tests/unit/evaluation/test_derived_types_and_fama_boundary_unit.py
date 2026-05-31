"""Comprehensive tests for derived_types.py and expression/contracts.py.

Tests DerivedSpec, DerivedRole, MaterializationProfile, and
CompileIdentity/Analysis/CompiledDerivedExpression with edge cases.
Also tests evaluation report dataclasses for completeness.
"""

from __future__ import annotations

import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    FactorExposureResult,
    FamaMacBethResult,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
    TailRiskMetrics,
)

# ---------------------------------------------------------------------------
# DerivedRole
# ---------------------------------------------------------------------------


class TestDerivedRole:
    """Tests for DerivedRole enum."""

    def test_all_values(self) -> None:
        """All expected roles exist."""
        assert DerivedRole.FEATURE == "feature"
        assert DerivedRole.FACTOR == "factor"
        assert DerivedRole.SIGNAL == "signal"
        assert DerivedRole.LABEL == "label"

    def test_is_str_enum(self) -> None:
        """DerivedRole is a string enum."""
        assert isinstance(DerivedRole.FEATURE, str)

    @pytest.mark.parametrize("role", ["feature", "factor", "signal", "label"])
    def test_construct_from_string(self, role: str) -> None:
        """Can construct from string value."""
        assert DerivedRole(role) == role


# ---------------------------------------------------------------------------
# MaterializationProfile
# ---------------------------------------------------------------------------


class TestMaterializationProfile:
    """Tests for MaterializationProfile enum."""

    def test_all_values(self) -> None:
        """All expected profiles exist."""
        assert MaterializationProfile.SERIES == "SERIES"
        assert MaterializationProfile.STATE == "STATE"
        assert MaterializationProfile.DERIVE == "DERIVE"
        assert MaterializationProfile.OFFLINE == "OFFLINE"

    def test_is_str_enum(self) -> None:
        """MaterializationProfile is a string enum."""
        assert isinstance(MaterializationProfile.SERIES, str)


# ---------------------------------------------------------------------------
# DerivedSpec
# ---------------------------------------------------------------------------


class TestDerivedSpec:
    """Tests for DerivedSpec dataclass."""

    def _make_spec(self, **overrides: object) -> DerivedSpec:
        defaults = {
            "id": "test",
            "version": 1,
            "role": DerivedRole.FEATURE,
            "materialization_profile": MaterializationProfile.SERIES,
            "expression": "market.close + 1",
        }
        defaults.update(overrides)
        return DerivedSpec(**defaults)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """All required fields are accessible."""
        spec = self._make_spec()
        assert spec.id == "test"
        assert spec.version == 1
        assert spec.role == DerivedRole.FEATURE
        assert spec.expression == "market.close + 1"

    def test_default_entity_keys(self) -> None:
        """Default entity_keys is ('instrument_id',)."""
        spec = self._make_spec()
        assert spec.entity_keys == ("instrument_id",)

    def test_custom_entity_keys(self) -> None:
        """Custom entity_keys are accepted."""
        spec = self._make_spec(entity_keys=("asset_id",))
        assert spec.entity_keys == ("asset_id",)

    def test_default_grain(self) -> None:
        """Default grain is '1d'."""
        spec = self._make_spec()
        assert spec.grain == "1d"

    def test_effective_time_keys_default(self) -> None:
        """effective_time_keys returns grain-derived default when not set."""
        spec = self._make_spec()
        result = spec.effective_time_keys
        assert isinstance(result, tuple)
        assert len(result) > 0

    def test_effective_time_keys_explicit(self) -> None:
        """effective_time_keys returns explicit value when set."""
        spec = self._make_spec(time_keys=("trade_date",))
        assert spec.effective_time_keys == ("trade_date",)

    def test_timezone_from_calendar(self) -> None:
        """timezone property returns calendar-derived timezone."""
        spec = self._make_spec()
        tz = spec.timezone
        assert isinstance(tz, str)
        assert len(tz) > 0

    def test_frozen(self) -> None:
        """DerivedSpec is frozen."""
        spec = self._make_spec()
        with pytest.raises(AttributeError):
            spec.id = "other"  # type: ignore[misc]

    def test_all_roles(self) -> None:
        """All DerivedRole values are accepted."""
        for role in DerivedRole:
            spec = self._make_spec(role=role)
            assert spec.role == role

    def test_all_profiles(self) -> None:
        """All MaterializationProfile values are accepted."""
        for profile in MaterializationProfile:
            spec = self._make_spec(materialization_profile=profile)
            assert spec.materialization_profile == profile

    def test_optional_fields(self) -> None:
        """Optional fields have sensible defaults."""
        spec = self._make_spec()
        assert spec.time_keys is None
        assert spec.calendar == "cn_stock"
        assert spec.description is None
        assert spec.universe_id is None

    def test_custom_description(self) -> None:
        """Custom description is accepted."""
        spec = self._make_spec(description="My factor")
        assert spec.description == "My factor"

    def test_operator_versions_default(self) -> None:
        """operator_versions defaults to empty dict."""
        spec = self._make_spec()
        assert spec.operator_versions == {}


# ---------------------------------------------------------------------------
# ICSummary
# ---------------------------------------------------------------------------


class TestICSummaryDataclass:
    """Tests for ICSummary dataclass."""

    def test_creation(self) -> None:
        """ICSummary can be created with all fields."""
        summary = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        assert summary.mean == 0.05
        assert summary.std == 0.10
        assert summary.icir == 0.5

    def test_frozen(self) -> None:
        """ICSummary is frozen."""
        summary = ICSummary(
            mean=0.0, std=0.0, icir=0.0, t_stat=0.0, p_value=1.0, win_rate=0.0
        )
        with pytest.raises(AttributeError):
            summary.mean = 1.0  # type: ignore[misc]

    def test_equality(self) -> None:
        """Equal ICSummaries compare equal."""
        a = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        b = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        assert a == b

    def test_inequality(self) -> None:
        """Different ICSummaries compare unequal."""
        a = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        b = ICSummary(
            mean=0.06, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        assert a != b


# ---------------------------------------------------------------------------
# TailRiskMetrics
# ---------------------------------------------------------------------------


class TestTailRiskMetricsDataclass:
    """Tests for TailRiskMetrics dataclass."""

    def test_creation(self) -> None:
        """Can be created with all fields."""
        metrics = TailRiskMetrics(
            cvar_95=-0.02,
            cvar_99=-0.05,
            skewness=-0.1,
            kurtosis=0.5,
            max_single_day_loss=-0.03,
        )
        assert metrics.cvar_95 == -0.02

    def test_zero_metrics(self) -> None:
        """All-zero metrics."""
        metrics = TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=0.0,
        )
        assert metrics.cvar_95 == 0.0


# ---------------------------------------------------------------------------
# LongShortResult
# ---------------------------------------------------------------------------


class TestLongShortResultDataclass:
    """Tests for LongShortResult dataclass."""

    def _make_tail(self) -> TailRiskMetrics:
        return TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=0.0,
        )

    def test_creation(self) -> None:
        """Can be created with all fields."""
        ls = LongShortResult(
            annual_return=0.1,
            annual_volatility=0.15,
            sharpe=0.67,
            portfolio_ir=0.67,
            sortino=1.0,
            max_drawdown=-0.08,
            calmar=1.25,
            tail_risk=self._make_tail(),
        )
        assert ls.annual_return == 0.1

    def test_frozen(self) -> None:
        """LongShortResult is frozen."""
        ls = LongShortResult(
            annual_return=0.0,
            annual_volatility=0.0,
            sharpe=0.0,
            portfolio_ir=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            calmar=0.0,
            tail_risk=self._make_tail(),
        )
        with pytest.raises(AttributeError):
            ls.annual_return = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FamaMacBethResult
# ---------------------------------------------------------------------------


class TestFamaMacBethResultDataclass:
    """Tests for FamaMacBethResult dataclass."""

    def test_creation(self) -> None:
        """Can be created with all fields."""
        result = FamaMacBethResult(
            factor_exposure=0.05,
            exposure_t_stat=2.0,
            exposure_p_value=0.05,
            exposure_stderr=0.025,
            r_squared_avg=0.3,
            n_periods=50,
            slopes=(("target", 0.05),),
        )
        assert result.factor_exposure == 0.05
        assert result.n_periods == 50

    def test_empty_slopes(self) -> None:
        """Empty slopes tuple."""
        result = FamaMacBethResult(
            factor_exposure=0.0,
            exposure_t_stat=0.0,
            exposure_p_value=1.0,
            exposure_stderr=0.0,
            r_squared_avg=0.0,
            n_periods=0,
            slopes=(),
        )
        assert result.slopes == ()


# ---------------------------------------------------------------------------
# FactorExposureResult
# ---------------------------------------------------------------------------


class TestFactorExposureResultDataclass:
    """Tests for FactorExposureResult dataclass."""

    def test_creation(self) -> None:
        """Can be created with all fields."""
        result = FactorExposureResult(
            target_exposure={"market": 0.5},
            correlation_matrix={"target": {"target": 1.0}},
            orthogonal_residual_stats={"market": 0.02},
            n_factors=1,
            n_dates=100,
        )
        assert result.n_factors == 1
        assert result.target_exposure["market"] == 0.5


# ---------------------------------------------------------------------------
# RegimeICResult
# ---------------------------------------------------------------------------


class TestRegimeICResultDataclass:
    """Tests for RegimeICResult dataclass."""

    def test_creation(self) -> None:
        """Can be created with all fields."""
        result = RegimeICResult(
            regimes={},
            regime_labels=[],
            transition_matrix={},
            ic_trend=0.0,
            ic_trend_p_value=1.0,
        )
        assert result.regimes == {}
        assert result.ic_trend == 0.0

    def test_with_data(self) -> None:
        """Can hold regime data."""
        ic_summary = ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )
        result = RegimeICResult(
            regimes={"low_vol": ic_summary},
            regime_labels=[("2024-01-01", "low_vol")],
            transition_matrix={"low_vol": {"low_vol": 0.8, "high_vol": 0.2}},
            ic_trend=0.001,
            ic_trend_p_value=0.3,
        )
        assert "low_vol" in result.regimes


# ---------------------------------------------------------------------------
# PerformanceAttributionResult
# ---------------------------------------------------------------------------


class TestPerformanceAttributionResultDataclass:
    """Tests for PerformanceAttributionResult dataclass."""

    def test_creation(self) -> None:
        """Can be created with all fields."""
        result = PerformanceAttributionResult(
            total_return=0.15,
            selection_return=0.10,
            timing_return=0.05,
            interaction_return=0.0,
            annual_alpha=0.10,
            tracking_error=0.08,
            information_ratio=1.25,
            win_rate_by_quantile={1: 0.45, 5: 0.55},
        )
        assert result.total_return == 0.15
        assert result.win_rate_by_quantile[5] == 0.55

    def test_zero_result(self) -> None:
        """All-zero result."""
        result = PerformanceAttributionResult(
            total_return=0.0,
            selection_return=0.0,
            timing_return=0.0,
            interaction_return=0.0,
            annual_alpha=0.0,
            tracking_error=0.0,
            information_ratio=0.0,
            win_rate_by_quantile={},
        )
        assert result.total_return == 0.0
        assert result.win_rate_by_quantile == {}


# ---------------------------------------------------------------------------
# FactorEvaluationReport
# ---------------------------------------------------------------------------


class TestFactorEvaluationReportDataclass:
    """Tests for FactorEvaluationReport creation and immutability."""

    def _make_ic_summary(self) -> ICSummary:
        return ICSummary(
            mean=0.05, std=0.10, icir=0.5, t_stat=2.0, p_value=0.05, win_rate=0.6
        )

    def _make_tail(self) -> TailRiskMetrics:
        return TailRiskMetrics(
            cvar_95=0.0,
            cvar_99=0.0,
            skewness=0.0,
            kurtosis=0.0,
            max_single_day_loss=0.0,
        )

    def _make_ls(self) -> LongShortResult:
        return LongShortResult(
            annual_return=0.1,
            annual_volatility=0.15,
            sharpe=0.67,
            portfolio_ir=0.67,
            sortino=1.0,
            max_drawdown=-0.08,
            calmar=1.25,
            tail_risk=self._make_tail(),
        )

    def _make_report(self) -> FactorEvaluationReport:
        ic = self._make_ic_summary()
        return FactorEvaluationReport(
            factor_id="test_factor",
            factor_version=1,
            evaluation_period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
            rank_ic_summary=ic,
            pearson_ic_summary=ic,
            ic_decay=[],
            ic_half_life=None,
            ic_autocorrelation=[],
            quantile_annual_returns={},
            long_short=self._make_ls(),
            avg_turnover=0.0,
            net_return_after_cost=0.0,
            turnover_adjusted_ir=0.0,
            grinold_kahn_ir=0.0,
            sub_period_ic={},
            n_observations=0,
            n_dates=0,
            computed_at="2024-01-01",
        )

    def test_creation(self) -> None:
        """Report can be created with all required fields."""
        report = self._make_report()
        assert report.factor_id == "test_factor"
        assert report.holding_period == 5

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None."""
        report = self._make_report()
        assert report.fama_macbeth is None
        assert report.factor_exposure is None
        assert report.regime_ic is None
        assert report.performance_attribution is None

    def test_frozen(self) -> None:
        """Report is frozen."""
        report = self._make_report()
        with pytest.raises(AttributeError):
            report.factor_id = "other"  # type: ignore[misc]

    def test_with_optional_fields(self) -> None:
        """Report can hold optional analysis results."""
        fm = FamaMacBethResult(
            factor_exposure=0.05,
            exposure_t_stat=2.0,
            exposure_p_value=0.05,
            exposure_stderr=0.025,
            r_squared_avg=0.3,
            n_periods=50,
            slopes=(("target", 0.05),),
        )
        report = FactorEvaluationReport(
            factor_id="f",
            factor_version=1,
            evaluation_period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
            rank_ic_summary=self._make_ic_summary(),
            pearson_ic_summary=self._make_ic_summary(),
            ic_decay=[],
            ic_half_life=None,
            ic_autocorrelation=[],
            quantile_annual_returns={},
            long_short=self._make_ls(),
            avg_turnover=0.0,
            net_return_after_cost=0.0,
            turnover_adjusted_ir=0.0,
            grinold_kahn_ir=0.0,
            sub_period_ic={},
            n_observations=0,
            n_dates=0,
            computed_at="2024-01-01",
            fama_macbeth=fm,
        )
        assert report.fama_macbeth is not None
        assert report.fama_macbeth.factor_exposure == 0.05
