"""Portfolio optimization allocators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
import polars as pl

from ditto_portfolio.rebalancing.allocation import InverseVolAllocator

__all__ = [
    "CovarianceProvider",
    "DiagonalVolCovariance",
    "MeanVarianceAllocator",
]

_EPSILON = 1e-12
_ZERO_VARIANCE_SCALE = 1e-9


class CovarianceProvider(Protocol):
    """Provides an asset covariance matrix for a candidate portfolio frame."""

    def covariance(self, frame: pl.DataFrame) -> npt.NDArray[np.float64]:
        """Return an ``n x n`` covariance matrix in frame row order."""
        ...


@dataclass(frozen=True)
class DiagonalVolCovariance:
    """Build a diagonal covariance matrix from a volatility column."""

    vol_column: str = "volatility"

    def covariance(self, frame: pl.DataFrame) -> npt.NDArray[np.float64]:
        """Return ``diag(volatility ** 2)`` in input row order."""
        if frame.is_empty():
            return np.zeros((0, 0), dtype=np.float64)
        vol = np.asarray(frame[self.vol_column].to_numpy(), dtype=np.float64)
        clean_vol = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)
        clean_vol = np.clip(clean_vol, 0.0, None)
        return np.diag(clean_vol**2)


@dataclass(frozen=True)
class MeanVarianceAllocator:
    """
    Long-only minimum-variance allocator with bounded weights.

    The Wave 1 implementation deliberately avoids a solver dependency. For a
    diagonal covariance matrix, the minimum-variance solution is proportional to
    inverse variance; max-weight constraints are applied with deterministic
    water filling.
    """

    covariance: CovarianceProvider = field(default_factory=DiagonalVolCovariance)
    max_weight: float = 1.0
    cash_target: float = 0.0
    fallback_vol_column: str = "volatility"

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Add a ``weight`` column with optimized target weights."""
        n_assets = frame.height
        if n_assets == 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        total_investable = _effective_investable(
            n_assets=n_assets,
            cash_target=self.cash_target,
            max_weight=self.max_weight,
        )
        if total_investable <= 0.0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        covariance = self.covariance.covariance(frame)
        if not _is_valid_covariance(covariance, n_assets):
            return self._fallback_allocate(frame, total_investable=total_investable)

        variances = np.diag(covariance)
        if not np.all(np.isfinite(variances)):
            return self._fallback_allocate(frame, total_investable=total_investable)

        preferences = _preferences_from_variances(variances)
        weights = _bounded_proportional_weights(
            preferences=preferences,
            total=total_investable,
            cap=max(0.0, self.max_weight),
        )
        return frame.with_columns(pl.Series("weight", weights))

    def _fallback_allocate(
        self,
        frame: pl.DataFrame,
        *,
        total_investable: float,
    ) -> pl.DataFrame:
        if self.fallback_vol_column not in frame.columns:
            weights = _bounded_proportional_weights(
                preferences=np.ones(frame.height, dtype=np.float64),
                total=total_investable,
                cap=max(0.0, self.max_weight),
            )
            return frame.with_columns(pl.Series("weight", weights))

        fallback_result = InverseVolAllocator(
            vol_column=self.fallback_vol_column,
            cash_target=self.cash_target,
        ).allocate(frame)
        raw_weights = np.asarray(
            fallback_result["weight"].to_numpy(),
            dtype=np.float64,
        )
        weights = _bounded_proportional_weights(
            preferences=raw_weights,
            total=total_investable,
            cap=max(0.0, self.max_weight),
        )
        return frame.with_columns(pl.Series("weight", weights))


def _effective_investable(
    *,
    n_assets: int,
    cash_target: float,
    max_weight: float,
) -> float:
    requested = max(0.0, 1.0 - cash_target)
    capacity = max(0.0, max_weight) * n_assets
    return min(requested, capacity)


def _is_valid_covariance(
    covariance: npt.NDArray[np.float64],
    n_assets: int,
) -> bool:
    return covariance.shape == (n_assets, n_assets)


def _preferences_from_variances(
    variances: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    clean_variances = np.nan_to_num(
        variances,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    clean_variances = np.clip(clean_variances, 0.0, None)
    positive = clean_variances[clean_variances > 0.0]
    if positive.size == 0:
        return cast(
            "npt.NDArray[np.float64]",
            np.ones(clean_variances.shape[0], dtype=np.float64),
        )
    floor = float(np.min(positive)) * _ZERO_VARIANCE_SCALE
    safe_variances = np.where(clean_variances > 0.0, clean_variances, floor)
    return 1.0 / safe_variances


def _bounded_proportional_weights(
    *,
    preferences: npt.NDArray[np.float64],
    total: float,
    cap: float,
) -> npt.NDArray[np.float64]:
    n_assets = preferences.shape[0]
    weights = np.zeros(n_assets, dtype=np.float64)
    if n_assets == 0 or total <= 0.0 or cap <= 0.0:
        return weights

    clean_preferences = np.nan_to_num(
        preferences,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    clean_preferences = np.clip(clean_preferences, 0.0, None)
    if float(np.sum(clean_preferences)) <= 0.0:
        clean_preferences = np.ones(n_assets, dtype=np.float64)

    remaining = min(total, cap * n_assets)
    available = np.ones(n_assets, dtype=bool)
    while remaining > _EPSILON and bool(np.any(available)):
        available_indices = np.flatnonzero(available)
        active_preferences = clean_preferences[available]
        preference_sum = float(np.sum(active_preferences))
        if preference_sum <= 0.0:
            proposed = np.full(
                available_indices.shape[0],
                remaining / available_indices.shape[0],
                dtype=np.float64,
            )
        else:
            proposed = remaining * active_preferences / preference_sum

        capped = proposed > cap + _EPSILON
        if not bool(np.any(capped)):
            weights[available_indices] = proposed
            return weights

        capped_indices = available_indices[capped]
        weights[capped_indices] = cap
        remaining -= cap * capped_indices.shape[0]
        available[capped_indices] = False

    return weights
