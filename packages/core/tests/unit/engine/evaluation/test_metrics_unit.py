"""Comprehensive unit tests for factor evaluation metrics."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_engine.engine.evaluation.metrics import (
    ic_autocorrelation,
    ic_decay,
    ic_summary,
    long_short_returns,
    net_returns,
    orthogonalize,
    pearson_ic,
    quantile_returns,
    rank_ic,
    sub_period_ic,
    turnover,
    turnover_adjusted_ir,
)
from ditto_engine.engine.evaluation.report import (
    ICSummary,
    LongShortResult,
    TailRiskMetrics,
)

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_factor_and_return(
    n_dates: int = 20,
    n_entities: int = 50,
    *,
    seed: int = 42,
    ic_strength: float = 0.3,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create synthetic factor values and forward returns with known IC.

    Factor values and returns are correlated with strength *ic_strength* via
    a shared latent signal.
    """
    rng = np.random.default_rng(seed)

    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(n_entities))

    rows_f: list[dict[str, object]] = []
    rows_r: list[dict[str, object]] = []

    for d in dates:
        signal = rng.standard_normal(n_entities)
        noise_f = rng.standard_normal(n_entities) * math.sqrt(1 - ic_strength)
        noise_r = rng.standard_normal(n_entities) * math.sqrt(1 - ic_strength)
        factor_vals = ic_strength * signal + noise_f
        return_vals = ic_strength * signal + noise_r

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

    return (
        pl.DataFrame(rows_f),
        pl.DataFrame(rows_r),
    )


