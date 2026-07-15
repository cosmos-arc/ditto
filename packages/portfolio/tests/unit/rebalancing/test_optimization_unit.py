"""Portfolio optimization allocator tests."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest


def _frame(
    *,
    instrument_ids: list[int] | None = None,
    volatility: list[float] | None = None,
) -> pl.DataFrame:
    ids = instrument_ids or [1, 2, 3]
    vols = volatility or [0.10, 0.20, 0.30]
    return pl.DataFrame({"instrument_id": ids, "volatility": vols})


class TestDiagonalVolCovariance:
    def test_preserves_instrument_order_in_diagonal_covariance(self) -> None:
        from ditto_portfolio.rebalancing.optimization import DiagonalVolCovariance

        frame = _frame(instrument_ids=[3, 1, 2], volatility=[0.30, 0.10, 0.20])

        covariance = DiagonalVolCovariance().covariance(frame)

        assert covariance.shape == (3, 3)
        assert covariance.diagonal().tolist() == pytest.approx([0.09, 0.01, 0.04])
        np.testing.assert_allclose(
            covariance,
            np.array(
                [
                    [0.09, 0.0, 0.0],
                    [0.0, 0.01, 0.0],
                    [0.0, 0.0, 0.04],
                ]
            ),
        )

    def test_empty_frame_returns_empty_covariance(self) -> None:
        from ditto_portfolio.rebalancing.optimization import DiagonalVolCovariance

        frame = pl.DataFrame(
            {
                "instrument_id": pl.Series([], dtype=pl.Int64),
                "volatility": pl.Series([], dtype=pl.Float64),
            }
        )

        covariance = DiagonalVolCovariance().covariance(frame)

        assert covariance.shape == (0, 0)


class TestMeanVarianceAllocator:
    def test_allocates_lower_weight_to_higher_volatility(self) -> None:
        from ditto_portfolio.rebalancing.optimization import MeanVarianceAllocator

        result = MeanVarianceAllocator().allocate(_frame(volatility=[0.10, 0.20, 0.30]))

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(1.0)
        assert all(weight >= 0.0 for weight in weights)
        assert weights[0] > weights[1] > weights[2]

    def test_respects_cash_target_and_max_weight(self) -> None:
        from ditto_portfolio.rebalancing.optimization import MeanVarianceAllocator

        result = MeanVarianceAllocator(max_weight=0.30, cash_target=0.10).allocate(
            _frame(instrument_ids=[1, 2, 3, 4], volatility=[0.10, 0.20, 0.30, 0.40])
        )

        weights = result["weight"].to_list()
        assert sum(weights) == pytest.approx(0.90)
        assert all(weight <= 0.30 + 1e-12 for weight in weights)
        assert weights[0] == pytest.approx(0.30)

    def test_empty_frame_returns_empty_weight_column(self) -> None:
        from ditto_portfolio.rebalancing.optimization import MeanVarianceAllocator

        frame = pl.DataFrame({"instrument_id": pl.Series([], dtype=pl.Int64)})

        result = MeanVarianceAllocator().allocate(frame)

        assert result.height == 0
        assert "weight" in result.columns

    def test_single_instrument_receives_investable_weight(self) -> None:
        from ditto_portfolio.rebalancing.optimization import MeanVarianceAllocator

        result = MeanVarianceAllocator(cash_target=0.20).allocate(
            _frame(instrument_ids=[1], volatility=[0.15])
        )

        assert result["weight"].to_list() == pytest.approx([0.80])

    def test_falls_back_to_inverse_vol_when_covariance_shape_is_invalid(self) -> None:
        from ditto_portfolio.rebalancing.optimization import MeanVarianceAllocator

        class InvalidCovariance:
            def covariance(self, frame: pl.DataFrame) -> np.ndarray:
                return np.eye(1)

        result = MeanVarianceAllocator(covariance=InvalidCovariance()).allocate(
            _frame(instrument_ids=[1, 2], volatility=[0.10, 0.20])
        )

        assert result["weight"].to_list() == pytest.approx([2.0 / 3.0, 1.0 / 3.0])
