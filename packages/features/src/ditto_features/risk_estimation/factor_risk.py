"""PIT-safe stock style and industry factor risk decomposition."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import polars as pl
from ditto_kernel.identity import InstrumentId

from ditto_features.risk_estimation.covariance import RiskEstimationEvidence

__all__ = [
    "FactorRiskError",
    "FactorRiskPosition",
    "FactorRiskRequest",
    "FactorRiskResult",
    "StockFactorRiskEstimator",
]

_STYLE_FACTORS = (
    "size",
    "value",
    "momentum",
    "volatility",
    "liquidity",
    "quality",
)
_REQUIRED_COLUMNS = (
    "instrument_id",
    "factor_name",
    "exposure",
    "knowledge_time",
    "publication_time",
    "source_snapshot_id",
)
_PSD_REJECTION_TOLERANCE = -1e-8
_WEIGHT_TOLERANCE = 1e-8


class FactorRiskError(ValueError):
    """Raised when stock factor risk evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class FactorRiskPosition:
    """Portfolio weight and asset class needed for exposure availability."""

    instrument_id: InstrumentId
    weight: float
    asset_type: str


@dataclass(frozen=True)
class FactorRiskRequest:
    """Visible factor exposures, covariance, and idiosyncratic risk inputs."""

    positions: tuple[FactorRiskPosition, ...]
    exposure_frame: pl.DataFrame
    factor_names: tuple[str, ...]
    factor_covariance: np.ndarray
    idiosyncratic_variances: Mapping[InstrumentId, float]
    evidence: RiskEstimationEvidence


@dataclass(frozen=True)
class FactorRiskResult:
    """Euler-reconciled factor variance decomposition and availability status."""

    availability: str
    stock_weight: float
    unavailable_weight: float
    total_variance: float
    total_risk: float
    portfolio_exposures: Mapping[str, float]
    marginal_contributions: Mapping[str, float]
    variance_contributions: Mapping[str, float]
    percentage_contributions: Mapping[str, float]
    euler_residual: float
    evidence: RiskEstimationEvidence


