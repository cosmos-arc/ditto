"""Unit tests for evaluation/metrics/_math.py helpers.

Tests scalar_to_float, two_sided_p_value, regularized_incomplete_beta,
fit_ic_half_life, log_gamma, and EvaluationColumns.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ditto_features.evaluation.metrics._math import (
    MIN_OBS_FOR_OLS,
    MIN_POINTS_FOR_HALF_LIFE_FIT,
    MIN_TAIL_OBSERVATIONS,
    MIN_TRANSITIONS_FOR_MATRIX,
    EvaluationColumns,
    fit_ic_half_life,
    log_gamma,
    regularized_incomplete_beta,
    scalar_to_float,
    two_sided_p_value,
)

# ---------------------------------------------------------------------------
# scalar_to_float
# ---------------------------------------------------------------------------


class TestScalarToFloat:
    """Tests for scalar_to_float."""

    def test_none_returns_default(self) -> None:
        """None input returns the default value."""
        assert scalar_to_float(None) == 0.0
        assert scalar_to_float(None, default=1.5) == 1.5

    def test_bool_to_float(self) -> None:
        """Boolean is converted to float."""
        assert scalar_to_float(True) == 1.0
        assert scalar_to_float(False) == 0.0

    def test_int_to_float(self) -> None:
        """Integer is converted to float."""
        assert scalar_to_float(42) == 42.0
        assert scalar_to_float(-7) == -7.0

    def test_float_passthrough(self) -> None:
        """Float is returned as-is."""
        assert scalar_to_float(3.14) == pytest.approx(3.14)

    def test_decimal_to_float(self) -> None:
        """Decimal is converted to float."""
        assert scalar_to_float(Decimal("2.5")) == pytest.approx(2.5)

    def test_timedelta_to_seconds(self) -> None:
        """timedelta is converted to total seconds."""
        td = timedelta(hours=1, minutes=30)
        assert scalar_to_float(td) == pytest.approx(5400.0)

    def test_date_to_ordinal(self) -> None:
        """date is converted to ordinal float."""
        d = date(2024, 1, 1)
        assert scalar_to_float(d) == float(d.toordinal())

    def test_datetime_to_timestamp(self) -> None:
        """datetime is converted to timestamp."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = scalar_to_float(dt)
        assert isinstance(result, float)
        assert result > 0

    def test_time_to_seconds(self) -> None:
        """time is converted to total seconds."""
        t = time(2, 30, 45)
        expected = 2 * 3600 + 30 * 60 + 45
        assert scalar_to_float(t) == pytest.approx(float(expected))

    def test_string_numeric(self) -> None:
        """Numeric string is converted to float."""
        assert scalar_to_float("3.14") == pytest.approx(3.14)
        assert scalar_to_float("42") == pytest.approx(42.0)

    def test_string_non_numeric(self) -> None:
        """Non-numeric string returns default."""
        assert scalar_to_float("hello") == 0.0
        assert scalar_to_float("hello", default=1.0) == 1.0

    def test_bytes_numeric(self) -> None:
        """Numeric bytes is converted to float."""
        assert scalar_to_float(b"3.14") == pytest.approx(3.14)

    def test_list_returns_default(self) -> None:
        """List returns default (not convertible)."""
        assert scalar_to_float([1, 2, 3]) == 0.0


# ---------------------------------------------------------------------------
# two_sided_p_value
# ---------------------------------------------------------------------------


class TestTwoSidedPValue:
    """Tests for two_sided_p_value."""

    def test_zero_t_returns_one(self) -> None:
        """t=0 means p=1 (no evidence against null)."""
        assert two_sided_p_value(0.0, 10) == pytest.approx(1.0, abs=1e-10)

    def test_large_t_returns_small_p(self) -> None:
        """Large |t| produces very small p-value."""
        assert two_sided_p_value(10.0, 100) < 0.001

    def test_symmetry(self) -> None:
        """p-value is symmetric: p(t) == p(-t)."""
        p1 = two_sided_p_value(2.0, 50)
        p2 = two_sided_p_value(-2.0, 50)
        assert p1 == pytest.approx(p2, abs=1e-10)

    @pytest.mark.parametrize("df", [1, 5, 10, 50, 100])
    def test_p_value_in_zero_one(self, df: int) -> None:
        """p-value is always in [0, 1]."""
        p = two_sided_p_value(1.5, df)
        assert 0.0 <= p <= 1.0

    def test_classical_t_table_value(self) -> None:
        """For t=2.093, df=19, p ~ 0.05 (from t-tables)."""
        p = two_sided_p_value(2.093, 19)
        assert 0.04 < p < 0.06


# ---------------------------------------------------------------------------
# regularized_incomplete_beta
# ---------------------------------------------------------------------------


class TestRegularizedIncompleteBeta:
    """Tests for regularized_incomplete_beta."""

    def test_x_zero(self) -> None:
        """x=0 returns 0."""
        assert regularized_incomplete_beta(0.0, 1.0, 1.0) == 0.0

    def test_x_one(self) -> None:
        """x=1 returns 1."""
        assert regularized_incomplete_beta(1.0, 1.0, 1.0) == 1.0

    def test_symmetry_b1(self) -> None:
        """I_x(a, 1) should equal x^a for simple cases."""
        result = regularized_incomplete_beta(0.5, 2.0, 1.0)
        assert result == pytest.approx(0.5**2.0, abs=1e-6)

    def test_monotonic_in_x(self) -> None:
        """Result increases with x."""
        a, b = 2.0, 3.0
        prev = 0.0
        for x in [0.1, 0.3, 0.5, 0.7, 0.9]:
            current = regularized_incomplete_beta(x, a, b)
            assert current >= prev
            prev = current