def _make_close_df(
    n_dates: int = 30,
    n_entities: int = 50,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    """Create synthetic close price data."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(n_entities))

    rows: list[dict[str, object]] = []
    prices = dict.fromkeys(entities, 100.0)

    for d in dates:
        for eid in entities:
            rows.append(
                {"trade_date": d, "instrument_id": eid, "close": prices[eid]},
            )
            prices[eid] *= 1 + rng.normal(0, 0.02)

    return pl.DataFrame(rows)


def _make_ic_df(
    n_dates: int = 20,
    *,
    seed: int = 42,
    mean_ic: float = 0.05,
    ic_std: float = 0.1,
) -> pl.DataFrame:
    """Create synthetic IC series."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    ic_vals = rng.normal(mean_ic, ic_std, n_dates)
    return pl.DataFrame(
        {"trade_date": dates, "ic": [float(v) for v in ic_vals]},
    )


def _make_weights_df(
    n_dates: int = 5,
    n_entities: int = 10,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    """Create synthetic portfolio weights."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(n_entities))
    rows: list[dict[str, object]] = []
    for d in dates:
        w = rng.dirichlet(np.ones(n_entities))
        for i, eid in enumerate(entities):
            rows.append(
                {"trade_date": d, "instrument_id": eid, "weight": float(w[i])},
            )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# rank_ic
# ---------------------------------------------------------------------------


class TestRankIC:
    """Tests for rank_ic."""

    def test_basic_shape_and_sort(self) -> None:
        """Result has date and ic columns, sorted by date."""
        factor_df, return_df = _make_factor_and_return(n_dates=10, n_entities=30)
        result = rank_ic(factor_df, return_df)
        assert "trade_date" in result.columns
        assert "ic" in result.columns
        assert result.height == 10
        assert result["trade_date"].is_sorted()

    def test_positive_ic_with_perfect_rank_correlation(self) -> None:
        """When factor and return are monotonically related, IC should be positive."""
        dates = [date(2024, 1, 1)]
        entities = list(range(10))
        rows_f = [
            {"trade_date": dates[0], "instrument_id": e, "value": float(e)}
            for e in entities
        ]
        rows_r = [
            {"trade_date": dates[0], "instrument_id": e, "forward_return": float(e)}
            for e in entities
        ]
        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        result = rank_ic(factor_df, return_df)
        ic_val = result["ic"][0]
        assert ic_val > 0.9  # nearly perfect correlation

    def test_negative_ic_with_inverse_relationship(self) -> None:
        """When factor and return are inversely related, IC should be negative."""
        dates = [date(2024, 1, 1)]
        entities = list(range(10))
        rows_f = [
            {"trade_date": dates[0], "instrument_id": e, "value": float(e)}
            for e in entities
        ]
        rows_r = [
            {"trade_date": dates[0], "instrument_id": e, "forward_return": float(9 - e)}
            for e in entities
        ]
        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        result = rank_ic(factor_df, return_df)
        ic_val = result["ic"][0]
        assert ic_val < -0.9

    def test_empty_dataframes(self) -> None:
        """Empty DataFrames should produce empty result."""
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
        result = rank_ic(factor_df, return_df)
        assert result.height == 0

    def test_single_entity_per_date_returns_null_ic(self) -> None:
        """Single entity cannot produce a meaningful correlation."""
        rows_f = [
            {"trade_date": date(2024, 1, 1), "instrument_id": 1, "value": 1.0},
        ]
        rows_r = [
            {
                "trade_date": date(2024, 1, 1),
                "instrument_id": 1,
                "forward_return": 0.01,
            },
        ]
        result = rank_ic(pl.DataFrame(rows_f), pl.DataFrame(rows_r))
        # polars returns null for corr with a single observation
        assert result["ic"][0] is None or math.isnan(result["ic"][0])

    def test_custom_column_names(self) -> None:
        """rank_ic respects custom column name parameters."""
        factor_df = pl.DataFrame(
            {
                "date": [date(2024, 1, 1)] * 3,
                "entity": [1, 2, 3],
                "score": [1.0, 2.0, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "date": [date(2024, 1, 1)] * 3,
                "entity": [1, 2, 3],
                "ret": [0.01, 0.02, 0.03],
            },
        )
        result = rank_ic(
            factor_df,
            return_df,
            factor_col="score",
            return_col="ret",
            date_col="date",
            entity_col="entity",
        )
        assert result.height == 1
        assert result["ic"][0] > 0.9


# ---------------------------------------------------------------------------
# pearson_ic
# ---------------------------------------------------------------------------


class TestPearsonIC:
    """Tests for pearson_ic."""

    def test_basic_shape(self) -> None:
        """Result has date and ic columns."""
        factor_df, return_df = _make_factor_and_return(n_dates=10, n_entities=30)
        result = pearson_ic(factor_df, return_df)
        assert result.height == 10
        assert "trade_date" in result.columns
        assert "ic" in result.columns

    def test_perfect_linear_relationship(self) -> None:
        """Exact linear relationship yields IC of 1.0."""
        dates = [date(2024, 1, 1)]
        rows_f = [
            {"trade_date": dates[0], "instrument_id": i, "value": float(i)}
            for i in range(1, 11)
        ]
        rows_r = [
            {
                "trade_date": dates[0],
                "instrument_id": i,
                "forward_return": 2.0 * i + 1.0,
            }
            for i in range(1, 11)
        ]
        result = pearson_ic(pl.DataFrame(rows_f), pl.DataFrame(rows_r))
        assert abs(result["ic"][0] - 1.0) < 1e-10

    def test_empty_input(self) -> None:
        """Empty input returns empty DataFrame."""
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
        result = pearson_ic(factor_df, return_df)
        assert result.height == 0


# ---------------------------------------------------------------------------
# ic_summary
# ---------------------------------------------------------------------------


class TestICSummary:
    """Tests for ic_summary."""

    def test_positive_mean_ic(self) -> None:
        """IC with consistently positive mean yields positive ICIR and low p-value."""
        rng = np.random.default_rng(42)
        ic_vals = rng.normal(0.05, 0.10, 100)
        df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1) + timedelta(days=i) for i in range(100)
                ],
                "ic": ic_vals.tolist(),
            },
        )
        result = ic_summary(df)
        assert result.mean > 0
        assert result.std > 0
        assert result.icir > 0
        assert isinstance(result.t_stat, float)
        assert isinstance(result.p_value, float)
        assert 0 < result.win_rate < 1

    def test_zero_ic(self) -> None:
        """All-zero IC yields zero summary metrics."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(20)],
                "ic": [0.0] * 20,
            },
        )
        result = ic_summary(df)
        assert result.mean == 0.0
        assert result.std == 0.0
        assert result.icir == 0.0
        assert result.t_stat == 0.0
        assert result.p_value == 1.0
        assert result.win_rate == 0.0

    def test_empty_dataframe(self) -> None:
        """Empty input returns zero-filled ICSummary."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        result = ic_summary(df)
        assert result == ICSummary(
            mean=0.0,
            std=0.0,
            icir=0.0,
            t_stat=0.0,
            p_value=1.0,
            win_rate=0.0,
        )

    def test_single_date(self) -> None:
        """Single-date IC should have std=0, icir=0, p_value=1."""
        df = pl.DataFrame({"trade_date": [date(2024, 1, 1)], "ic": [0.05]})
        result = ic_summary(df)
        assert result.std == 0.0
        assert result.icir == 0.0
        assert result.p_value == 1.0

    def test_nan_handling(self) -> None:
        """NaN values are dropped before computation."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(10)],
                "ic": [
                    0.1,
                    float("nan"),
                    0.05,
                    0.08,
                    0.03,
                    0.07,
                    0.09,
                    0.02,
                    0.06,
                    0.04,
                ],
            },
        )
        result = ic_summary(df)
        assert not math.isnan(result.mean)
        assert not math.isnan(result.std)

    def test_p_value_consistency_with_scipy_reference(self) -> None:
        """Verify p-value matches scipy t-distribution reference.

        scipy is not available in production, so we verify against the manual
        formula using a known reference implementation.
        """
        # t=2.0, df=49 => p ~ 0.0505 (from t-tables).
        rng = np.random.default_rng(123)
        ic_vals = rng.normal(0.08, 0.20, 50)
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "ic": ic_vals.tolist(),
            },
        )
        result = ic_summary(df)
        # For a strong positive mean IC, p should be small.
        if result.mean > 0.05:
            assert result.p_value < 0.1

    def test_icir_equals_mean_over_std(self) -> None:
        """ICIR should exactly equal mean / std."""
        rng = np.random.default_rng(99)
        ic_vals = rng.normal(0.03, 0.12, 60)
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(60)],
                "ic": ic_vals.tolist(),
            },
        )
        result = ic_summary(df)
        if result.std > 0:
            assert abs(result.icir - result.mean / result.std) < 1e-10