class StockFactorRiskEstimator:
    """Decompose stock risk while leaving ETF exposure explicitly unavailable."""

    def estimate(self, request: FactorRiskRequest) -> FactorRiskResult:
        """Return a factor report or fail closed for any missing stock evidence."""
        self._validate_request(request)
        stock_positions = tuple(
            position
            for position in request.positions
            if position.asset_type.lower() == "stock" and position.weight != 0.0
        )
        stock_weight = sum(position.weight for position in stock_positions)
        unavailable_weight = sum(
            position.weight
            for position in request.positions
            if position.asset_type.lower() != "stock"
        )
        if not stock_positions:
            return FactorRiskResult(
                availability="unavailable",
                stock_weight=0.0,
                unavailable_weight=unavailable_weight,
                total_variance=0.0,
                total_risk=0.0,
                portfolio_exposures={},
                marginal_contributions={},
                variance_contributions={},
                percentage_contributions={},
                euler_residual=0.0,
                evidence=request.evidence,
            )
        exposures = self._visible_exposures(request, stock_positions)
        portfolio_exposures = np.zeros(len(request.factor_names), dtype=float)
        for position in stock_positions:
            instrument_exposures = exposures[position.instrument_id]
            portfolio_exposures += position.weight * np.asarray(
                [instrument_exposures.get(name, 0.0) for name in request.factor_names]
            )
        factor_covariance = (
            request.factor_covariance + request.factor_covariance.T
        ) / 2.0
        factor_marginal = factor_covariance @ portfolio_exposures
        factor_contributions = portfolio_exposures * factor_marginal
        specific_contributions = {
            f"specific:{position.instrument_id}": (
                position.weight**2
                * float(request.idiosyncratic_variances[position.instrument_id])
            )
            for position in stock_positions
        }
        contributions = {
            name: float(value)
            for name, value in zip(
                request.factor_names,
                factor_contributions,
                strict=True,
            )
        }
        contributions.update(specific_contributions)
        total_variance = float(sum(contributions.values()))
        if not math.isfinite(total_variance) or total_variance <= 0.0:
            raise FactorRiskError("total stock factor variance must be positive")
        total_risk = math.sqrt(total_variance)
        marginal = {
            name: float(value) / total_risk
            for name, value in zip(
                request.factor_names,
                factor_marginal,
                strict=True,
            )
        }
        marginal.update(
            {
                f"specific:{position.instrument_id}": (
                    position.weight
                    * float(request.idiosyncratic_variances[position.instrument_id])
                    / total_risk
                )
                for position in stock_positions
            }
        )
        percentages = {
            name: value / total_variance for name, value in contributions.items()
        }
        return FactorRiskResult(
            availability="partial" if unavailable_weight > 0.0 else "available",
            stock_weight=stock_weight,
            unavailable_weight=unavailable_weight,
            total_variance=total_variance,
            total_risk=total_risk,
            portfolio_exposures={
                name: float(value)
                for name, value in zip(
                    request.factor_names,
                    portfolio_exposures,
                    strict=True,
                )
            },
            marginal_contributions=marginal,
            variance_contributions=contributions,
            percentage_contributions=percentages,
            euler_residual=total_variance - sum(contributions.values()),
            evidence=request.evidence,
        )

    @staticmethod
    def _validate_request(request: FactorRiskRequest) -> None:
        StockFactorRiskEstimator._validate_positions(request)
        StockFactorRiskEstimator._validate_factor_model(request)

    @staticmethod
    def _validate_positions(request: FactorRiskRequest) -> None:
        if not request.positions:
            raise FactorRiskError("positions must be non-empty")
        if len({position.instrument_id for position in request.positions}) != len(
            request.positions
        ):
            raise FactorRiskError("position instrument ids must be unique")
        if not all(
            math.isfinite(position.weight) and position.weight >= 0.0
            for position in request.positions
        ):
            raise FactorRiskError("position weights must be finite and non-negative")
        if sum(position.weight for position in request.positions) > (
            1.0 + _WEIGHT_TOLERANCE
        ):
            raise FactorRiskError("position weights cannot exceed one")

    @staticmethod
    def _validate_factor_model(request: FactorRiskRequest) -> None:
        if not request.factor_names or len(set(request.factor_names)) != len(
            request.factor_names
        ):
            raise FactorRiskError("factor names must be non-empty and unique")
        missing_styles = [
            name for name in _STYLE_FACTORS if name not in request.factor_names
        ]
        if missing_styles:
            raise FactorRiskError("factor model requires all six style factors")
        if not any(name.startswith("industry:") for name in request.factor_names):
            raise FactorRiskError("factor model requires at least one industry factor")
        covariance = np.asarray(request.factor_covariance, dtype=float)
        count = len(request.factor_names)
        if covariance.shape != (count, count) or not np.isfinite(covariance).all():
            raise FactorRiskError("factor covariance has invalid shape or values")
        if (
            float(np.linalg.eigvalsh((covariance + covariance.T) / 2.0).min())
            < _PSD_REJECTION_TOLERANCE
        ):
            raise FactorRiskError("factor covariance must be PSD")
        missing = [
            name for name in _REQUIRED_COLUMNS if name not in request.exposure_frame
        ]
        if missing:
            raise FactorRiskError(f"factor exposure frame missing columns: {missing}")

    @staticmethod
    def _visible_exposures(
        request: FactorRiskRequest,
        stock_positions: tuple[FactorRiskPosition, ...],
    ) -> dict[InstrumentId, dict[str, float]]:
        evidence = request.evidence
        stock_ids = tuple(position.instrument_id for position in stock_positions)
        visible = request.exposure_frame.filter(
            pl.col("instrument_id").is_in(stock_ids)
            & (pl.col("knowledge_time") <= evidence.knowledge_cutoff)
            & (pl.col("publication_time") <= evidence.publication_cutoff)
            & pl.col("source_snapshot_id").is_in(evidence.source_snapshot_ids)
        )
        duplicate = (
            visible.group_by(("instrument_id", "factor_name"))
            .len()
            .filter(pl.col("len") > 1)
        )
        if not duplicate.is_empty():
            raise FactorRiskError("visible factor exposures contain duplicates")
        result: dict[InstrumentId, dict[str, float]] = {}
        for position in stock_positions:
            rows = visible.filter(pl.col("instrument_id") == position.instrument_id)
            names = rows.get_column("factor_name").to_list()
            values = rows.get_column("exposure").cast(pl.Float64).to_list()
            if not all(math.isfinite(value) for value in values):
                raise FactorRiskError(
                    f"stock {position.instrument_id} has non-finite exposure"
                )
            mapping = dict(zip(names, values, strict=True))
            missing_styles = [name for name in _STYLE_FACTORS if name not in mapping]
            industries = [name for name in mapping if name.startswith("industry:")]
            if missing_styles or len(industries) != 1:
                raise FactorRiskError(
                    " ".join(
                        (
                            f"stock {position.instrument_id} requires six styles",
                            "and one industry",
                        )
                    )
                )
            if industries[0] not in request.factor_names:
                raise FactorRiskError(
                    f"stock {position.instrument_id} industry factor is not in model"
                )
            if position.instrument_id not in request.idiosyncratic_variances:
                raise FactorRiskError(
                    f"stock {position.instrument_id} lacks idiosyncratic variance"
                )
            specific = float(request.idiosyncratic_variances[position.instrument_id])
            if not math.isfinite(specific) or specific < 0.0:
                raise FactorRiskError(
                    f"stock {position.instrument_id} has invalid idiosyncratic variance"
                )
            result[position.instrument_id] = mapping
        return result
