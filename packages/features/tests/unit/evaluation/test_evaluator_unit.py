"""Unit tests for FactorEvaluator and its private helpers."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.evaluation.evaluator import (
    EvaluationConfig,
    FactorEvaluator,
    _compute_ic_decay_safe,
    _compute_quantile_annual_returns,
    _empty_report,
    _estimate_avg_turnover,
    _prepare_data,
    _resolve_period,
)
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    ICSummary,
    LongShortResult,
)

type FactorReturnPair = tuple[pl.DataFrame, pl.DataFrame]

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_factor_and_return(
    n_dates: int = 100,
    n_entities: int = 50,
    *,
    seed: int = 42,
    ic_strength: float = 0.3,
) -> FactorReturnPair:
    """Create synthetic factor values and forward returns with known IC."""
    rng = np.random.default_rng(seed)

    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

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

    return (
        pl.DataFrame(rows_f),
        pl.DataFrame(rows_r),
    )


def _make_quantile_return_df(
    n_dates: int = 20,
    n_quantiles: int = 5,
    *,
    seed: int = 42,
) -> pl.DataFrame:
    """Create synthetic quantile return DataFrame."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    rows: list[dict[str, object]] = []
    for d in dates:
        for q in range(1, n_quantiles + 1):
            rows.append(
                {
                    "trade_date": d,
                    "quantile": q,
                    "mean_return": float(rng.normal(0, 0.01)),
                    "count": 10,
                },
            )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# Mock ForwardReturnProvider
# ---------------------------------------------------------------------------


class MockForwardReturnProvider:
    """Mock implementation of ForwardReturnProvider protocol."""

    def __init__(self, return_df: pl.DataFrame) -> None:
        self.return_df = return_df
        self.compute_calls: list[dict[str, object]] = []

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: str = "none",
    ) -> pl.DataFrame:
        self.compute_calls.append(
            {
                "asset_class": asset_class,
                "start": start,
                "end": end,
                "holding_period": holding_period,
                "adj": adj,
            },
        )
        return self.return_df


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data() -> FactorReturnPair:
    """Provide synthetic factor and return DataFrames."""
    return _make_factor_and_return(n_dates=100, n_entities=50)


@pytest.fixture
def mock_provider(
    synthetic_data: FactorReturnPair,
) -> MockForwardReturnProvider:
    """Provide a mock ForwardReturnProvider with synthetic return data."""
    _, return_df = synthetic_data
    return MockForwardReturnProvider(return_df)


@pytest.fixture
def evaluator(
    mock_provider: MockForwardReturnProvider,
) -> FactorEvaluator:
    """Provide a FactorEvaluator with mocked provider."""
    return FactorEvaluator(mock_provider)


# ---------------------------------------------------------------------------
# TestFactorEvaluator.evaluate
# ---------------------------------------------------------------------------


