"""Unified derived query service contract."""

from __future__ import annotations

import polars as pl

from ditto_datahub.errors import DerivedNotFoundError, DerivedValidationError
from ditto_datahub.services.derived.artifact_reader import DerivedArtifactReader
from ditto_datahub.services.derived.queries import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from ditto_datahub.services.derived.results import (
    empty_compare_result,
    empty_latest_result,
    empty_series_result,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

__all__ = ["DerivedQueryService"]


class DerivedQueryService:
    """Artifact-backed query service for unified derived access."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        artifact_reader: DerivedArtifactReader,
    ) -> None:
        self._catalog_service = catalog_service
        self._artifact_reader = artifact_reader

    def find_latest(self, query: DerivedLatestQuery) -> pl.DataFrame:
        """Read latest serving or offline values from materialized artifacts."""
        self._validate_source_scope(query.source_scope)
        frames: list[pl.DataFrame] = []
        for derived_id in query.derived_ids:
            version = self._resolve_query_version(
                derived_id=derived_id,
                source_scope=query.source_scope,
                requested_version=query.version,
            )
            frame = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                instrument_ids=query.instrument_ids,
                as_of=query.as_of,
            )
            if frame.is_empty():
                continue
            latest = (
                frame.sort(["instrument_id", "trade_date"], descending=[False, True])
                .group_by("instrument_id", maintain_order=True)
                .first()
                .sort("instrument_id")
            )
            frames.append(
                _shape_latest_frame(
                    latest,
                    derived_id=derived_id,
                    version=version,
                )
            )
        return _concat_frames(frames, empty_latest_result())

    def find_series(self, query: DerivedSeriesQuery) -> pl.DataFrame:
        """Read offline or serving series slices from materialized artifacts."""
        self._validate_source_scope(query.source_scope)
        frames: list[pl.DataFrame] = []
        for derived_id in query.derived_ids:
            version = self._resolve_query_version(
                derived_id=derived_id,
                source_scope=query.source_scope,
                requested_version=query.version,
            )
            frame = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                instrument_ids=query.instrument_ids,
                start=query.start,
                end=query.end,
                as_of=query.as_of,
            )
            if frame.is_empty():
                continue
            frames.append(
                _shape_series_frame(
                    frame,
                    derived_id=derived_id,
                    version=version,
                )
            )
        result = _concat_frames(frames, empty_series_result())
        if query.limit is not None and not result.is_empty():
            return result.head(query.limit)
        return result

    def compare_sources(self, query: DerivedCompareQuery) -> pl.DataFrame:
        """Compare serving and offline slices backed by the same artifact reader."""
        for source_scope in query.compare_sources:
            self._validate_source_scope(source_scope)
        frames: list[pl.DataFrame] = []
        for derived_id in query.derived_ids:
            serving_version = self._artifact_reader.resolve_serving_version(derived_id)
            offline_version = self._artifact_reader.resolve_offline_version(
                derived_id,
                requested_version=query.version,
            )
            serving = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=serving_version,
                instrument_ids=query.instrument_ids,
                start=query.start,
                end=query.end,
            )
            offline = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=offline_version,
                instrument_ids=query.instrument_ids,
                start=query.start,
                end=query.end,
            )
            if serving.is_empty() and offline.is_empty():
                continue
            frames.append(
                _shape_compare_frame(
                    serving=serving,
                    offline=offline,
                    derived_id=derived_id,
                )
            )
        return _concat_frames(frames, empty_compare_result())

    def _resolve_query_version(
        self,
        *,
        derived_id: str,
        source_scope: DerivedSourceScope,
        requested_version: int | None,
    ) -> int:
        if source_scope == DerivedSourceScope.OFFLINE:
            return self._artifact_reader.resolve_offline_version(
                derived_id,
                requested_version=requested_version,
            )
        if requested_version is not None:
            spec = self._catalog_service.get_spec(derived_id, requested_version)
            if spec is None:
                raise DerivedNotFoundError(
                    derived_id=derived_id, version=requested_version
                )
            version_record = self._catalog_service.get_version(
                derived_id,
                requested_version,
            )
            if version_record is None:
                raise DerivedNotFoundError(
                    derived_id=derived_id, version=requested_version
                )
            return requested_version
        return self._artifact_reader.resolve_serving_version(derived_id)

    def _validate_source_scope(self, source_scope: DerivedSourceScope) -> None:
        if source_scope not in (
            DerivedSourceScope.SERVING,
            DerivedSourceScope.OFFLINE,
        ):
            raise DerivedValidationError(
                field="source_scope",
                value=str(source_scope),
                reason="unsupported source_scope",
            )


def _shape_latest_frame(
    frame: pl.DataFrame,
    *,
    derived_id: str,
    version: int,
) -> pl.DataFrame:
    return frame.select(
        pl.lit(derived_id).alias("derived_id"),
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("value").cast(pl.Float64),
        pl.col("trade_date").cast(pl.Date),
        _optional_column(frame, "bar_time", pl.Time()),
        _optional_column(frame, "asof_ts", pl.Datetime()),
        pl.lit(version).cast(pl.Int64).alias("version"),
    )


def _shape_series_frame(
    frame: pl.DataFrame,
    *,
    derived_id: str,
    version: int,
) -> pl.DataFrame:
    return frame.sort(["instrument_id", "trade_date"]).select(
        pl.lit(derived_id).alias("derived_id"),
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("trade_date").cast(pl.Date),
        _optional_column(frame, "bar_time", pl.Time()),
        pl.col("value").cast(pl.Float64),
        _optional_column(frame, "asof_ts", pl.Datetime()),
        pl.lit(version).cast(pl.Int64).alias("version"),
    )


def _shape_compare_frame(
    *,
    serving: pl.DataFrame,
    offline: pl.DataFrame,
    derived_id: str,
) -> pl.DataFrame:
    combined = pl.concat(
        [
            serving.select(
                "instrument_id",
                "trade_date",
                pl.col("value").cast(pl.Float64).alias("value"),
            ).with_columns(pl.lit("serving").alias("source")),
            offline.select(
                "instrument_id",
                "trade_date",
                pl.col("value").cast(pl.Float64).alias("value"),
            ).with_columns(pl.lit("offline").alias("source")),
        ],
        how="diagonal_relaxed",
    )
    pivoted = (
        combined.pivot(
            index=["instrument_id", "trade_date"],
            on="source",
            values="value",
            aggregate_function="first",
        )
        .rename({"serving": "serving_value", "offline": "offline_value"})
        .sort(["instrument_id", "trade_date"])
    )
    return pivoted.select(
        pl.lit(derived_id).alias("derived_id"),
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("trade_date").cast(pl.Date),
        pl.col("serving_value").cast(pl.Float64),
        pl.col("offline_value").cast(pl.Float64),
        (
            pl.col("serving_value").cast(pl.Float64)
            - pl.col("offline_value").cast(pl.Float64)
        )
        .round(12)
        .alias("diff"),
    )


def _optional_column(
    frame: pl.DataFrame,
    column_name: str,
    dtype: pl.DataType,
) -> pl.Expr:
    if column_name in frame.columns:
        return pl.col(column_name).cast(dtype)
    return pl.lit(None).cast(dtype).alias(column_name)


def _concat_frames(
    frames: list[pl.DataFrame],
    empty_frame: pl.DataFrame,
) -> pl.DataFrame:
    if not frames:
        return empty_frame
    return pl.concat(frames, how="vertical")
