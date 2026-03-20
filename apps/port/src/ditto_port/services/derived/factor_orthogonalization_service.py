"""
Factor orthogonalization service.

Orchestrates loading factor artifacts and delegating to the Core
orthogonalize() pure function.
"""

from __future__ import annotations

import polars as pl
from ditto_core.engine.evaluation.metrics import orthogonalize
from ditto_datahub.services.derived import DerivedArtifactReader

__all__ = ["FactorOrthogonalizationService"]


class FactorOrthogonalizationService:
    """
    Orthogonalize a target factor against control factors.

    Loads the target and control factor artifacts via
    :class:`DerivedArtifactReader`, joins them on
    ``(trade_date, instrument_id)``, and delegates to the pure-function
    :func:`~ditto_core.engine.evaluation.metrics.orthogonalize` from
    ``ditto_core``.
    """

    def __init__(self, artifact_reader: DerivedArtifactReader) -> None:
        self._artifact_reader = artifact_reader

    def load_and_orthogonalize(
        self,
        target_id: str,
        target_version: int,
        other_factor_ids: list[tuple[str, int]],
        *,
        start: str,
        end: str,
        method: str = "sequential",
    ) -> pl.DataFrame:
        """
        Load factors and compute orthogonalized target values.

        Args:
            target_id: Derived artifact identifier for the target factor.
            target_version: Version of the target artifact.
            other_factor_ids: List of ``(factor_id, version)`` pairs for
                control factors.
            start: Start date (``YYYY-MM-DD``).
            end: End date (``YYYY-MM-DD``).
            method: Orthogonalization method (``"sequential"`` or
                ``"symmetric"``).

        Returns:
            ``pl.DataFrame[trade_date, instrument_id,
            orthogonalized_value]``.

        """
        target_df = self._artifact_reader.read_frame(
            derived_id=target_id,
            version=target_version,
            start=start,
            end=end,
        )

        if not other_factor_ids:
            # No control factors -- return the target values unchanged.
            if target_df.is_empty():
                return pl.DataFrame(
                    schema={
                        "trade_date": pl.Utf8,
                        "instrument_id": pl.Int64,
                        "orthogonalized_value": pl.Float64,
                    },
                )
            return target_df.select(
                pl.col("trade_date"),
                pl.col("instrument_id"),
                pl.col("value").alias("orthogonalized_value"),
            )

        # Load and join control factors.  Each factor gets a
        # ``factor_name`` column so that the orthogonalize() function
        # can distinguish them.
        control_frames: list[pl.DataFrame] = []
        for factor_id, factor_version in other_factor_ids:
            frame = self._artifact_reader.read_frame(
                derived_id=factor_id,
                version=factor_version,
                start=start,
                end=end,
            )
            if frame.is_empty():
                continue
            control_frames.append(
                frame.select(
                    pl.col("trade_date"),
                    pl.col("instrument_id"),
                    pl.col("value"),
                    pl.lit(factor_id).alias("factor_name"),
                ),
            )

        if not control_frames:
            if target_df.is_empty():
                return pl.DataFrame(
                    schema={
                        "trade_date": pl.Utf8,
                        "instrument_id": pl.Int64,
                        "orthogonalized_value": pl.Float64,
                    },
                )
            return target_df.select(
                pl.col("trade_date"),
                pl.col("instrument_id"),
                pl.col("value").alias("orthogonalized_value"),
            )

        factors_df = pl.concat(control_frames)

        return orthogonalize(
            target_df,
            factors_df,
            method=method,
        )