class TestFactorEvaluatorEvaluate:
    """Tests for FactorEvaluator.evaluate()."""

    def test_returns_factor_evaluation_report(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """evaluate() should return a FactorEvaluationReport instance."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        assert isinstance(report, FactorEvaluationReport)

    def test_report_has_all_expected_fields(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Report should contain all expected fields with correct types."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)

        assert isinstance(report.factor_id, str)
        assert isinstance(report.factor_version, int)
        assert isinstance(report.evaluation_period, tuple)
        assert len(report.evaluation_period) == 2
        assert isinstance(report.holding_period, int)
        assert isinstance(report.n_quantiles, int)
        assert isinstance(report.rank_ic_summary, ICSummary)
        assert isinstance(report.pearson_ic_summary, ICSummary)
        assert isinstance(report.ic_decay, list)
        assert report.ic_half_life is None or isinstance(
            report.ic_half_life,
            float,
        )
        assert isinstance(report.ic_autocorrelation, list)
        assert isinstance(report.quantile_annual_returns, dict)
        assert isinstance(report.long_short, LongShortResult)
        assert isinstance(report.avg_turnover, float)
        assert isinstance(report.net_return_after_cost, float)
        assert isinstance(report.turnover_adjusted_ir, float)
        assert isinstance(report.sub_period_ic, dict)
        assert isinstance(report.n_observations, int)
        assert isinstance(report.n_dates, int)
        assert isinstance(report.computed_at, str)

    def test_ic_summary_fields_are_finite(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """IC summary values should be finite numbers."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)

        for ic_summary in (report.rank_ic_summary, report.pearson_ic_summary):
            assert math.isfinite(ic_summary.mean)
            assert math.isfinite(ic_summary.std)
            assert 0 <= ic_summary.win_rate <= 1
            assert 0 <= ic_summary.p_value <= 1

    def test_long_short_fields_are_finite(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Long-short result values should be finite numbers."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        ls = report.long_short
        assert math.isfinite(ls.annual_return)
        assert math.isfinite(ls.annual_volatility)
        assert math.isfinite(ls.sharpe)
        assert math.isfinite(ls.portfolio_ir)
        assert math.isfinite(ls.sortino)
        assert ls.max_drawdown <= 0

    def test_n_observations_matches_data(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """n_observations should equal the rows after join and null cleanup."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        assert report.n_observations > 0
        assert report.n_dates > 0
        assert report.n_observations == report.n_dates * 50  # 50 entities

    def test_computed_at_is_iso_timestamp(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """computed_at should be a valid ISO timestamp string."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        from datetime import datetime

        datetime.fromisoformat(report.computed_at)

    def test_empty_factor_df_returns_empty_report(
        self,
        evaluator: FactorEvaluator,
    ) -> None:
        """Empty factor DataFrame should return an empty report with zero values."""
        empty_factor = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        # Provide explicit bounds because empty DataFrame has no date range
        report = evaluator.evaluate(
            empty_factor,
            start="2024-01-01",
            end="2024-06-30",
        )

        assert isinstance(report, FactorEvaluationReport)
        assert report.n_observations == 0
        assert report.n_dates == 0
        assert report.rank_ic_summary.mean == 0.0
        assert report.rank_ic_summary.std == 0.0
        assert report.long_short.annual_return == 0.0
        assert report.quantile_annual_returns == {}
        assert report.sub_period_ic == {}
        assert report.ic_decay == []
        assert report.ic_autocorrelation == []

    def test_no_matching_dates_produces_zero_ic(
        self,
        mock_provider: MockForwardReturnProvider,
    ) -> None:
        """Factor dates with no overlap in returns should produce zero ICs.

        The evaluator checks factor_df_clean.height after _prepare_data, but
        at that point the data has not been joined with returns yet.  When the
        inner join in rank_ic/pearson_ic produces no matches, IC summaries are
        zero.
        """
        rng = np.random.default_rng(1)
        factor_dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(10)]
        return_dates = [date(2025, 1, 2) + timedelta(days=i) for i in range(10)]
        entities = list(range(1, 51))

        rows_f = [
            {
                "trade_date": d,
                "instrument_id": e,
                "value": float(rng.standard_normal()),
            }
            for d in factor_dates
            for e in entities
        ]
        rows_r = [
            {
                "trade_date": d,
                "instrument_id": e,
                "forward_return": float(rng.standard_normal() * 0.02),
            }
            for d in return_dates
            for e in entities
        ]

        factor_df = pl.DataFrame(rows_f)
        return_df = pl.DataFrame(rows_r)
        mock_provider.return_df = return_df

        evaluator = FactorEvaluator(mock_provider)
        report = evaluator.evaluate(factor_df)

        # IC should be zero because no dates overlap for the inner join
        assert report.rank_ic_summary.mean == 0.0
        assert report.pearson_ic_summary.mean == 0.0
        assert report.rank_ic_summary.std == 0.0
        assert report.long_short.annual_return == 0.0

    def test_forward_provider_called_with_correct_params(
        self,
        mock_provider: MockForwardReturnProvider,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """evaluate() should call the forward return provider correctly."""
        factor_df, _ = synthetic_data
        evaluator = FactorEvaluator(mock_provider)
        evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(
                asset_class="stock",
                holding_period=10,
                adj="hfq",
            ),
            start="2024-02-01",
            end="2024-06-01",
        )

        assert len(mock_provider.compute_calls) == 1
        call = mock_provider.compute_calls[0]
        assert call["asset_class"] == "stock"
        assert call["holding_period"] == 10
        assert call["adj"] == "hfq"
        assert call["start"] == "2024-02-01"
        assert call["end"] == "2024-06-01"

    def test_custom_holding_period(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Custom holding_period should be reflected in the report."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(holding_period=10),
        )
        assert report.holding_period == 10

    def test_custom_n_quantiles(
        self,
        mock_provider: MockForwardReturnProvider,
    ) -> None:
        """Custom n_quantiles should be reflected in the report."""
        # Use 100 entities so n_quantiles=10 divides evenly
        factor_df, return_df = _make_factor_and_return(
            n_dates=100,
            n_entities=100,
        )
        mock_provider.return_df = return_df
        evaluator = FactorEvaluator(mock_provider)
        report = evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(n_quantiles=10),
        )
        assert report.n_quantiles == 10

    def test_custom_risk_free_rate(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Custom risk_free_rate should affect portfolio IR."""
        factor_df, _ = synthetic_data

        report_zero = evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(risk_free_rate=0.0),
        )
        report_high = evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(risk_free_rate=0.05),
        )

        if report_zero.long_short.annual_volatility > 0:
            assert (
                report_high.long_short.portfolio_ir
                < report_zero.long_short.portfolio_ir
            )

    def test_evaluation_period_from_data_range(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """When start/end are not provided, period should be inferred from data."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        start, end = report.evaluation_period
        # The period should cover the synthetic data range
        assert start <= end

    def test_evaluation_period_with_explicit_bounds(
        self,
        mock_provider: MockForwardReturnProvider,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Explicit start/end should be used in the evaluation period."""
        factor_df, _ = synthetic_data
        evaluator = FactorEvaluator(mock_provider)
        report = evaluator.evaluate(
            factor_df,
            start="2024-03-01",
            end="2024-04-01",
        )
        assert report.evaluation_period == ("2024-03-01", "2024-04-01")

    def test_custom_ic_lags(
        self,
        mock_provider: MockForwardReturnProvider,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Custom ic_lags should be used for IC decay computation."""
        factor_df, _ = synthetic_data
        evaluator = FactorEvaluator(mock_provider)
        report = evaluator.evaluate(
            factor_df,
            config=EvaluationConfig(ic_lags=[1, 5, 10]),
        )

        # Each lag should produce one decay entry
        assert len(report.ic_decay) == 3
        decay_lags = [lag for lag, _ in report.ic_decay]
        assert decay_lags == [1, 5, 10]

    def test_default_ic_lags(
        self,
        evaluator: FactorEvaluator,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Default IC lags should be [1, 2, 3, 5, 10, 20]."""
        factor_df, _ = synthetic_data
        report = evaluator.evaluate(factor_df)
        decay_lags = [lag for lag, _ in report.ic_decay]
        assert decay_lags == [1, 2, 3, 5, 10, 20]


# ---------------------------------------------------------------------------
# TestFactorEvaluator.evaluate_orthogonal
# ---------------------------------------------------------------------------


class TestFactorEvaluatorEvaluateOrthogonal:
    """Tests for FactorEvaluator.evaluate_orthogonal()."""

    def test_no_other_factors_returns_target_as_is(self) -> None:
        """When no other factors provided, returns target values as orthogonalized."""
        rng = np.random.default_rng(42)
        n = 50
        target_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2)] * n,
                "instrument_id": list(range(1, n + 1)),
                "value": rng.normal(0, 1, n).tolist(),
            },
        )

        provider = MockForwardReturnProvider(pl.DataFrame())
        evaluator = FactorEvaluator(provider)
        result = evaluator.evaluate_orthogonal(target_df, [])

        assert "trade_date" in result.columns
        assert "instrument_id" in result.columns
        assert "orthogonalized_value" in result.columns
        assert result.height == n
        # Values should be identical to input
        expected_values = target_df["value"].to_list()
        result_values = result["orthogonalized_value"].to_list()
        for expected, actual in zip(
            expected_values,
            result_values,
            strict=True,
        ):
            assert actual == pytest.approx(expected)

    def test_one_other_factor_calls_orthogonalize(self) -> None:
        """With one other factor, should delegate to orthogonalize."""
        rng = np.random.default_rng(42)
        n = 50
        dates = [date(2024, 1, 2)] * n
        entities = list(range(1, n + 1))

        target_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )
        other_df = pl.DataFrame(
            {
                "trade_date": dates,
                "instrument_id": entities,
                "value": rng.normal(0, 1, n).tolist(),
            },
        )

        provider = MockForwardReturnProvider(pl.DataFrame())
        evaluator = FactorEvaluator(provider)
        result = evaluator.evaluate_orthogonal(target_df, [other_df])

        assert "orthogonalized_value" in result.columns
        assert result.height > 0

    def test_multiple_other_factors_uses_long_format(self) -> None:
        """With multiple other factors, evaluate_orthogonal produces long format.

        The evaluator concatenates multiple factor DataFrames into long format
        with a factor_name column before passing to orthogonalize.
        """
        rng = np.random.default_rng(42)
        n = 50
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(5)]
        entities = list(range(1, n + 1))

        rows_t: list[dict[str, object]] = []
        rows_f1: list[dict[str, object]] = []
        rows_f2: list[dict[str, object]] = []
        for d in dates:
            for e in entities:
                rows_t.append(
                    {
                        "trade_date": d,
                        "instrument_id": e,
                        "value": float(rng.normal()),
                    },
                )
                rows_f1.append(
                    {
                        "trade_date": d,
                        "instrument_id": e,
                        "value": float(rng.normal()),
                    },
                )
                rows_f2.append(
                    {
                        "trade_date": d,
                        "instrument_id": e,
                        "value": float(rng.normal()),
                    },
                )

        target_df = pl.DataFrame(rows_t)
        other1 = pl.DataFrame(rows_f1)
        other2 = pl.DataFrame(rows_f2)

        provider = MockForwardReturnProvider(pl.DataFrame())
        evaluator = FactorEvaluator(provider)

        # Use symmetric method which handles multiple factors via PCA
        result = evaluator.evaluate_orthogonal(
            target_df,
            [other1, other2],
            method="symmetric",
        )

        assert "orthogonalized_value" in result.columns
        assert result.height > 0

    def test_orthogonalize_reduces_correlation(self) -> None:
        """After orthogonalization, correlation with the factor should decrease.

        Uses multiple dates so the sequential method can iterate per-date
        cross-sections correctly.
        """
        rng = np.random.default_rng(42)
        n_entities = 50
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(5)]
        entities = list(range(1, n_entities + 1))

        # Target is a linear combination of factor + noise
        factor_vals = rng.normal(0, 1, n_entities * len(dates))
        noise = rng.normal(0, 0.1, n_entities * len(dates))
        target_vals = 0.8 * factor_vals + noise

        rows_t: list[dict[str, object]] = []
        rows_f: list[dict[str, object]] = []
        for i, d in enumerate(dates):
            for j, e in enumerate(entities):
                idx = i * n_entities + j
                rows_t.append(
                    {
                        "trade_date": d,
                        "instrument_id": e,
                        "value": float(target_vals[idx]),
                    },
                )
                rows_f.append(
                    {
                        "trade_date": d,
                        "instrument_id": e,
                        "value": float(factor_vals[idx]),
                    },
                )

        target_df = pl.DataFrame(rows_t)
        other_df = pl.DataFrame(rows_f)

        provider = MockForwardReturnProvider(pl.DataFrame())
        evaluator = FactorEvaluator(provider)
        result = evaluator.evaluate_orthogonal(
            target_df,
            [other_df],
            min_cross_section=10,
        )

        # Correlation before should be strong
        corr_before = float(
            np.corrcoef(target_vals, factor_vals)[0, 1],
        )
        assert abs(corr_before) > 0.5

        # After orthogonalization, correlation should decrease
        corr_after = float(
            np.corrcoef(
                result["orthogonalized_value"].to_numpy(),
                factor_vals,
            )[0, 1],
        )
        assert abs(corr_after) < abs(corr_before)

    def test_empty_target_with_other_factors(self) -> None:
        """Empty target DataFrame with other factors should not crash."""
        empty_target = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        rng = np.random.default_rng(42)
        other_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2)] * 10,
                "instrument_id": list(range(1, 11)),
                "value": rng.normal(0, 1, 10).tolist(),
            },
        )

        provider = MockForwardReturnProvider(pl.DataFrame())
        evaluator = FactorEvaluator(provider)
        result = evaluator.evaluate_orthogonal(empty_target, [other_df])
        assert "orthogonalized_value" in result.columns


# ---------------------------------------------------------------------------
# Test _resolve_period
# ---------------------------------------------------------------------------


class TestResolvePeriod:
    """Tests for the _resolve_period helper."""

    def test_infers_period_from_data(self) -> None:
        """Period is inferred from the trade_date column range."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 5), date(2024, 3, 15)],
                "value": [1.0, 2.0],
            },
        )
        start, end = _resolve_period(df, None, None)
        assert start == "2024-01-05"
        assert end == "2024-03-15"

    def test_explicit_start_overrides_data(self) -> None:
        """Explicit start overrides the min date from data."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 5), date(2024, 3, 15)],
                "value": [1.0, 2.0],
            },
        )
        start, end = _resolve_period(df, start="2024-02-01", end=None)
        assert start == "2024-02-01"
        assert end == "2024-03-15"

    def test_explicit_end_overrides_data(self) -> None:
        """Explicit end overrides the max date from data."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 5), date(2024, 3, 15)],
                "value": [1.0, 2.0],
            },
        )
        start, end = _resolve_period(df, start=None, end="2024-02-28")
        assert start == "2024-01-05"
        assert end == "2024-02-28"

    def test_both_explicit_bounds(self) -> None:
        """Both explicit start and end are used."""
        df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 5), date(2024, 3, 15)],
                "value": [1.0, 2.0],
            },
        )
        start, end = _resolve_period(df, start="2024-01-01", end="2024-12-31")
        assert start == "2024-01-01"
        assert end == "2024-12-31"

    def test_no_trade_date_column_uses_defaults(self) -> None:
        """When trade_date column is absent, uses default fallback dates."""
        df = pl.DataFrame({"value": [1.0, 2.0]})
        start, end = _resolve_period(df, None, None)
        assert start == "1970-01-01"
        assert end == "2099-12-31"

    def test_no_trade_date_with_explicit_bounds(self) -> None:
        """Explicit bounds are used even without trade_date column."""
        df = pl.DataFrame({"value": [1.0, 2.0]})
        start, end = _resolve_period(df, start="2024-01-01", end="2024-06-30")
        assert start == "2024-01-01"
        assert end == "2024-06-30"


