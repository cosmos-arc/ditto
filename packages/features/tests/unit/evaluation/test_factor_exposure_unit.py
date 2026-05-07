"""Unit tests for factor exposure analysis (EVAL-EV-3)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_target_and_risk(
    n_dates: int = 50,
    n_entities: int = 100,
    *,
    seed: int = 42,
    risk_exposure: float = 0.6,
    noise_std: float = 0.3,
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame], pl.DataFrame]:
    """Create synthetic target factor and risk factors with known exposure.

    Target = risk_exposure * risk_factor + noise
    """
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

    rows_target: list[dict[str, object]] = []
    rows_risk: list[dict[str, object]] = []
    rows_return: list[dict[str, object]] = []

    for d in dates:
        risk_vals = rng.standard_normal(n_entities)
        noise = rng.normal(0, noise_std, n_entities)
        target_vals = risk_exposure * risk_vals + noise

        # Returns correlated with target (for IC computation)
        return_noise = rng.normal(0, 0.01, n_entities)
        return_vals = 0.001 + 0.3 * target_vals + return_noise

        for i, eid in enumerate(entities):
            rows_target.append(
                {"trade_date": d, "instrument_id": eid, "value": float(target_vals[i])},
            )
            rows_risk.append(
                {"trade_date": d, "instrument_id": eid, "value": float(risk_vals[i])},
            )
            rows_return.append(
                {
                    "trade_date": d,
                    "instrument_id": eid,
                    "forward_return": float(return_vals[i]),
                },
            )

    target_df = pl.DataFrame(rows_target)
    risk_df = pl.DataFrame(rows_risk)
    return_df = pl.DataFrame(rows_return)
    return target_df, {"market": risk_df}, return_df


def _make_multi_risk_data(
    n_dates: int = 50,
    n_entities: int = 100,
    *,
    seed: int = 42,
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    """Create target factor with multiple risk factors."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
    entities = list(range(1, n_entities + 1))

    rows_target: list[dict[str, object]] = []
    risk_data: dict[str, list[dict[str, object]]] = {
        "market": [],
        "size": [],
    }

    for d in dates:
        market_vals = rng.standard_normal(n_entities)
        size_vals = rng.standard_normal(n_entities)
        noise = rng.normal(0, 0.2, n_entities)
        target_vals = 0.5 * market_vals + 0.3 * size_vals + noise

        for i, eid in enumerate(entities):
            rows_target.append(
                {"trade_date": d, "instrument_id": eid, "value": float(target_vals[i])},
            )
            risk_data["market"].append(
                {"trade_date": d, "instrument_id": eid, "value": float(market_vals[i])},
            )
            risk_data["size"].append(
                {"trade_date": d, "instrument_id": eid, "value": float(size_vals[i])},
            )

    target_df = pl.DataFrame(rows_target)
    risk_dfs = {name: pl.DataFrame(rows) for name, rows in risk_data.items()}
    return target_df, risk_dfs


# ---------------------------------------------------------------------------
# Tests: basic factor exposure
# ---------------------------------------------------------------------------


