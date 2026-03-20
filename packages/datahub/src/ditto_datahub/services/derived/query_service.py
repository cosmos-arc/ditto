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

    def find_latest(
        self,
        query: DerivedLatestQuery,
        *,
        streaming: bool = False,
    ) -> pl.DataFrame:
        """
        Read latest serving or offline values from materialized artifacts.

        Args:
            query: The latest query parameters.
            streaming: When True, use Polars streaming engine to reduce
                peak memory for large datasets.

        """
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
                streaming=streaming,
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

    def find_series(
        self,
        query: DerivedSeriesQuery,
        *,
        streaming: bool = False,
    ) -> pl.DataFrame:
        """
        Read offline or serving series slices from materialized artifacts.

        Args:
            query: The series query parameters.
            streaming: When True, use Polars streaming engine to reduce
                peak memory for large datasets.

        """
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
                streaming=streaming,
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

    def compare_sources(
        self,
        query: DerivedCompareQuery,
        *,
        streaming: bool = False,
    ) -> pl.DataFrame:
        """
        Compare serving and offline slices backed by the same artifact reader.

        Args:
            query: The compare query parameters.
            streaming: When True, use Polars streaming engine to reduce
                peak memory for large datasets.

        """
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
                streaming=streaming,
            )
            offline = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=offline_version,
                instrument_ids=query.instrument_ids,
                start=query.start,
                end=query.end,
                streaming=streaming,
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

    def query_for_evaluation(
        self,
        *,
        derived_ids: tuple[str, ...],
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        version: int | None = None,
        streaming: bool = False,
    ) -> pl.DataFrame:
        """
        Return a clean evaluation DataFrame for backtesting / strategy evaluation.

        Produces a normalized ``(derived_id, instrument_id, trade_date, value)``
        frame by resolving the offline version for each derived, reading the
        artifact slice, stripping internal columns, concatenating results, and
        sorting by ``(derived_id, instrument_id, trade_date)``.

        Args:
            derived_ids: The derived artifact identifiers.
            instrument_ids: Optional filter for specific instruments.
            start: Optional start date filter (inclusive).
            end: Optional end date filter (inclusive).
            as_of: Optional point-in-time filter (inclusive).
            version: Optional explicit version override.
            streaming: When True, use Polars streaming engine to reduce
                peak memory for large datasets.

        """
        frames: list[pl.DataFrame] = []
        for derived_id in derived_ids:
            resolved_version = self._artifact_reader.resolve_offline_version(
                derived_id,
                requested_version=version,
            )
            frame = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=resolved_version,
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                as_of=as_of,
                streaming=streaming,
            )
            if frame.is_empty():
                continue
            frames.append(
                frame.select(
                    pl.lit(derived_id).alias("derived_id"),
                    pl.col("instrument_id").cast(pl.Int64),
                    pl.col("trade_date").cast(pl.Date),
                    pl.col("value").cast(pl.Float64),
                )
            )
        if not frames:
            return _empty_evaluation_result()
        return pl.concat(frames, how="vertical").sort(
            ["derived_id", "instrument_id", "trade_date"]
        )

    def query_as_lazy(
        self,
        *,
        derived_ids: tuple[str, ...],
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        version: int | None = None,
    ) -> pl.LazyFrame:
        """
        Return a LazyFrame for custom downstream processing.

        Reads each derived artifact in lazy mode (no collection) and
        concatenates the results into a single ``pl.LazyFrame`` that
        callers can further transform before calling ``.collect()``.

        This is the recommended API for large datasets where callers
        want full control over the query plan, e.g. adding additional
        filters, joins, or aggregations before materialization.

        Args:
            derived_ids: The derived artifact identifiers.
            instrument_ids: Optional filter for specific instruments.
            start: Optional start date filter (inclusive).
            end: Optional end date filter (inclusive).
            as_of: Optional point-in-time filter (inclusive).
            version: Optional explicit version override.

        Returns:
            A ``pl.LazyFrame`` that the caller can collect or extend.

        """
        lazy_frames: list[pl.LazyFrame] = []
        for derived_id in derived_ids:
            resolved_version = self._artifact_reader.resolve_offline_version(
                derived_id,
                requested_version=version,
            )
            lf = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=resolved_version,
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                as_of=as_of,
                as_lazy=True,
            )
            if not isinstance(lf, pl.LazyFrame):
                continue
            lazy_frames.append(
                lf.select(
                    pl.lit(derived_id).alias("derived_id"),
                    pl.col("instrument_id").cast(pl.Int64),
                    pl.col("trade_date").cast(pl.Date),
                    pl.col("value").cast(pl.Float64),
                )
            )
        if not lazy_frames:
            return _empty_evaluation_result().lazy()
        return pl.concat(lazy_frames, how="vertical").sort(
            ["derived_id", "instrument_id", "trade_date"]
        )

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


def _empty_evaluation_result() -> pl.DataFrame:
    """Create an empty evaluation result frame with the canonical schema."""
    return pl.DataFrame(
        {
            "derived_id": pl.Series("derived_id", [], dtype=pl.String),
            "instrument_id": pl.Series("instrument_id", [], dtype=pl.Int64),
            "trade_date": pl.Series("trade_date", [], dtype=pl.Date),
            "value": pl.Series("value", [], dtype=pl.Float64),
        }
    )
