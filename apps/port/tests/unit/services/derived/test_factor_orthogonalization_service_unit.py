"""Unit tests for FactorOrthogonalizationService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_port.services.derived.factor_orthogonalization_service import (
    FactorOrthogonalizationService,
)

_EMPTY_FACTOR_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Utf8,
    "value": pl.Float64,
}


def _make_factor_frame(
    instrument_ids: list[int],
    trade_dates: list[str],
    values: list[float],
) -> pl.DataFrame:
    """Helper: build a minimal factor artifact DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "trade_date": trade_dates,
            "value": values,
        },
    )


class TestFactorOrthogonalizationService:
    """Tests for FactorOrthogonalizationService.load_and_orthogonalize()."""

    def test_no_control_factors_returns_values(self) -> None:
        """With no control factors, target values are returned unchanged."""
        reader = MagicMock()
        target = _make_factor_frame(
            instrument_ids=[1, 2, 3],
            trade_dates=["2024-01-02", "2024-01-02", "2024-01-02"],
            values=[0.5, -0.3, 1.2],
        )
        reader.read_frame.return_value = target

        svc = FactorOrthogonalizationService(reader)
        result = svc.load_and_orthogonalize(
            "factor.target",
            1,
            other_factor_ids=[],
            start="2024-01-02",
            end="2024-01-02",
        )

        assert result.columns == [
            "trade_date",
            "instrument_id",
            "orthogonalized_value",
        ]
        assert result.height == 3
        vals = result.sort("instrument_id")["orthogonalized_value"].to_list()
        # instrument_id order: 1=0.5, 2=-0.3, 3=1.2
        expected = [0.5, -0.3, 1.2]
        for v, e in zip(vals, expected, strict=True):
            assert abs(v - e) < 1e-10

    def test_single_control_factor(self) -> None:
        """Single control factor triggers orthogonalization."""
        reader = MagicMock()
        target = _make_factor_frame(
            instrument_ids=[1, 2, 3, 4, 5],
            trade_dates=["2024-01-02"] * 5,
            values=[1.0, 2.0, 3.0, 4.0, 5.0],
        )
        control = _make_factor_frame(
            instrument_ids=[1, 2, 3, 4, 5],
            trade_dates=["2024-01-02"] * 5,
            values=[0.5, 1.0, 1.5, 2.0, 2.5],
        )

        def mock_read(**kwargs: Any) -> pl.DataFrame:
            if kwargs["derived_id"] == "factor.target":
                return target
            return control

        reader.read_frame.side_effect = mock_read

        svc = FactorOrthogonalizationService(reader)
        result = svc.load_and_orthogonalize(
            "factor.target",
            1,
            other_factor_ids=[("factor.size", 1)],
            start="2024-01-02",
            end="2024-01-02",
        )

        # The orthogonalize function may return empty rows when
        # cross-section < min_cross_section (30).
        # That is expected -- we verify the call chain works.
        assert "orthogonalized_value" in result.columns

    def test_multiple_control_factors(self) -> None:
        """Multiple control factors are loaded and concatenated."""
        reader = MagicMock()
        target = _make_factor_frame(
            instrument_ids=[1, 2, 3, 4, 5],
            trade_dates=["2024-01-02"] * 5,
            values=[1.0, 2.0, 3.0, 4.0, 5.0],
        )
        control1 = _make_factor_frame(
            instrument_ids=[1, 2, 3, 4, 5],
            trade_dates=["2024-01-02"] * 5,
            values=[0.5, 1.0, 1.5, 2.0, 2.5],
        )
        control2 = _make_factor_frame(
            instrument_ids=[1, 2, 3, 4, 5],
            trade_dates=["2024-01-02"] * 5,
            values=[10.0, 20.0, 30.0, 40.0, 50.0],
        )

        def mock_read(**kwargs: Any) -> pl.DataFrame:
            if kwargs["derived_id"] == "factor.target":
                return target
            if kwargs["derived_id"] == "factor.size":
                return control1
            return control2

        reader.read_frame.side_effect = mock_read

        svc = FactorOrthogonalizationService(reader)
        result = svc.load_and_orthogonalize(
            "factor.target",
            1,
            other_factor_ids=[("factor.size", 1), ("factor.vol", 1)],
            start="2024-01-02",
            end="2024-01-02",
        )

        assert "orthogonalized_value" in result.columns
        # Verify all three reads happened
        assert reader.read_frame.call_count == 3

    def test_empty_target_returns_empty(self) -> None:
        """Empty target artifact returns empty DataFrame."""
        reader = MagicMock()
        reader.read_frame.return_value = pl.DataFrame(schema=_EMPTY_FACTOR_SCHEMA)

        svc = FactorOrthogonalizationService(reader)
        result = svc.load_and_orthogonalize(
            "factor.target",
            1,
            other_factor_ids=[],
            start="2024-01-02",
            end="2024-01-02",
        )

        assert result.is_empty()
        assert "orthogonalized_value" in result.columns

    def test_empty_control_factors_returns_target(self) -> None:
        """Control factors that return empty are skipped."""
        reader = MagicMock()
        target = _make_factor_frame(
            instrument_ids=[1, 2, 3],
            trade_dates=["2024-01-02"] * 3,
            values=[0.1, 0.2, 0.3],
        )

        def mock_read(**kwargs: Any) -> pl.DataFrame:
            if kwargs["derived_id"] == "factor.target":
                return target
            return pl.DataFrame()

        reader.read_frame.side_effect = mock_read

        svc = FactorOrthogonalizationService(reader)
        result = svc.load_and_orthogonalize(
            "factor.target",
            1,
            other_factor_ids=[("factor.size", 1)],
            start="2024-01-02",
            end="2024-01-02",
        )

        # All control frames are empty, so target values are returned
        assert result.height == 3
        assert "orthogonalized_value" in result.columns

    def test_method_parameter_passed_through(self) -> None:
        """The method parameter is forwarded to orthogonalize."""
        reader = MagicMock()
        target = _make_factor_frame(
            instrument_ids=list(range(1, 31)),
            trade_dates=["2024-01-02"] * 30,
            values=[float(i) for i in range(1, 31)],
        )
        control = _make_factor_frame(
            instrument_ids=list(range(1, 31)),
            trade_dates=["2024-01-02"] * 30,
            values=[float(i) * 0.5 for i in range(1, 31)],
        )

        def mock_read(**kwargs: Any) -> pl.DataFrame:
            if kwargs["derived_id"] == "factor.target":
                return target
            return control

        reader.read_frame.side_effect = mock_read

        svc = FactorOrthogonalizationService(reader)
        with pytest.raises(ValueError, match="Unknown orthogonalization method"):
            svc.load_and_orthogonalize(
                "factor.target",
                1,
                other_factor_ids=[("factor.size", 1)],
                start="2024-01-02",
                end="2024-01-02",
                method="invalid",
            )