class TestFactorExposureBasic:
    """Tests for basic factor exposure analysis."""

    def test_returns_factor_exposure_result(self) -> None:
        """Should return a FactorExposureResult."""
        from ditto_features.evaluation.metrics import factor_exposure
        from ditto_features.evaluation.report import FactorExposureResult

        target_df, risk_dfs, return_df = _make_target_and_risk()
        result = factor_exposure(target_df, risk_dfs, return_df=return_df)

        assert isinstance(result, FactorExposureResult)

    def test_single_risk_factor_exposure(self) -> None:
        """Single risk factor should produce non-zero target exposure."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, return_df = _make_target_and_risk(
            n_dates=100,
            n_entities=200,
            risk_exposure=0.6,
        )
        result = factor_exposure(target_df, risk_dfs, return_df=return_df)

        assert "market" in result.target_exposure
        # Target should have measurable exposure to the risk factor
        assert result.target_exposure["market"] > 0.0

    def test_residual_ic_after_orthogonalization(self) -> None:
        """Residual IC should be present after removing risk factor."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, return_df = _make_target_and_risk(
            n_dates=100,
            n_entities=200,
            risk_exposure=0.6,
        )
        result = factor_exposure(target_df, risk_dfs, return_df=return_df)

        assert "market" in result.orthogonal_residual_stats
        assert isinstance(result.orthogonal_residual_stats["market"], float)

    def test_n_factors_and_n_dates(self) -> None:
        """n_factors and n_dates should be correctly reported."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, _ = _make_target_and_risk(n_dates=50, n_entities=100)
        result = factor_exposure(target_df, risk_dfs)

        assert result.n_factors == 1  # only "market"
        assert result.n_dates == 50


# ---------------------------------------------------------------------------
# Tests: correlation matrix
# ---------------------------------------------------------------------------


class TestFactorExposureCorrelation:
    """Tests for correlation matrix in factor exposure analysis."""

    def test_correlation_matrix_structure(self) -> None:
        """Correlation matrix should include target and all risk factors."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, _ = _make_target_and_risk(n_dates=50, n_entities=100)
        result = factor_exposure(target_df, risk_dfs)

        assert "target" in result.correlation_matrix
        assert "market" in result.correlation_matrix

        # Each factor should have entries for all factors
        for key in result.correlation_matrix:
            assert "target" in result.correlation_matrix[key]
            assert "market" in result.correlation_matrix[key]

    def test_correlation_values_in_valid_range(self) -> None:
        """All correlation values should be in [-1, 1]."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, _ = _make_target_and_risk(
            n_dates=50,
            n_entities=100,
            risk_exposure=0.6,
        )
        result = factor_exposure(target_df, risk_dfs)

        for outer_key, inner_dict in result.correlation_matrix.items():
            for inner_key, corr_val in inner_dict.items():
                assert -1.0 <= corr_val <= 1.0, (
                    f"corr({outer_key}, {inner_key}) = {corr_val} outside [-1, 1]"
                )

    def test_self_correlation_is_one(self) -> None:
        """A factor's correlation with itself should be 1.0."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, _ = _make_target_and_risk(n_dates=50, n_entities=100)
        result = factor_exposure(target_df, risk_dfs)

        assert result.correlation_matrix["target"]["target"] == pytest.approx(
            1.0,
            abs=1e-6,
        )
        assert result.correlation_matrix["market"]["market"] == pytest.approx(
            1.0,
            abs=1e-6,
        )

    def test_known_correlation_with_controlled_data(self) -> None:
        """Correlation between target and risk factor should match known exposure."""
        from ditto_features.evaluation.metrics import factor_exposure

        # With high risk_exposure and low noise, correlation should be high
        target_df, risk_dfs, _ = _make_target_and_risk(
            n_dates=200,
            n_entities=200,
            risk_exposure=0.9,
            noise_std=0.1,
        )
        result = factor_exposure(target_df, risk_dfs)

        corr = result.correlation_matrix["target"]["market"]
        assert corr > 0.8  # strong correlation

    def test_multi_factor_correlation_matrix(self) -> None:
        """Multiple risk factors should all appear in the correlation matrix."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs = _make_multi_risk_data(
            n_dates=50,
            n_entities=100,
        )
        result = factor_exposure(target_df, risk_dfs)

        assert "target" in result.correlation_matrix
        assert "market" in result.correlation_matrix
        assert "size" in result.correlation_matrix

        assert result.n_factors == 2


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestFactorExposureEdgeCases:
    """Tests for edge cases in factor exposure analysis."""

    def test_empty_risk_factors_returns_zero_exposure(self) -> None:
        """Empty risk factors should produce zero exposure."""
        from ditto_features.evaluation.metrics import factor_exposure

        rng = np.random.default_rng(42)
        n_dates = 50
        n_entities = 100
        dates = [date(2024, 1, 2) + timedelta(days=i) for i in range(n_dates)]
        entities = list(range(1, n_entities + 1))

        rows: list[dict[str, object]] = []
        for d in dates:
            vals = rng.standard_normal(n_entities)
            for i, eid in enumerate(entities):
                rows.append(
                    {"trade_date": d, "instrument_id": eid, "value": float(vals[i])},
                )

        target_df = pl.DataFrame(rows)
        result = factor_exposure(target_df, {})

        assert result.target_exposure == {}
        assert result.correlation_matrix == {}
        assert result.orthogonal_residual_stats == {}
        assert result.n_factors == 0

    def test_small_cross_section_returns_empty(self) -> None:
        """Fewer entities than min_cross_section should produce empty results."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df, risk_dfs, _ = _make_target_and_risk(
            n_dates=10,
            n_entities=10,
        )
        result = factor_exposure(target_df, risk_dfs, min_cross_section=30)

        assert result.target_exposure == {}
        assert result.correlation_matrix == {}
        assert result.orthogonal_residual_stats == {}

    def test_empty_target_returns_empty(self) -> None:
        """Empty target DataFrame should produce empty results."""
        from ditto_features.evaluation.metrics import factor_exposure

        target_df = pl.DataFrame(
            schema={
                "trade_date": pl.Date,
                "instrument_id": pl.Int64,
                "value": pl.Float64,
            },
        )
        rng = np.random.default_rng(42)
        risk_df = pl.DataFrame(
            {
                "trade_date": [date(2024, 1, 2)] * 50,
                "instrument_id": list(range(1, 51)),
                "value": rng.standard_normal(50).tolist(),
            },
        )
        result = factor_exposure(target_df, {"market": risk_df})

        assert result.target_exposure == {}

    def test_frozen_dataclass(self) -> None:
        """FactorExposureResult should be a frozen dataclass."""
        from ditto_features.evaluation.metrics import factor_exposure
        from ditto_features.evaluation.report import FactorExposureResult

        target_df, risk_dfs, return_df = _make_target_and_risk()
        result = factor_exposure(target_df, risk_dfs, return_df=return_df)
        assert isinstance(result, FactorExposureResult)

        with pytest.raises(AttributeError):
            result.n_factors = 999  # type: ignore[misc]
