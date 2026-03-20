"""Unit tests for Fama-MacBeth regression (EVAL-EV-2)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_linear_data(
    n_dates: int = 50,
    n_entities: int = 100,
    *,
    seed: int = 42,
    beta_true: float = 0.5,
    alpha_true: float = 0.001,
    noise_std: float = 0.02,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create synthetic factor and return data with a known linear relationship.

    For each date cross-section:
        return_t = alpha + beta * factor_t + noise_t

    """
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

    rows_f: list[dict[str, object]] = []
    rows_r: list[dict[str, object]] = []

    for d in dates:
        factor_vals = rng.standard_normal(n_entities)
        noise = rng.normal(0, noise_std, n_entities)
        return_vals = alpha_true + beta_true * factor_vals + noise

        for i, eid in enumerate(entities):
            rows_f.append(
                {"trade_date": d, "instrument_id": eid, "value": float(factor_vals[i])},
            )
            rows_r.append(
                {
                    "trade_date": d,
                    "instrument_id": eid,
                    "forward_return": float(return_vals[i]),
                },
            )

    return pl.DataFrame(rows_f), pl.DataFrame(rows_r)


def _make_risk_factor_df(
    n_dates: int,
    n_entities: int,
    *,
    seed: int = 99,
) -> pl.DataFrame:
    """Create a synthetic risk factor DataFrame."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

    rows: list[dict[str, object]] = []
    for d in dates:
        vals = rng.standard_normal(n_entities)
        for i, eid in enumerate(entities):
            rows.append(
                {"trade_date": d, "instrument_id": eid, "value": float(vals[i])},
            )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: single-factor Fama-MacBeth
# ---------------------------------------------------------------------------


class TestFamaMacBethSingleFactor:
    """Tests for Fama-MacBeth regression with a single target factor."""

    def test_slope_matches_manual_ols(self) -> None:
        """Single-factor synthetic data: mean slope should be near beta_true."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(
            n_dates=100,
            n_entities=200,
            beta_true=0.5,
            alpha_true=0.001,
            noise_std=0.02,
        )
        result = fama_macbeth(factor_df, return_df)
        assert abs(result.factor_exposure - 0.5) < 0.1

    def test_perfect_linear_relationship(self) -> None:
        """When return = alpha + beta * factor (no noise), slope should be exact."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        n = 50
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
        rows_f: list[dict[str, object]] = []
        rows_r: list[dict[str, object]] = []

        rng = np.random.default_rng(42)
        for d in dates:
            factor_vals = rng.standard_normal(n)
            return_vals = 0.001 + 0.5 * factor_vals
            for i, eid in enumerate(range(1, n + 1)):
                rows_f.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "value": float(factor_vals[i]),
                    },
                )
                rows_r.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "forward_return": float(return_vals[i]),
                    },
                )

        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        result = fama_macbeth(factor_df, return_df)

        assert result.factor_exposure == pytest.approx(0.5, abs=1e-6)
        assert result.exposure_p_value < 0.05  # highly significant

    def test_zero_slope_when_no_relationship(self) -> None:
        """When factor and return are independent, mean slope should be near 0."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        rng = np.random.default_rng(42)
        n_dates = 100
        n_entities = 200
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
        entities = list(range(1, n_entities + 1))

        rows_f: list[dict[str, object]] = []
        rows_r: list[dict[str, object]] = []

        # Generate independent factor and return
        factor_data = rng.standard_normal(n_dates * n_entities)
        return_data = rng.standard_normal(n_dates * n_entities)

        idx = 0
        for d in dates:
            for eid in entities:
                rows_f.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "value": float(factor_data[idx]),
                    },
                )
                rows_r.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "forward_return": float(return_data[idx]),
                    },
                )
                idx += 1

        result = fama_macbeth(pl.DataFrame(rows_f), pl.DataFrame(rows_r))
        assert abs(result.factor_exposure) < 0.1

    def test_t_statistic_sign(self) -> None:
        """t-statistic should have the same sign as factor_exposure."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(
            n_dates=100,
            n_entities=200,
            beta_true=0.5,
        )
        result = fama_macbeth(factor_df, return_df)

        assert result.factor_exposure > 0
        assert result.exposure_t_stat > 0
        assert result.exposure_p_value < 0.05

    def test_negative_beta(self) -> None:
        """Negative true beta should produce negative mean slope."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(
            n_dates=100,
            n_entities=200,
            beta_true=-0.5,
        )
        result = fama_macbeth(factor_df, return_df)

        assert result.factor_exposure < 0
        assert result.exposure_t_stat < 0

    def test_r_squared_avg_in_valid_range(self) -> None:
        """Average R-squared should be between 0 and 1."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=50, n_entities=100)
        result = fama_macbeth(factor_df, return_df)

        assert 0.0 <= result.r_squared_avg <= 1.0

    def test_n_periods_matches_dates(self) -> None:
        """Number of periods should equal the number of unique dates."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=50, n_entities=100)
        result = fama_macbeth(factor_df, return_df)

        assert result.n_periods == 50

    def test_slopes_tuple_format(self) -> None:
        """slopes should be a tuple of (factor_name, mean_slope) tuples."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=10, n_entities=50)
        result = fama_macbeth(factor_df, return_df)

        assert isinstance(result.slopes, tuple)
        assert len(result.slopes) >= 1
        for name, slope in result.slopes:
            assert isinstance(name, str)
            assert isinstance(slope, float)

    def test_exposure_stderr_is_nonnegative(self) -> None:
        """Standard error should be non-negative."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=50, n_entities=100)
        result = fama_macbeth(factor_df, return_df)

        assert result.exposure_stderr >= 0.0


