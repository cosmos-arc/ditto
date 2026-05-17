"""Evaluation-layer Protocol contracts for external data providers."""

from __future__ import annotations

from typing import Protocol

import polars as pl

__all__ = [
    "ClosePriceProvider",
    "ForwardReturnProvider",
    "RiskFactorProvider",
]


class ForwardReturnProvider(Protocol):
    """Protocol for providing forward return data."""

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: str = "none",
    ) -> pl.DataFrame:
        """Compute forward returns for the given parameters."""
        ...


class ClosePriceProvider(Protocol):
    """Protocol for providing close price data for IC decay computation."""

    def get_close_prices(
        self,
        asset_class: str,
        start: str,
        end: str,
        adj: str = "none",
    ) -> pl.DataFrame:
        """Return close prices as ``[date, entity, close]``."""
        ...


class RiskFactorProvider(Protocol):
    """Provide risk factor data for Fama-MacBeth and factor exposure."""

    def get_risk_factors(
        self,
        factor_ids: list[str],
        start: str,
        end: str,
    ) -> dict[str, pl.DataFrame]:
        """
        Retrieve risk factor DataFrames for the given IDs and date range.

        Args:
            factor_ids: List of risk factor identifiers to retrieve.
            start: Start date string (inclusive).
            end: End date string (inclusive).

        Returns:
            ``{factor_id: DataFrame[date, entity, value]}`` mapping.

        """
        ...
