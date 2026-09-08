"""Service wrapper for derived artifact persistence operations."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ditto_features.models.derived import DerivedSpecRecord, PartitionInfo
from ditto_features.storage.derived_artifact_writer import (
    ArtifactMetadataParams,
    ArtifactMetadataUpdateParams,
    DerivedArtifactWriter,
)

__all__ = [
    "ArtifactMetadataParams",
    "ArtifactMetadataUpdateParams",
    "ArtifactPersistenceService",
]


class ArtifactPersistenceService:
    """
    Service facade for derived artifact persistence.

    Wraps :class:`DerivedArtifactWriter` to provide a service-layer boundary
    that Port can depend on without reaching into the stores layer directly.
    """

    def __init__(
        self,
        artifact_root: Path,
        *,
        _writer: DerivedArtifactWriter | None = None,
    ) -> None:
        self._artifact_root = Path(artifact_root)
        self._writer = (
            _writer if _writer is not None else DerivedArtifactWriter(artifact_root)
        )

    # -- public API (mirrors DerivedArtifactWriter)

    def write_ephemeral_result(
        self,
        *,
        spec: DerivedSpecRecord,
        run_id: str,
        frame: pl.DataFrame,
    ) -> None:
        """Write ephemeral (derive profile) result to parquet."""
        self._writer.write_ephemeral_result(
            spec=spec,
            run_id=run_id,
            frame=frame,
        )

    def write_durable_partitions(
        self,
        *,
        spec: DerivedSpecRecord,
        time_key: str,
        run_id: str,
        frame: pl.DataFrame,
        request_start: str,
        request_end: str,
        source_snapshot_id: str | None,
    ) -> tuple[PartitionInfo, ...]:
        """Write durable (series) partitions as per-year parquet files."""
        return self._writer.write_durable_partitions(
            spec=spec,
            time_key=time_key,
            run_id=run_id,
            frame=frame,
            request_start=request_start,
            request_end=request_end,
            source_snapshot_id=source_snapshot_id,
        )

    def write_artifact_metadata(
        self,
        params: ArtifactMetadataParams,
    ) -> None:
        """Write run metadata as artifact_metadata.json."""
        self._writer.write_artifact_metadata(params)

    def update_artifact_metadata(
        self,
        params: ArtifactMetadataUpdateParams,
    ) -> None:
        """Read existing metadata JSON and inject publication safety info."""
        self._writer.update_artifact_metadata(params)