# ---------------------------------------------------------------------------
# Tests: multi-factor Fama-MacBeth
# ---------------------------------------------------------------------------


class TestFamaMacBethMultiFactor:
    """Tests for Fama-MacBeth regression with risk factors."""

    def test_multi_factor_slope_adjustment(self) -> None:
        """Adding a correlated risk factor should change the target slope."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        rng = np.random.default_rng(42)
        n_dates = 100
        n_entities = 200
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
        entities = list(range(1, n_entities + 1))

        rows_f: list[dict[str, object]] = []
        rows_r: list[dict[str, object]] = []
        rows_rf: list[dict[str, object]] = []

        for d in dates:
            # Risk factor drives returns
            rf_vals = rng.standard_normal(n_entities)
            # Target factor is correlated with risk factor
            noise_f = rng.standard_normal(n_entities) * 0.3
            factor_vals = 0.5 * rf_vals + noise_f
            # Returns driven by risk factor, not target factor
            noise_r = rng.normal(0, 0.01, n_entities)
            return_vals = 0.3 * rf_vals + noise_r

            for i, eid in enumerate(entities):
                rows_f.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "value": float(factor_vals[i]),
                    },
                )
                rows_r.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "forward_return": float(return_vals[i]),
                    },
                )
                rows_rf.append(
                    {"trade_date": d, "instrument_id": eid, "value": float(rf_vals[i])},
                )

        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        risk_factor_df = pl.DataFrame(rows_rf)

        result_single = fama_macbeth(factor_df, return_df)
        result_multi = fama_macbeth(
            factor_df,
            return_df,
            risk_factors={"market": risk_factor_df},
        )

        # Target factor slope should decrease when controlling for risk factor
        assert abs(result_multi.factor_exposure) < abs(result_single.factor_exposure)

    def test_multi_factor_slopes_tuple_has_multiple_entries(self) -> None:
        """With risk factors, slopes tuple should contain entries for each factor."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=50, n_entities=100)
        risk_df = _make_risk_factor_df(50, 100, seed=10)

        result = fama_macbeth(
            factor_df,
            return_df,
            risk_factors={"market": risk_df},
        )

        # slopes should contain the target factor
        slope_names = {name for name, _ in result.slopes}
        assert "target" in slope_names
        assert "market" in slope_names

    def test_empty_risk_factors_equivalent_to_none(self) -> None:
        """Empty risk_factors dict should behave like None."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=50, n_entities=100)
        result_none = fama_macbeth(factor_df, return_df, risk_factors=None)
        result_empty = fama_macbeth(factor_df, return_df, risk_factors={})

        assert result_none.factor_exposure == pytest.approx(
            result_empty.factor_exposure,
        )
        assert result_none.exposure_t_stat == pytest.approx(
            result_empty.exposure_t_stat,
        )


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestFamaMacBethEdgeCases:
    """Tests for edge cases in Fama-MacBeth regression."""

    def test_small_cross_section_returns_zero(self) -> None:
        """Fewer entities than min_cross_section should produce zero result."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(
            n_dates=10,
            n_entities=10,
            beta_true=0.5,
        )
        result = fama_macbeth(factor_df, return_df, min_cross_section=30)

        assert result.factor_exposure == 0.0
        assert result.exposure_t_stat == 0.0
        assert result.exposure_p_value == 1.0
        assert result.exposure_stderr == 0.0
        assert result.r_squared_avg == 0.0
        assert result.n_periods == 0

    def test_empty_dataframes_return_zero(self) -> None:
        """Empty input DataFrames should produce zero result."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        return_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "forward_return": pl.Float64,
            },
        )
        result = fama_macbeth(factor_df, return_df)

        assert result.factor_exposure == 0.0
        assert result.n_periods == 0

    def test_single_period_returns_valid_stats(self) -> None:
        """Single period should still produce valid stats."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        factor_df, return_df = _make_linear_data(n_dates=1, n_entities=100)
        result = fama_macbeth(factor_df, return_df)

        assert result.n_periods == 1
        assert isinstance(result.factor_exposure, float)
        assert isinstance(result.exposure_stderr, float)

    def test_custom_column_names(self) -> None:
        """Custom column name parameters should be respected."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth

        rng = np.random.default_rng(42)
        n = 100
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(20)]
        rows_f: list[dict[str, object]] = []
        rows_r: list[dict[str, object]] = []

        for d in dates:
            f = rng.standard_normal(n)
            r = 0.001 + 0.3 * f + rng.normal(0, 0.01, n)
            for i, eid in enumerate(range(1, n + 1)):
                rows_f.append({"dt": d, "eid": eid, "factor": float(f[i])})
                rows_r.append({"dt": d, "eid": eid, "ret": float(r[i])})

        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        from ditto_core.engine.evaluation.metrics import EvaluationColumns

        result = fama_macbeth(
            factor_df,
            return_df,
            columns=EvaluationColumns(
                date="dt",
                entity="eid",
                factor="factor",
                return_col="ret",
            ),
        )

        assert result.n_periods == 20
        assert result.factor_exposure != 0.0

    def test_frozen_dataclass(self) -> None:
        """FamaMacBethResult should be a frozen dataclass."""
        from ditto_core.engine.evaluation.metrics import fama_macbeth
        from ditto_core.engine.evaluation.report import FamaMacBethResult

        factor_df, return_df = _make_linear_data(n_dates=10, n_entities=50)
        result = fama_macbeth(factor_df, return_df)
        assert isinstance(result, FamaMacBethResult)

        with pytest.raises(AttributeError):
            result.factor_exposure = 999.0  # type: ignore[misc]