# ---------------------------------------------------------------------------
# Test _prepare_data
# ---------------------------------------------------------------------------


class TestPrepareData:
    """Tests for the _prepare_data helper."""

    def test_filters_by_start_date(self) -> None:
        """Data before the start date should be filtered out."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 2, 1),
                    date(2024, 3, 1),
                ],
                "instrument_id": [1, 1, 1],
                "value": [1.0, 2.0, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 2, 1),
                    date(2024, 3, 1),
                ],
                "instrument_id": [1, 1, 1],
                "forward_return": [0.01, 0.02, 0.03],
            },
        )

        f_clean, _ = _prepare_data(factor_df, return_df, start="2024-02-15")
        # Only March 1 >= Feb 15
        assert f_clean.height == 1
        assert f_clean["trade_date"][0] == date(2024, 3, 1)

    def test_filters_by_end_date(self) -> None:
        """Data after the end date should be filtered out."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 2, 1),
                    date(2024, 3, 1),
                ],
                "instrument_id": [1, 1, 1],
                "value": [1.0, 2.0, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 2, 1),
                    date(2024, 3, 1),
                ],
                "instrument_id": [1, 1, 1],
                "forward_return": [0.01, 0.02, 0.03],
            },
        )

        f_clean, _ = _prepare_data(factor_df, return_df, end="2024-02-15")
        assert f_clean.height == 2
        assert f_clean["trade_date"].max() <= date(2024, 2, 15)

    def test_drops_null_values(self) -> None:
        """Rows with null values should be dropped."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "value": [1.0, None, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "forward_return": [0.01, 0.02, None],
            },
        )

        f_clean, r_clean = _prepare_data(factor_df, return_df)
        assert f_clean.height == 2  # drops null value row
        assert r_clean.height == 2  # drops null forward_return row

    def test_drops_null_trade_dates(self) -> None:
        """Rows with null trade_date should be dropped."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), None],
                "instrument_id": [1, 2],
                "value": [1.0, 2.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 1), None],
                "instrument_id": [1, 2],
                "forward_return": [0.01, 0.02],
            },
        )

        f_clean, r_clean = _prepare_data(factor_df, return_df)
        assert f_clean.height == 1
        assert r_clean.height == 1

    def test_null_drop_only(self) -> None:
        """With no start/end bounds, _prepare_data only drops nulls."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "value": [1.0, None, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "forward_return": [0.01, None, 0.03],
            },
        )

        f_clean, r_clean = _prepare_data(factor_df, return_df)
        assert f_clean.height == 2
        assert r_clean.height == 2

    def test_no_filtering_when_bounds_are_none(self) -> None:
        """With no start/end, all rows are kept (minus nulls)."""
        factor_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "value": [1.0, 2.0, 3.0],
            },
        )
        return_df = pl.DataFrame(
            {
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "instrument_id": [1, 2, 3],
                "forward_return": [0.01, 0.02, 0.03],
            },
        )

        f_clean, r_clean = _prepare_data(factor_df, return_df)
        assert f_clean.height == 3
        assert r_clean.height == 3


# ---------------------------------------------------------------------------
# Test _empty_report
# ---------------------------------------------------------------------------


class TestEmptyReport:
    """Tests for the _empty_report helper."""

    def test_returns_valid_factor_evaluation_report(self) -> None:
        """_empty_report should return a valid FactorEvaluationReport."""
        report = _empty_report(
            factor_id="test_factor",
            factor_version=3,
            period=("2024-01-01", "2024-06-30"),
            holding_period=5,
            n_quantiles=5,
        )
        assert isinstance(report, FactorEvaluationReport)

    def test_zero_values(self) -> None:
        """Empty report should have zero values for all numeric fields."""
        report = _empty_report(
            factor_id="test",
            factor_version=1,
            period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
        )
        assert report.rank_ic_summary.mean == 0.0
        assert report.rank_ic_summary.std == 0.0
        assert report.rank_ic_summary.icir == 0.0
        assert report.rank_ic_summary.p_value == 1.0
        assert report.rank_ic_summary.win_rate == 0.0

        assert report.long_short.annual_return == 0.0
        assert report.long_short.annual_volatility == 0.0
        assert report.long_short.sharpe == 0.0
        assert report.long_short.max_drawdown == 0.0

        assert report.n_observations == 0
        assert report.n_dates == 0
        assert report.avg_turnover == 0.0
        assert report.net_return_after_cost == 0.0
        assert report.turnover_adjusted_ir == 0.0

    def test_correct_metadata(self) -> None:
        """Empty report should preserve the passed metadata."""
        report = _empty_report(
            factor_id="momentum",
            factor_version=7,
            period=("2023-01-01", "2023-12-31"),
            holding_period=20,
            n_quantiles=10,
        )
        assert report.factor_id == "momentum"
        assert report.factor_version == 7
        assert report.evaluation_period == ("2023-01-01", "2023-12-31")
        assert report.holding_period == 20
        assert report.n_quantiles == 10

    def test_empty_collections(self) -> None:
        """Empty report should have empty collections."""
        report = _empty_report(
            factor_id="test",
            factor_version=1,
            period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
        )
        assert report.ic_decay == []
        assert report.ic_autocorrelation == []
        assert report.quantile_annual_returns == {}
        assert report.sub_period_ic == {}

    def test_none_half_life(self) -> None:
        """Empty report should have None half_life."""
        report = _empty_report(
            factor_id="test",
            factor_version=1,
            period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
        )
        assert report.ic_half_life is None

    def test_computed_at_is_valid_iso(self) -> None:
        """computed_at should be a valid ISO timestamp."""
        report = _empty_report(
            factor_id="test",
            factor_version=1,
            period=("2024-01-01", "2024-12-31"),
            holding_period=5,
            n_quantiles=5,
        )
        from datetime import datetime

        datetime.fromisoformat(report.computed_at)


# ---------------------------------------------------------------------------
# Test _compute_ic_decay_safe
# ---------------------------------------------------------------------------


class TestComputeICDecaySafe:
    """Tests for the _compute_ic_decay_safe helper."""

    def test_returns_list_and_half_life(self) -> None:
        """Should return a tuple of (list, optional half_life)."""
        factor_df, _ = _make_factor_and_return(n_dates=50, n_entities=50)
        result, half_life = _compute_ic_decay_safe(factor_df, [1, 5])
        assert isinstance(result, list)
        assert half_life is None or isinstance(half_life, float)

    def test_respects_lag_parameter(self) -> None:
        """Should produce one entry per lag."""
        factor_df, _ = _make_factor_and_return(n_dates=50, n_entities=50)
        result, _ = _compute_ic_decay_safe(factor_df, [1, 2, 3, 5])
        assert len(result) == 4
        lags = [lag for lag, _ in result]
        assert lags == [1, 2, 3, 5]

    def test_empty_dataframe_returns_zero_ics(self) -> None:
        """Empty DataFrame should return zero ICs and None half_life."""
        empty_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        result, half_life = _compute_ic_decay_safe(empty_df, [1, 5])
        # ic_decay on empty data produces zero ICs per lag
        assert len(result) == 2
        assert all(ic == 0.0 for _, ic in result)
        assert half_life is None

    def test_with_close_df_uses_close_not_factor_value(self) -> None:
        """When close_df is provided, IC decay should use close prices for
        forward returns instead of factor values as pseudo-close.

        This is a regression test for the bug where factor values were
        passed as pseudo-close, computing factor autocorrelation instead
        of factor-vs-forward-return IC decay.
        """
        rng = np.random.default_rng(42)
        n_factor_dates = 100
        n_close_dates = 130  # extra dates so forward returns cover factor range
        n_entities = 50
        entities = list(range(1, n_entities + 1))

        # Build correlated factor and close series so IC is non-zero
        signal = rng.standard_normal(n_close_dates)
        rows_f: list[dict[str, object]] = []
        rows_c: list[dict[str, object]] = []

        # Close prices: random walk with signal correlation
        prices = dict.fromkeys(entities, 100.0)
        for t in range(n_close_dates):
            d = date(2024, 1, 2) + timedelta(days=t)
            for eid in entities:
                rows_c.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "close": prices[eid],
                    },
                )
                prices[eid] *= 1 + 0.01 * signal[t] + rng.standard_normal() * 0.02

        # Factor values for the first n_factor_dates
        for t in range(n_factor_dates):
            d = date(2024, 1, 2) + timedelta(days=t)
            for eid in entities:
                factor_val = 0.5 * signal[t] + rng.standard_normal() * 0.5
                rows_f.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "value": float(factor_val),
                    },
                )

        factor_df = pl.DataFrame(rows_f)
        close_df = pl.DataFrame(rows_c)

        # With close_df: IC decay should be well-defined
        result_with_close, _ = _compute_ic_decay_safe(
            factor_df,
            [5, 10, 20],
            close_df=close_df,
        )
        assert len(result_with_close) == 3
        # IC values should be in reasonable range (not NaN/inf)
        for lag, ic in result_with_close:
            assert math.isfinite(ic), f"IC at lag {lag} should be finite"

        # Without close_df (old pseudo-close behavior)
        result_without, _ = _compute_ic_decay_safe(
            factor_df,
            [5, 10, 20],
        )
        assert len(result_without) == 3

        # The IC values should differ between the two approaches
        # because one uses close prices for forward returns and the other
        # uses factor values as pseudo-close.
        ics_with = [ic for _, ic in result_with_close]
        ics_without = [ic for _, ic in result_without]
        assert ics_with != ics_without, (
            "IC decay with close_df should differ from pseudo-close approach"
        )

    def test_close_df_none_falls_back_to_empty(self) -> None:
        """When close_df is None and factor_df is empty, should return zeros."""
        empty_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        result, half_life = _compute_ic_decay_safe(
            empty_df,
            [1, 5],
            close_df=None,
        )
        assert len(result) == 2
        assert all(ic == 0.0 for _, ic in result)
        assert half_life is None


# ---------------------------------------------------------------------------
# Test ClosePriceProvider protocol
# ---------------------------------------------------------------------------


class TestClosePriceProvider:
    """Tests for ClosePriceProvider protocol integration."""

    def test_evaluator_accepts_close_price_provider(self) -> None:
        """FactorEvaluator should accept an optional close_price_provider."""

        class MockClosePriceProvider:
            def get_close_prices(
                self,
                asset_class: str,
                start: str,
                end: str,
                adj: str = "none",
            ) -> pl.DataFrame:
                return pl.DataFrame(
                    schema={
                        "trade_date": pl.Date,
                        "instrument_id": pl.Int64,
                        "close": pl.Float64,
                    },
                )

        # Verify the provider can be passed without error
        evaluator = FactorEvaluator(
            mock_provider,
            close_price_provider=MockClosePriceProvider(),
        )
        assert evaluator._cp_provider is not None

    def test_ic_decay_with_close_provider_produces_finite_values(
        self,
        mock_provider: MockForwardReturnProvider,
        synthetic_data: FactorReturnPair,
    ) -> None:
        """Evaluator with close_price_provider should produce finite IC decay."""

        class MockClosePriceProvider:
            def __init__(self, close_df: pl.DataFrame) -> None:
                self._close_df = close_df

            def get_close_prices(
                self,
                asset_class: str,
                start: str,
                end: str,
                adj: str = "none",
            ) -> pl.DataFrame:
                return self._close_df

        import math

        factor_df, _ = synthetic_data
        rng = np.random.default_rng(42)
        # Close prices need extra dates beyond the factor range so that
        # forward returns (shift(-lag)) are available for the full factor
        # period.  Use 40 extra calendar days (~28 trading days).
        n_close_dates = 140
        n_entities = 50
        entities = list(range(1, n_entities + 1))

        rows_c: list[dict[str, object]] = []
        prices = dict.fromkeys(entities, 100.0)
        for t in range(n_close_dates):
            d = date(2024, 1, 2) + timedelta(days=t)
            for eid in entities:
                rows_c.append(
                    {
                        "trade_date": d,
                        "instrument_id": eid,
                        "close": prices[eid],
                    },
                )
                prices[eid] *= 1 + rng.standard_normal() * 0.02
        close_df = pl.DataFrame(rows_c)

        close_provider = MockClosePriceProvider(close_df)
        evaluator = FactorEvaluator(
            mock_provider,
            close_price_provider=close_provider,
        )
        report = evaluator.evaluate(factor_df)

        # IC decay should have finite values
        for lag, ic in report.ic_decay:
            assert math.isfinite(ic), (
                f"IC decay at lag {lag} should be finite, got {ic}"
            )


# ---------------------------------------------------------------------------
# Test _compute_quantile_annual_returns
# ---------------------------------------------------------------------------


class TestComputeQuantileAnnualReturns:
    """Tests for the _compute_quantile_annual_returns helper."""

    def test_returns_dict_of_int_to_float(self) -> None:
        """Should return {quantile: annualized_return} mapping."""
        q_ret_df = _make_quantile_return_df()
        result = _compute_quantile_annual_returns(q_ret_df)
        assert isinstance(result, dict)
        for key, val in result.items():
            assert isinstance(key, int)
            assert isinstance(val, float)

    def test_correct_number_of_quantiles(self) -> None:
        """Should produce entries for all quantiles."""
        q_ret_df = _make_quantile_return_df(n_quantiles=5)
        result = _compute_quantile_annual_returns(q_ret_df)
        assert len(result) == 5

    def test_empty_dataframe_returns_empty_dict(self) -> None:
        """Empty DataFrame should return empty dict."""
        empty_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            },
        )
        result = _compute_quantile_annual_returns(empty_df)
        assert result == {}


# ---------------------------------------------------------------------------
# Test _estimate_avg_turnover
# ---------------------------------------------------------------------------


class TestEstimateAvgTurnover:
    """Tests for the _estimate_avg_turnover helper."""

    def test_returns_float(self) -> None:
        """Should return a float."""
        q_ret_df = _make_quantile_return_df()
        result = _estimate_avg_turnover(q_ret_df)
        assert isinstance(result, float)

    def test_nonnegative(self) -> None:
        """Turnover estimate should be non-negative."""
        q_ret_df = _make_quantile_return_df()
        result = _estimate_avg_turnover(q_ret_df)
        assert result >= 0

    def test_single_date_returns_zero(self) -> None:
        """Single date should return 0 turnover (need 2+ dates)."""
        q_ret_df = _make_quantile_return_df(n_dates=1)
        result = _estimate_avg_turnover(q_ret_df)
        assert result == 0.0

    def test_empty_dataframe_returns_zero(self) -> None:
        """Empty DataFrame should return 0."""
        empty_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "quantile": pl.Int64,
                "mean_return": pl.Float64,
            },
        )
        result = _estimate_avg_turnover(empty_df)
        assert result == 0.0