# ---------------------------------------------------------------------------
# log_gamma
# ---------------------------------------------------------------------------


class TestLogGamma:
    """Tests for log_gamma."""

    def test_known_values(self) -> None:
        """log(Gamma(1)) = 0, log(Gamma(2)) = 0, log(Gamma(3)) = log(2)."""
        assert log_gamma(1.0) == pytest.approx(0.0, abs=1e-10)
        assert log_gamma(2.0) == pytest.approx(0.0, abs=1e-10)
        assert log_gamma(3.0) == pytest.approx(math.log(2.0), abs=1e-10)
        assert log_gamma(4.0) == pytest.approx(math.log(6.0), abs=1e-10)

    def test_reflection_for_small_x(self) -> None:
        """Reflection formula used for x < 0.5."""
        # Gamma(0.5) = sqrt(pi)
        assert log_gamma(0.5) == pytest.approx(math.log(math.sqrt(math.pi)), abs=1e-6)

    def test_raises_for_non_positive(self) -> None:
        """log_gamma raises ValueError for x <= 0."""
        with pytest.raises(ValueError, match="x > 0"):
            log_gamma(0.0)
        with pytest.raises(ValueError, match="x > 0"):
            log_gamma(-1.0)

    @pytest.mark.parametrize("x", [0.5, 1.0, 1.5, 2.0, 5.0, 10.0, 100.0])
    def test_positive_result_for_x_gt_1(self, x: float) -> None:
        """log_gamma(x) is positive for x > ~1.46."""
        result = log_gamma(x)
        assert isinstance(result, float)
        assert math.isfinite(result)


# ---------------------------------------------------------------------------
# fit_ic_half_life
# ---------------------------------------------------------------------------


class TestFitIcHalfLife:
    """Tests for fit_ic_half_life."""

    def test_too_few_points_returns_none(self) -> None:
        """Fewer than MIN_POINTS points returns None."""
        assert fit_ic_half_life([(1, 0.05)]) is None
        assert fit_ic_half_life([]) is None

    def test_all_negative_ic_returns_none(self) -> None:
        """All negative IC values returns None (no valid points)."""
        result = fit_ic_half_life([(1, -0.1), (5, -0.05)])
        assert result is None

    def test_decaying_ic_produces_half_life(self) -> None:
        """Decaying IC series produces a positive half-life."""
        decay_results = [
            (1, 0.10),
            (2, 0.08),
            (5, 0.04),
            (10, 0.02),
            (20, 0.01),
        ]
        result = fit_ic_half_life(decay_results)
        assert result is not None
        assert result > 0

    def test_increasing_ic_returns_none(self) -> None:
        """Non-decaying (increasing) IC returns None."""
        growth_results = [
            (1, 0.01),
            (5, 0.05),
            (10, 0.10),
        ]
        result = fit_ic_half_life(growth_results)
        assert result is None

    def test_constant_ic_returns_none(self) -> None:
        """Constant IC (zero variance in log(IC^2)) returns None."""
        constant_results = [
            (1, 0.05),
            (5, 0.05),
        ]
        result = fit_ic_half_life(constant_results)
        assert result is None

    def test_two_valid_points_minimum(self) -> None:
        """Minimum 2 valid points can produce a half-life."""
        result = fit_ic_half_life([(1, 0.10), (5, 0.02)])
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests that constants have expected values."""

    def test_min_obs_for_ols(self) -> None:
        """MIN_OBS_FOR_OLS should be 30."""
        assert MIN_OBS_FOR_OLS == 30

    def test_min_tail_observations(self) -> None:
        """MIN_TAIL_OBSERVATIONS should be 2."""
        assert MIN_TAIL_OBSERVATIONS == 2

    def test_min_transitions_for_matrix(self) -> None:
        """MIN_TRANSITIONS_FOR_MATRIX should be 2."""
        assert MIN_TRANSITIONS_FOR_MATRIX == 2

    def test_min_points_for_half_life_fit(self) -> None:
        """MIN_POINTS_FOR_HALF_LIFE_FIT should be 2."""
        assert MIN_POINTS_FOR_HALF_LIFE_FIT == 2


# ---------------------------------------------------------------------------
# EvaluationColumns
# ---------------------------------------------------------------------------


class TestEvaluationColumns:
    """Tests for EvaluationColumns dataclass."""

    def test_default_values(self) -> None:
        """Default column names match standard convention."""
        cols = EvaluationColumns()
        assert cols.date == "trade_date"
        assert cols.entity == "instrument_id"
        assert cols.factor == "value"
        assert cols.return_col == "forward_return"

    def test_custom_values(self) -> None:
        """Custom column names are accepted."""
        cols = EvaluationColumns(
            date="dt", entity="asset", factor="score", return_col="ret"
        )
        assert cols.date == "dt"
        assert cols.entity == "asset"
        assert cols.factor == "score"
        assert cols.return_col == "ret"

    def test_frozen(self) -> None:
        """EvaluationColumns is frozen."""
        cols = EvaluationColumns()
        with pytest.raises(AttributeError):
            cols.date = "other"  # type: ignore[misc]
