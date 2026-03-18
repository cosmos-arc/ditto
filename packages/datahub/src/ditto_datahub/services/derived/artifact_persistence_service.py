"""Service wrapper for derived artifact persistence operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from ditto_datahub.models.derived import PartitionInfo
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)
from ditto_datahub.stores.runtime.derived_artifact_writer import DerivedArtifactWriter

if TYPE_CHECKING:
    from ditto_core.engine.materialization import Analysis, CompileIdentity
    from ditto_core.engine.specs import DerivedSpec

__all__ = ["ArtifactPersistenceService"]


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

    # -- public API (mirrors DerivedArtifactWriter) --

    def write_ephemeral_result(
        self,
        *,
        spec: DerivedSpec,
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
        spec: DerivedSpec,
        run_id: str,
        frame: pl.DataFrame,
        request_start: str,
        request_end: str,
        source_snapshot_id: str | None,
    ) -> tuple[PartitionInfo, ...]:
        """Write durable (series) partitions as per-year parquet files."""
        return self._writer.write_durable_partitions(
            spec=spec,
            run_id=run_id,
            frame=frame,
            request_start=request_start,
            request_end=request_end,
            source_snapshot_id=source_snapshot_id,
        )

    def write_artifact_metadata(  # noqa: PLR0913
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        compile_identity: CompileIdentity,
        analysis: Analysis,
        partitions: tuple[PartitionInfo, ...],
        request_start: str,
        request_end: str,
        source_snapshot_id: str | None,
    ) -> None:
        """Write run metadata as artifact_metadata.json."""
        self._writer.write_artifact_metadata(
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            analysis=analysis,
            partitions=partitions,
            request_start=request_start,
            request_end=request_end,
            source_snapshot_id=source_snapshot_id,
        )

    def update_artifact_metadata(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        compile_identity: CompileIdentity,
        partitions: tuple[PartitionInfo, ...],
        source_snapshot_id: str | None,
        manifest_record: CompatibilityManifestRecord,
        minimal_dq_record: DerivedMinimalDQSummaryRecord,
    ) -> None:
        """Read existing metadata JSON and inject publication safety info."""
        self._writer.update_artifact_metadata(
            spec=spec,
            run_id=run_id,
            compile_identity=compile_identity,
            partitions=partitions,
            source_snapshot_id=source_snapshot_id,
            manifest_record=manifest_record,
            minimal_dq_record=minimal_dq_record,
        )
