"""PIT-safe return matrix assembly and Ledoit-Wolf covariance shrinkage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl
from ditto_kernel.identity import InstrumentId

__all__ = [
    "ReturnMatrixRequest",
    "ReturnRiskEstimate",
    "RiskEstimationError",
    "RiskEstimationEvidence",
    "ShrinkageCovarianceEstimator",
]

_REQUIRED_COLUMNS = (
    "instrument_id",
    "observation_time",
    "knowledge_time",
    "publication_time",
    "source_snapshot_id",
    "return",
)
_MINIMUM_COVARIANCE_OBSERVATIONS = 2
_MINIMUM_COVARIANCE_EIGENVALUE = 1e-12


class RiskEstimationError(ValueError):
    """Raised when a PIT-sensitive risk estimate cannot be produced safely."""


@dataclass(frozen=True)
class RiskEstimationEvidence:
    """Temporal visibility and revision identity for one risk estimate."""

    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject missing or temporally impossible evidence."""
        if not self.source_snapshot_ids or any(
            not value.strip() for value in self.source_snapshot_ids
        ):
            raise RiskEstimationError("source_snapshot_ids must be non-empty")
        if len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise RiskEstimationError("source_snapshot_ids must be unique")
        if self.knowledge_cutoff > self.decision_time:
            raise RiskEstimationError("knowledge_cutoff cannot follow decision_time")
        if self.publication_cutoff > self.decision_time:
            raise RiskEstimationError("publication_cutoff cannot follow decision_time")


@dataclass(frozen=True)
class ReturnMatrixRequest:
    """Long-form visible return observations requested for a fixed universe."""

    frame: pl.DataFrame
    instrument_ids: tuple[InstrumentId, ...]
    evidence: RiskEstimationEvidence
    lookback_sessions: int = 250
    min_observations: int = 60


@dataclass(frozen=True)
class ReturnRiskEstimate:
    """Aligned scenarios and moment estimates with their PIT evidence."""

    instrument_ids: tuple[InstrumentId, ...]
    returns_matrix: np.ndarray
    expected_returns: np.ndarray
    covariance: np.ndarray
    observation_count: int
    shrinkage: float
    covariance_repaired: bool
    evidence: RiskEstimationEvidence


class ShrinkageCovarianceEstimator:
    """Build a visible return matrix and shrink covariance to scaled identity."""

    def estimate(self, request: ReturnMatrixRequest) -> ReturnRiskEstimate:
        """Estimate aligned scenarios, means, and a PSD covariance matrix."""
        self._validate_request(request)
        visible = self._visible_rows(request)
        matrix = self._aligned_matrix(visible, request)
        covariance, shrinkage, repaired = self._ledoit_wolf(matrix)
        return ReturnRiskEstimate(
            instrument_ids=request.instrument_ids,
            returns_matrix=matrix,
            expected_returns=matrix.mean(axis=0),
            covariance=covariance,
            observation_count=matrix.shape[0],
            shrinkage=shrinkage,
            covariance_repaired=repaired,
            evidence=request.evidence,
        )

    @staticmethod
    def _validate_request(request: ReturnMatrixRequest) -> None:
        if not request.instrument_ids:
            raise RiskEstimationError("instrument_ids must be non-empty")
        if len(set(request.instrument_ids)) != len(request.instrument_ids):
            raise RiskEstimationError("instrument_ids must be unique")
        if request.lookback_sessions < request.min_observations:
            raise RiskEstimationError(
                "lookback_sessions must be at least min_observations"
            )
        if request.min_observations < _MINIMUM_COVARIANCE_OBSERVATIONS:
            raise RiskEstimationError("min_observations must be at least 2")
        missing = [name for name in _REQUIRED_COLUMNS if name not in request.frame]
        if missing:
            raise RiskEstimationError(f"return frame missing columns: {missing}")

    @staticmethod
    def _visible_rows(request: ReturnMatrixRequest) -> pl.DataFrame:
        evidence = request.evidence
        visible = request.frame.filter(
            pl.col("instrument_id").is_in(request.instrument_ids)
            & (pl.col("observation_time") < evidence.decision_time)
            & (pl.col("knowledge_time") <= evidence.knowledge_cutoff)
            & (pl.col("publication_time") <= evidence.publication_cutoff)
            & pl.col("source_snapshot_id").is_in(evidence.source_snapshot_ids)
        )
        duplicates = (
            visible.group_by(("instrument_id", "observation_time"))
            .len()
            .filter(pl.col("len") > 1)
        )
        if not duplicates.is_empty():
            raise RiskEstimationError(
                "visible return frame contains duplicate instrument observations"
            )
        return visible.sort(("observation_time", "instrument_id"))

    @staticmethod
    def _aligned_matrix(
        visible: pl.DataFrame,
        request: ReturnMatrixRequest,
    ) -> np.ndarray:
        complete_times = (
            visible.group_by("observation_time")
            .agg(pl.col("instrument_id").n_unique().alias("instrument_count"))
            .filter(pl.col("instrument_count") == len(request.instrument_ids))
            .sort("observation_time")
            .tail(request.lookback_sessions)
            .get_column("observation_time")
            .to_list()
        )
        if len(complete_times) < request.min_observations:
            raise RiskEstimationError(
                " ".join(
                    (
                        f"return matrix requires at least {request.min_observations}",
                        f"complete observations, got {len(complete_times)}",
                    )
                )
            )
        columns: list[np.ndarray] = []
        for instrument_id in request.instrument_ids:
            values = (
                visible.filter(
                    (pl.col("instrument_id") == instrument_id)
                    & pl.col("observation_time").is_in(complete_times)
                )
                .sort("observation_time")
                .get_column("return")
                .cast(pl.Float64)
                .to_numpy()
            )
            columns.append(values)
        matrix = np.column_stack(columns)
        if matrix.shape != (len(complete_times), len(request.instrument_ids)):
            raise RiskEstimationError("return matrix alignment is incomplete")
        if not np.isfinite(matrix).all():
            raise RiskEstimationError("return matrix contains non-finite values")
        return matrix

    @staticmethod
    def _ledoit_wolf(matrix: np.ndarray) -> tuple[np.ndarray, float, bool]:
        centered = matrix - matrix.mean(axis=0, keepdims=True)
        observations, assets = centered.shape
        sample = centered.T @ centered / observations
        mean_variance = float(np.trace(sample) / assets)
        prior = np.eye(assets, dtype=float) * mean_variance
        delta = float(np.square(sample - prior).sum())
        if delta <= np.finfo(float).eps:
            shrinkage = 1.0
        else:
            beta_sum = 0.0
            for row in centered:
                beta_sum += float(np.square(np.outer(row, row) - sample).sum())
            beta = beta_sum / (observations * observations)
            shrinkage = min(max(beta / delta, 0.0), 1.0)
        covariance = shrinkage * prior + (1.0 - shrinkage) * sample
        covariance = (covariance + covariance.T) / 2.0
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        repair_applied = bool(np.any(eigenvalues < _MINIMUM_COVARIANCE_EIGENVALUE))
        eigenvalues = np.maximum(eigenvalues, _MINIMUM_COVARIANCE_EIGENVALUE)
        repaired_covariance = (eigenvectors * eigenvalues) @ eigenvectors.T
        return (
            (repaired_covariance + repaired_covariance.T) / 2.0,
            shrinkage,
            repair_applied,
        )