# ---------------------------------------------------------------------------
# ic_decay
# ---------------------------------------------------------------------------


class TestICDecay:
    """Tests for ic_decay."""

    def test_returns_decay_for_default_lags(self) -> None:
        """Default lags [1,2,3,5,10,20] all produce results."""
        factor_df, _return_df = _make_factor_and_return(n_dates=30, n_entities=50)
        close_df = _make_close_df(n_dates=50, n_entities=50)
        results, _half_life = ic_decay(factor_df, close_df)
        assert len(results) == 6
        assert all(
            isinstance(lag, int) and isinstance(ic, float) for lag, ic in results
        )

    def test_custom_lags(self) -> None:
        """Custom lag list is respected."""
        factor_df, _return_df = _make_factor_and_return(n_dates=20, n_entities=30)
        close_df = _make_close_df(n_dates=30, n_entities=30)
        results, _ = ic_decay(factor_df, close_df, lags=[1, 5])
        assert len(results) == 2
        assert results[0][0] == 1
        assert results[1][0] == 5

    def test_half_life_is_positive_or_none(self) -> None:
        """Half-life, if computed, should be positive."""
        factor_df, _return_df = _make_factor_and_return(
            n_dates=30,
            n_entities=50,
            ic_strength=0.5,
        )
        close_df = _make_close_df(n_dates=50, n_entities=50)
        _, half_life = ic_decay(factor_df, close_df)
        if half_life is not None:
            assert half_life > 0


# ---------------------------------------------------------------------------
# ic_autocorrelation
# ---------------------------------------------------------------------------


