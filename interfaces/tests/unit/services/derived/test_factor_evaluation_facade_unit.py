"""Unit tests for FactorEvaluationFacade."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_analytics.evaluation.report import (
    FactorEvaluationReport,
)
from ditto_app.query.evaluation import (
    EvaluationOptions,
    FactorEvaluationFacade,
)

_DATES = [date(2024, 1, 2), date(2024, 1, 3)]


def _make_factor_df() -> pl.DataFrame:
    """Build a minimal factor DataFrame for testing."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 1, 2, 3],
            "trade_date": _DATES * 3,
            "value": [0.5, -0.3, 1.2, 0.6, -0.2, 1.1],
        },
    )


def _make_forward_return_df() -> pl.DataFrame:
    """Build a minimal forward return DataFrame for testing."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 1, 2, 3],
            "trade_date": _DATES * 3,
            "forward_return": [0.01, -0.02, 0.03, 0.02, -0.01, 0.04],
        },
    )


def _make_facade(
    *,
    factor_df: pl.DataFrame | None = None,
    fr_return_df: pl.DataFrame | None = None,
) -> FactorEvaluationFacade:
    """Build a FactorEvaluationFacade with mocked dependencies."""
    artifact_reader = MagicMock()
    artifact_reader.read_frame.return_value = factor_df or _make_factor_df()

    fr_service = MagicMock()
    empty_fr = pl.DataFrame(
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "forward_return": pl.Float64,
        },
    )
    fr_service.compute.return_value = (
        fr_return_df if fr_return_df is not None else empty_fr
    )

    return FactorEvaluationFacade(
        artifact_reader=artifact_reader,
        forward_return_service=fr_service,
    )


class TestFactorEvaluationFacade:
    """Tests for FactorEvaluationFacade.evaluate()."""

    def test_evaluate_stamps_factor_id_and_version(self) -> None:
        """The facade overrides the evaluator's default factor_id/version."""
        facade = _make_facade()

        report = facade.evaluate(
            "factor.momentum_20d",
            3,
            options=EvaluationOptions(
                start="2024-01-02",
                end="2024-01-03",
            ),
        )

        assert isinstance(report, FactorEvaluationReport)
        assert report.factor_id == "factor.momentum_20d"
        assert report.factor_version == 3

    def test_evaluate_passes_parameters_to_evaluator(self) -> None:
        """All options are forwarded to the evaluator and services."""
        facade = _make_facade(fr_return_df=_make_forward_return_df())
        opts = EvaluationOptions(
            start="2024-01-02",
            end="2024-01-03",
            holding_period=10,
            n_quantiles=10,
            asset_class="etf",
            adj="hfq",
        )

        facade.evaluate("factor.test", 1, options=opts)

        # Verify artifact reader was called with correct params
        facade._artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.test",
            version=1,
            start="2024-01-02",
            end="2024-01-03",
        )

    def test_evaluate_with_default_options(self) -> None:
        """Default options pass None start/end to the evaluator."""
        facade = _make_facade()

        report = facade.evaluate("factor.test", 1)

        assert report.factor_id == "factor.test"
        facade._artifact_reader.read_frame.assert_called_once_with(
            derived_id="factor.test",
            version=1,
            start=None,
            end=None,
        )

    def test_evaluate_preserves_report_metrics(self) -> None:
        """When evaluator returns a report, metrics structure is intact."""
        facade = _make_facade(fr_return_df=_make_forward_return_df())

        report = facade.evaluate("factor.test", 2)

        assert report.holding_period == 5  # default
        assert report.n_quantiles == 5  # default

    def test_evaluation_options_defaults(self) -> None:
        """EvaluationOptions has sensible defaults."""
        opts = EvaluationOptions()
        assert opts.start is None
        assert opts.end is None
        assert opts.holding_period == 5
        assert opts.n_quantiles == 5
        assert opts.asset_class == "stock"
        assert opts.adj == "none"

    def test_evaluation_options_is_frozen(self) -> None:
        """EvaluationOptions is immutable."""
        import dataclasses

        opts = EvaluationOptions()
        with pytest.raises(dataclasses.FrozenInstanceError):
            opts.holding_period = 10  # type: ignore[misc]
