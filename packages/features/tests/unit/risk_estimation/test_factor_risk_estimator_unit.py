"""PIT-safe stock factor risk decomposition tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from ditto_features.risk_estimation.covariance import RiskEstimationEvidence
from ditto_features.risk_estimation.factor_risk import (
    FactorRiskError,
    FactorRiskPosition,
    FactorRiskRequest,
    StockFactorRiskEstimator,
)

_STYLE_FACTORS = (
    "size",
    "value",
    "momentum",
    "volatility",
    "liquidity",
    "quality",
)


def _evidence() -> RiskEstimationEvidence:
    decision = datetime(2026, 4, 1, tzinfo=UTC)
    return RiskEstimationEvidence(
        decision_time=decision,
        knowledge_cutoff=decision - timedelta(hours=1),
        publication_cutoff=decision - timedelta(hours=1),
        source_snapshot_ids=("factor-snap-1",),
    )


def _exposures(*, include_second_stock: bool = True) -> pl.DataFrame:
    visible = datetime(2026, 3, 31, 20, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    instruments = (1, 2) if include_second_stock else (1,)
    for instrument_id in instruments:
        for factor_index, factor_name in enumerate(_STYLE_FACTORS):
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "factor_name": factor_name,
                    "exposure": (instrument_id + factor_index) / 10,
                    "knowledge_time": visible,
                    "publication_time": visible,
                    "source_snapshot_id": "factor-snap-1",
                }
            )
        rows.append(
            {
                "instrument_id": instrument_id,
                "factor_name": f"industry:{'bank' if instrument_id == 1 else 'tech'}",
                "exposure": 1.0,
                "knowledge_time": visible,
                "publication_time": visible,
                "source_snapshot_id": "factor-snap-1",
            }
        )
    return pl.DataFrame(rows)


def _request(positions: tuple[FactorRiskPosition, ...]) -> FactorRiskRequest:
    factors = (*_STYLE_FACTORS, "industry:bank", "industry:tech")
    return FactorRiskRequest(
        positions=positions,
        exposure_frame=_exposures(),
        factor_names=factors,
        factor_covariance=np.diag([0.01] * len(factors)),
        idiosyncratic_variances={1: 0.001, 2: 0.002},
        evidence=_evidence(),
    )


def test_stock_factor_risk_euler_contributions_reconcile_total_variance() -> None:
    result = StockFactorRiskEstimator().estimate(
        _request(
            (
                FactorRiskPosition(1, 0.6, "stock"),
                FactorRiskPosition(2, 0.4, "stock"),
            )
        )
    )

    assert result.availability == "available"
    assert result.stock_weight == pytest.approx(1.0)
    assert sum(result.percentage_contributions.values()) == pytest.approx(1.0)
    assert sum(result.variance_contributions.values()) == pytest.approx(
        result.total_variance
    )
    assert result.euler_residual == pytest.approx(0.0, abs=1e-12)

    size_exposure = result.portfolio_exposures["size"]
    assert result.marginal_contributions["size"] == pytest.approx(
        0.01 * size_exposure / result.total_risk
    )
    assert result.marginal_contributions["specific:1"] == pytest.approx(
        0.6 * 0.001 / result.total_risk
    )


def test_factor_risk_rejects_portfolio_weights_above_one() -> None:
    request = _request(
        (
            FactorRiskPosition(1, 0.7, "stock"),
            FactorRiskPosition(2, 0.4, "stock"),
        )
    )

    with pytest.raises(FactorRiskError, match="cannot exceed one"):
        StockFactorRiskEstimator().estimate(request)


def test_pure_etf_factor_risk_is_explicitly_unavailable() -> None:
    result = StockFactorRiskEstimator().estimate(
        _request((FactorRiskPosition(10, 1.0, "etf"),))
    )

    assert result.availability == "unavailable"
    assert result.total_variance == 0.0
    assert result.unavailable_weight == pytest.approx(1.0)


def test_mixed_portfolio_reports_partial_without_inventing_etf_exposure() -> None:
    result = StockFactorRiskEstimator().estimate(
        _request(
            (
                FactorRiskPosition(1, 0.5, "stock"),
                FactorRiskPosition(10, 0.5, "etf"),
            )
        )
    )

    assert result.availability == "partial"
    assert result.stock_weight == pytest.approx(0.5)
    assert result.unavailable_weight == pytest.approx(0.5)


def test_missing_stock_style_or_industry_exposure_fails_closed() -> None:
    request = _request(
        (
            FactorRiskPosition(1, 0.5, "stock"),
            FactorRiskPosition(2, 0.5, "stock"),
        )
    )
    request = FactorRiskRequest(
        positions=request.positions,
        exposure_frame=_exposures(include_second_stock=False),
        factor_names=request.factor_names,
        factor_covariance=request.factor_covariance,
        idiosyncratic_variances=request.idiosyncratic_variances,
        evidence=request.evidence,
    )

    with pytest.raises(FactorRiskError, match="stock 2"):
        StockFactorRiskEstimator().estimate(request)


def test_factor_model_catalog_cannot_omit_stock_industry_dimension() -> None:
    request = _request((FactorRiskPosition(1, 1.0, "stock"),))
    factors = _STYLE_FACTORS
    without_industry = FactorRiskRequest(
        positions=request.positions,
        exposure_frame=request.exposure_frame,
        factor_names=factors,
        factor_covariance=np.diag([0.01] * len(factors)),
        idiosyncratic_variances=request.idiosyncratic_variances,
        evidence=request.evidence,
    )

    with pytest.raises(FactorRiskError, match="industry factor"):
        StockFactorRiskEstimator().estimate(without_industry)


@pytest.mark.pit
def test_future_factor_exposure_sentinel_is_excluded() -> None:
    request = _request((FactorRiskPosition(1, 1.0, "stock"),))
    future = _exposures(include_second_stock=False).with_columns(
        pl.lit(999.0).alias("exposure"),
        pl.lit(datetime(2026, 4, 2, tzinfo=UTC)).alias("knowledge_time"),
        pl.lit(datetime(2026, 4, 2, tzinfo=UTC)).alias("publication_time"),
    )
    with_future = FactorRiskRequest(
        positions=request.positions,
        exposure_frame=pl.concat((request.exposure_frame, future)),
        factor_names=request.factor_names,
        factor_covariance=request.factor_covariance,
        idiosyncratic_variances=request.idiosyncratic_variances,
        evidence=request.evidence,
    )

    expected = StockFactorRiskEstimator().estimate(request)
    actual = StockFactorRiskEstimator().estimate(with_future)

    assert actual.portfolio_exposures == expected.portfolio_exposures
    assert actual.total_variance == expected.total_variance