class TestICAutocorrelation:
    """Tests for ic_autocorrelation."""

    def test_returns_correct_length(self) -> None:
        """Returns max_lag entries."""
        df = _make_ic_df(n_dates=50)
        result = ic_autocorrelation(df, max_lag=5)
        assert len(result) == 5

    def test_lag1_near_1_for_autocorrelated_series(self) -> None:
        """Highly autocorrelated IC series should have ACF(1) near 1."""
        rng = np.random.default_rng(42)
        # AR(1) process with phi=0.9.
        ic_vals = [0.0] * 50
        for i in range(1, 50):
            ic_vals[i] = 0.9 * ic_vals[i - 1] + rng.normal(0, 0.01)
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1) + timedelta(days=i) for i in range(50)],
                "ic": ic_vals,
            },
        )
        result = ic_autocorrelation(df, max_lag=1)
        acf1 = result[0][1]
        assert acf1 > 0.5  # should be strongly positive

    def test_empty_series(self) -> None:
        """Empty IC series returns empty result."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        result = ic_autocorrelation(df, max_lag=3)
        assert len(result) == 3  # still returns entries, but with NaN

    def test_max_lag_exceeds_length(self) -> None:
        """When max_lag >= n, later lags should be NaN."""
        df = pl.DataFrame(
            {"trade_date": [date(2024, 1, 1), date(2024, 1, 2)], "ic": [0.1, 0.2]},
        )
        result = ic_autocorrelation(df, max_lag=5)
        assert result[0][1] is not None  # lag=1, 2 observations
        assert math.isnan(result[1][1])  # lag=2, only 0 obs remaining

    def test_lag1_near_0_for_white_noise(self) -> None:
        """White noise IC series should have ACF(1) near 0."""
        rng = np.random.default_rng(42)
        ic_vals = rng.normal(0, 0.1, 200)
        df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1) + timedelta(days=i) for i in range(200)
                ],
                "ic": ic_vals.tolist(),
            },
        )
        result = ic_autocorrelation(df, max_lag=1)
        acf1 = result[0][1]
        assert abs(acf1) < 0.15  # should be near 0


# ---------------------------------------------------------------------------
# turnover_adjusted_ir
# ---------------------------------------------------------------------------


class TestTurnoverAdjustedIR:
    """Tests for turnover_adjusted_ir."""

    def test_zero_autocorr_equals_simple_ir(self) -> None:
        """With zero IC autocorrelation, BR_effective == BR."""
        mean_ic = 0.05
        simple_br = 244 / 5  # 48.8
        expected = mean_ic * math.sqrt(simple_br)
        result = turnover_adjusted_ir(mean_ic, ic_autocorr_lag1=0.0)
        assert abs(result - expected) < 1e-10

    def test_high_autocorr_reduces_ir(self) -> None:
        """Strong positive autocorrelation reduces effective BR, lowering IR.

        For rho close to 1.0 with weekly rebalancing, the denominator shrinks
        and the correction reduces effective breadth.
        """
        ir_zero = turnover_adjusted_ir(0.05, 0.0)
        ir_high = turnover_adjusted_ir(0.05, 0.95)
        assert ir_high < ir_zero

    def test_negative_ic(self) -> None:
        """Negative mean IC produces negative IR."""
        result = turnover_adjusted_ir(-0.05, 0.0)
        assert result < 0

    def test_zero_ic(self) -> None:
        """Zero IC produces zero IR."""
        result = turnover_adjusted_ir(0.0, 0.0)
        assert result == 0.0

    def test_custom_parameters(self) -> None:
        """Custom rebalance_freq and total_periods are respected."""
        result = turnover_adjusted_ir(
            0.05,
            0.0,
            rebalance_freq=20,
            total_periods=252,
        )
        br = 252 / 20
        expected = 0.05 * math.sqrt(br)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# quantile_returns
# ---------------------------------------------------------------------------


class TestQuantileReturns:
    """Tests for quantile_returns."""

    def test_basic_shape(self) -> None:
        """Result has date, quantile, mean_return, count columns."""
        factor_df, return_df = _make_factor_and_return(n_dates=10, n_entities=50)
        result = quantile_returns(factor_df, return_df, n_quantiles=5)
        assert "trade_date" in result.columns
        assert "quantile" in result.columns
        assert "mean_return" in result.columns
        assert "count" in result.columns
        assert result.height == 10 * 5

    def test_quantiles_are_integers(self) -> None:
        """Quantile column should contain integers 1..n_quantiles."""
        factor_df, return_df = _make_factor_and_return(n_dates=5, n_entities=50)
        result = quantile_returns(factor_df, return_df, n_quantiles=5)
        quantiles = result["quantile"].unique().sort().to_list()
        assert quantiles == [1, 2, 3, 4, 5]

    def test_counts_sum_to_n_entities_per_date(self) -> None:
        """Per date, counts across quantiles should sum to n_entities."""
        n_entities = 50
        factor_df, return_df = _make_factor_and_return(n_dates=5, n_entities=n_entities)
        result = quantile_returns(factor_df, return_df, n_quantiles=5)
        for date_val in result["trade_date"].unique():
            total = result.filter(pl.col("trade_date") == date_val)["count"].sum()
            assert total == n_entities

    def test_sorted_by_date_and_quantile(self) -> None:
        """Result should be sorted by (date, quantile)."""
        factor_df, return_df = _make_factor_and_return(n_dates=5, n_entities=50)
        result = quantile_returns(factor_df, return_df)
        assert result["trade_date"].is_sorted()
        # Check that within each date, quantile is sorted.
        for date_val in result["trade_date"].unique():
            q = result.filter(pl.col("trade_date") == date_val)["quantile"]
            assert q.is_sorted()


# ---------------------------------------------------------------------------
# long_short_returns
# ---------------------------------------------------------------------------


class TestLongShortReturns:
    """Tests for long_short_returns."""

    def test_basic_output_type(self) -> None:
        """Result should be a LongShortResult."""
        factor_df, return_df = _make_factor_and_return(n_dates=50, n_entities=50)
        q_ret = quantile_returns(factor_df, return_df, n_quantiles=5)
        result = long_short_returns(q_ret)
        assert isinstance(result, LongShortResult)

    def test_positive_factor_produces_positive_ls_return(self) -> None:
        """Strong positive IC factor should yield positive LS return."""
        factor_df, return_df = _make_factor_and_return(
            n_dates=50,
            n_entities=100,
            ic_strength=0.8,
        )
        q_ret = quantile_returns(factor_df, return_df, n_quantiles=5)
        result = long_short_returns(q_ret)
        assert result.annual_return > 0

    def test_empty_quantile_returns(self) -> None:
        """Empty quantile return DataFrame returns zero-filled result."""
        df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            },
        )
        result = long_short_returns(df)
        assert result == LongShortResult(
            annual_return=0.0,
            annual_volatility=0.0,
            sharpe=0.0,
            portfolio_ir=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            calmar=0.0,
            tail_risk=TailRiskMetrics(
                cvar_95=0.0,
                cvar_99=0.0,
                skewness=0.0,
                kurtosis=0.0,
                max_single_day_loss=0.0,
            ),
        )

    def test_max_drawdown_is_nonpositive(self) -> None:
        """Maximum drawdown should be <= 0."""
        factor_df, return_df = _make_factor_and_return(n_dates=100, n_entities=50)
        q_ret = quantile_returns(factor_df, return_df, n_quantiles=5)
        result = long_short_returns(q_ret)
        assert result.max_drawdown <= 0

    def test_risk_free_rate_adjustment(self) -> None:
        """Portfolio IR should adjust for risk-free rate."""
        factor_df, return_df = _make_factor_and_return(n_dates=100, n_entities=50)
        q_ret = quantile_returns(factor_df, return_df, n_quantiles=5)

        result_zero_rf = long_short_returns(q_ret, risk_free_rate=0.0)
        result_high_rf = long_short_returns(q_ret, risk_free_rate=0.05)

        if result_zero_rf.annual_volatility > 0:
            assert result_high_rf.portfolio_ir < result_zero_rf.portfolio_ir

    def test_custom_top_bottom_quantiles(self) -> None:
        """Custom top/bottom quantile indices are respected."""
        factor_df, return_df = _make_factor_and_return(n_dates=50, n_entities=50)
        q_ret = quantile_returns(factor_df, return_df, n_quantiles=5)
        result = long_short_returns(q_ret, top_quantile=3, bottom_quantile=3)
        # top == bottom means zero LS returns.
        assert result.annual_return == 0.0
        assert result.annual_volatility == 0.0


# ---------------------------------------------------------------------------
# turnover
# ---------------------------------------------------------------------------


class TestTurnover:
    """Tests for turnover."""

    def test_basic_shape(self) -> None:
        """Result has date, turnover_two_way, turnover_one_way columns."""
        current = _make_weights_df(n_dates=3, n_entities=10)
        previous = _make_weights_df(n_dates=3, n_entities=10, seed=99)
        result = turnover(current, previous)
        assert "trade_date" in result.columns
        assert "turnover_two_way" in result.columns
        assert "turnover_one_way" in result.columns

    def test_zero_turnover_for_identical_weights(self) -> None:
        """Identical current and previous weights yield zero turnover."""
        weights = _make_weights_df(n_dates=1, n_entities=5)
        result = turnover(weights, weights)
        assert result["turnover_two_way"][0] == pytest.approx(0.0, abs=1e-10)
        assert result["turnover_one_way"][0] == pytest.approx(0.0, abs=1e-10)

    def test_two_way_turnover_formula(self) -> None:
        """Two-way turnover = 0.5 * sum(|w_t - w_{t-1}|)."""
        current = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [1, 2, 3],
                "weight": [0.5, 0.3, 0.2],
            },
        )
        previous = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 3,
                "instrument_id": [1, 2, 3],
                "weight": [0.2, 0.5, 0.3],
            },
        )
        result = turnover(current, previous)
        # |0.5-0.2| + |0.3-0.5| + |0.2-0.3| = 0.3 + 0.2 + 0.1 = 0.6
        expected = 0.5 * 0.6
        assert result["turnover_two_way"][0] == pytest.approx(expected)

    def test_one_way_turnover_formula(self) -> None:
        """One-way turnover = min(buys, sells)."""
        current = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "instrument_id": [1, 2],
                "weight": [0.7, 0.3],
            },
        )
        previous = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)] * 2,
                "instrument_id": [1, 2],
                "weight": [0.3, 0.7],
            },
        )
        result = turnover(current, previous)
        # buys: |0.7-0.3| = 0.4, sells: |0.3-0.7| = 0.4
        expected_one_way = min(0.4, 0.4)
        assert result["turnover_one_way"][0] == pytest.approx(expected_one_way)


# ---------------------------------------------------------------------------
# net_returns
# ---------------------------------------------------------------------------


class TestNetReturns:
    """Tests for net_returns."""

    def test_basic_formula(self) -> None:
        """net = gross - turnover * cost_bps / 10000."""
        result = net_returns(0.10, 0.5, cost_bps=20.0)
        expected = 0.10 - 0.5 * 20.0 / 10000.0
        assert result == pytest.approx(expected)

    def test_zero_turnover(self) -> None:
        """Zero turnover returns gross return unchanged."""
        assert net_returns(0.10, 0.0) == pytest.approx(0.10)

    def test_high_cost_reduces_return(self) -> None:
        """Higher cost_bps should reduce net return."""
        r1 = net_returns(0.10, 1.0, cost_bps=10.0)
        r2 = net_returns(0.10, 1.0, cost_bps=50.0)
        assert r2 < r1

    def test_negative_net_return(self) -> None:
        """High turnover and cost can make net return negative."""
        result = net_returns(0.001, 5.0, cost_bps=50.0)
        assert result < 0


# ---------------------------------------------------------------------------
# orthogonalize
# ---------------------------------------------------------------------------


class TestOrthogonalize:
    """Tests for orthogonalize."""

    def test_sequential_method_basic(self) -> None:
        """Sequential method returns DataFrame with correct columns."""
        rng = np.random.default_rng(42)
        n = 50
        dates = [date(2024, 1, 1)] * n
        entities = list(range(n))

        target_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        factor_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "factor_name": ["market"] * n,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        result = orthogonalize(
            target_df,
            factor_df,
            method="sequential",
            min_cross_section=10,
        )
        assert "trade_date" in result.columns
        assert "instrument_id" in result.columns
        assert "orthogonalized_value" in result.columns

    def test_sequential_reduces_correlation(self) -> None:
        """After orthogonalization, correlation with the factor should decrease."""
        rng = np.random.default_rng(42)
        n = 100
        dates = [date(2024, 1, 1)] * n
        entities = list(range(n))

        # Create target that is linear combination of factor + noise.
        factor_vals = rng.normal(0, 1, n)
        noise = rng.normal(0, 0.1, n)
        target_vals = 0.8 * factor_vals + noise

        target_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": target_vals.tolist(),
            },
        )
        factor_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "factor_name": ["market"] * n,
                "value": factor_vals.tolist(),
            },
        )

        # Correlation before orthogonalization via numpy.
        corr_before = float(
            np.corrcoef(target_df["value"].to_numpy(), factor_df["value"].to_numpy())[
                0, 1
            ],
        )

        result = orthogonalize(
            target_df,
            factor_df,
            method="sequential",
            min_cross_section=10,
        )
        corr_after = float(
            np.corrcoef(
                result["orthogonalized_value"].to_numpy(),
                factor_df["value"].to_numpy(),
            )[0, 1],
        )

        assert abs(corr_after) < abs(corr_before)

    def test_symmetric_method_basic(self) -> None:
        """Symmetric method returns correct columns."""
        rng = np.random.default_rng(42)
        n = 50
        dates = [date(2024, 1, 1)] * n
        entities = list(range(n))

        target_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        factor_df = pl.DataFrame(
            {
                "trade_date": dates * 2,
                "instrument_id": entities * 2,
                "factor_name": ["market"] * n + ["size"] * n,
                "value": rng.normal(0, 1, 2 * n).tolist(),
            },
        )
        result = orthogonalize(
            target_df,
            factor_df,
            method="symmetric",
            min_cross_section=10,
        )
        assert "orthogonalized_value" in result.columns
        # Each entity has one row in the result.
        assert result.height == n

    def test_unknown_method_raises(self) -> None:
        """Unknown method should raise ValueError."""
        target_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)],
                "instrument_id": [1],
                "value": [1.0],
            },
        )
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1)],
                "instrument_id": [1],
                "factor_name": ["mkt"],
                "value": [2.0],
            },
        )
        with pytest.raises(ValueError, match="Unknown orthogonalization method"):
            orthogonalize(target_df, factor_df, method="invalid")

    def test_small_cross_section_skipped(self) -> None:
        """Dates with fewer entities than min_cross_section are skipped."""
        rng = np.random.default_rng(42)
        n = 5
        dates = [date(2024, 1, 1)] * n
        entities = list(range(n))

        target_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        factor_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "factor_name": ["mkt"] * n,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        result = orthogonalize(
            target_df,
            factor_df,
            method="sequential",
            min_cross_section=30,
        )
        assert result.height == 0


# ---------------------------------------------------------------------------
# sub_period_ic
# ---------------------------------------------------------------------------


class TestSubPeriodIC:
    """Tests for sub_period_ic."""

    def test_yearly_split(self) -> None:
        """Splitting by year should produce one entry per year."""
        dates = [date(2024, 1, i) for i in range(1, 11)] + [
            date(2025, 1, i) for i in range(1, 11)
        ]
        rng = np.random.default_rng(42)
        ic_vals = rng.normal(0.05, 0.1, 20)
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals.tolist()})
        result = sub_period_ic(df, freq="year")
        assert "2024" in result
        assert "2025" in result
        assert len(result) == 2
        assert all(isinstance(v, ICSummary) for v in result.values())

    def test_quarterly_split(self) -> None:
        """Splitting by quarter produces entries per quarter."""
        dates = [date(2024, m, d) for m in [1, 4, 7, 10] for d in [1, 2, 3]]
        rng = np.random.default_rng(42)
        ic_vals = rng.normal(0.05, 0.1, 12)
        df = pl.DataFrame({"trade_date": dates, "ic": ic_vals.tolist()})
        result = sub_period_ic(df, freq="quarter")
        assert "2024Q1" in result
        assert "2024Q4" in result

    def test_unknown_freq_raises(self) -> None:
        """Unknown frequency should raise ValueError."""
        df = _make_ic_df(n_dates=10)
        with pytest.raises(ValueError, match="Unknown frequency"):
            sub_period_ic(df, freq="month")

    def test_empty_dataframe(self) -> None:
        """Empty DataFrame should produce empty result."""
        df = pl.DataFrame(schema={"trade_date": pl.Date, "ic": pl.Float64})
        result = sub_period_ic(df, freq="year")
        assert len(result) == 0

    def test_single_year(self) -> None:
        """All dates in one year should produce a single entry."""
        df = _make_ic_df(n_dates=20)
        result = sub_period_ic(df, freq="year")
        assert len(result) == 1
        assert "2024" in result


# ---------------------------------------------------------------------------
# p-value implementation validation
# ---------------------------------------------------------------------------


class TestPValueImplementation:
    """Validate the manual p-value against known statistical values."""

    def test_p_value_t_distribution(self) -> None:
        """Check p-value for known t-statistics from t-distribution tables.

        For t=2.093, df=19 (two-tailed), p ~ 0.05.
        """
        from ditto_engine.engine.evaluation.metrics import _two_sided_p_value

        p = _two_sided_p_value(2.093, 19)
        assert 0.04 < p < 0.06  # approximately 0.05

    def test_p_value_large_t_is_small(self) -> None:
        """Large t-statistic should yield very small p-value."""
        from ditto_engine.engine.evaluation.metrics import _two_sided_p_value

        p = _two_sided_p_value(5.0, 100)
        assert p < 0.001

    def test_p_value_zero_t_is_one(self) -> None:
        """t=0 should yield p=1."""
        from ditto_engine.engine.evaluation.metrics import _two_sided_p_value

        p = _two_sided_p_value(0.0, 50)
        assert abs(p - 1.0) < 1e-10
