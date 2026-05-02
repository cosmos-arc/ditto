"""Artifact persistence writer for unified derived materialization."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import orjson
import polars as pl
from ditto_data.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)
from ditto_platform.foundation import logger
from ditto_platform.foundation.util.io import (
    ParquetCompression,
    atomic_bytes_write,
    atomic_write,
)

from ditto_features.models.derived import DerivedSpecRecord, PartitionInfo

__all__ = ["ArtifactMetadataParams", "DerivedArtifactWriter", "extract_partition_keys"]


@dataclass(frozen=True)
class ArtifactMetadataParams:
    """
    制品元数据写入参数.

    Attributes:
        spec: 派生规格记录.
        run_id: 运行 ID.
        compile_identity: 编译标识（已序列化为 dict）.
        analysis: 分析结果（已序列化为 dict）.
        partitions: 分区信息.
        request_start: 请求开始日期.
        request_end: 请求结束日期.
        source_snapshot_id: 源快照 ID.

    """

    spec: DerivedSpecRecord
    run_id: str
    compile_identity: dict[str, Any]
    analysis: dict[str, Any]
    partitions: tuple[PartitionInfo, ...]
    request_start: str
    request_end: str
    source_snapshot_id: str | None


class DerivedArtifactWriter:
    """
    Artifact persistence writer for unified derived materialization.

    Handles all file system I/O for derived artifact persistence, including
    ephemeral results (DERIVE profile), durable partitions (SERIES profile),
    run metadata JSON files, and publication safety metadata injection.

    All writes use atomic patterns (write-then-rename) to prevent partial
    file exposure.  Multi-partition writes follow a two-phase commit protocol
    so that either every partition is committed or none are.
    """

    _compression: ParquetCompression

    def __init__(
        self,
        artifact_root: Path,
        *,
        compression: ParquetCompression = "zstd",
    ) -> None:
        self._artifact_root = Path(artifact_root)
        self._compression = compression

    # ------------------------------------------------------------------
    # Ephemeral result (DERIVE profile)
    # ------------------------------------------------------------------

    def write_ephemeral_result(
        self,
        *,
        spec: DerivedSpecRecord,
        run_id: str,
        frame: pl.DataFrame,
    ) -> None:
        """Write ephemeral (derive profile) result to parquet atomically."""
        ephemeral_dir = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.lower()
            / spec.derived_id
            / f"v{spec.version}"
            / "_ephemeral"
            / run_id
        )
        ephemeral_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(
            frame,
            ephemeral_dir / "result.parquet",
            compression=self._compression,
        )

    # ------------------------------------------------------------------
    # Durable partitions (SERIES profile) -- two-phase commit
    # ------------------------------------------------------------------

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
        """
        Write durable (series) partitions as per-year parquet files.

        Uses a two-phase commit to guarantee all-or-nothing semantics:

        * **Phase 1** -- write every partition to a ``.tmp.parquet`` file.
        * **Phase 2** -- atomically rename all temp files to their final names.

        If Phase 1 raises, all temp files are cleaned up before re-raising.
        Checksums are computed on the *final* files after rename.
        """
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.lower()
            / spec.derived_id
            / f"v{spec.version}"
        )
        version_root.mkdir(parents=True, exist_ok=True)

        trade_date_expr = pl.col(time_key).cast(pl.Utf8)
        partition_keys = extract_partition_keys(frame, time_key)

        # Collect (partition_key, partition_frame, temp_path, final_path)
        pending: list[tuple[str, pl.DataFrame, Path, Path]] = []
        for partition_key in partition_keys:
            partition_frame = frame.filter(
                trade_date_expr.str.slice(0, 4) == partition_key
            )
            partition_path = version_root / f"{partition_key}.parquet"
            temp_path = version_root / f"{partition_key}.tmp.parquet"
            pending.append((partition_key, partition_frame, temp_path, partition_path))

        # --- Phase 1: write all temp files ---
        try:
            for _partition_key, partition_frame, temp_path, _partition_path in pending:
                partition_frame.write_parquet(temp_path, compression=self._compression)
        except BaseException:
            # Clean up any temp files that were written before the failure
            written_temps = self._existing_temp_files(
                [temp_path for _, _, temp_path, _ in pending]
            )
            self._cleanup_temp_files(written_temps)
            raise

        # --- Phase 2: atomic rename all temp -> final ---
        partitions: list[PartitionInfo] = []
        for _pk, _pf, temp_path, partition_path in pending:
            temp_path.replace(partition_path)

        # Compute checksums on final files (after rename)
        for partition_key, partition_frame, _temp_path, partition_path in pending:
            checksum = sha256(partition_path.read_bytes()).hexdigest()
            partitions.append(
                PartitionInfo(
                    partition_key=partition_key,
                    partition_path=str(partition_path.relative_to(self._artifact_root)),
                    row_count=partition_frame.height,
                    checksum=checksum,
                )
            )

        return tuple(partitions)

    # ------------------------------------------------------------------
    # Incremental partition merge (MAT-M-6)
    # ------------------------------------------------------------------

    def write_incremental_partition(
        self,
        *,
        spec: DerivedSpecRecord,
        time_key: str,
        run_id: str,
        frame: pl.DataFrame,
        source_snapshot_id: str | None,
    ) -> tuple[PartitionInfo, ...]:
        """
        Merge new data into existing year partitions incrementally.

        For each partition key present in *frame*:

        1. If an existing parquet file exists, read it and concat with
           the new data using ``diagonal_relaxed`` schema handling.
        2. Group by ``(instrument_id, trade_date)`` and take the **last**
           row so that newer values overwrite older ones.
        3. Write the merged result atomically.

        If no existing file exists, the partition is written as-is.

        Returns:
            Metadata for every partition that was written.

        """
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.lower()
            / spec.derived_id
            / f"v{spec.version}"
        )
        version_root.mkdir(parents=True, exist_ok=True)

        partition_keys = extract_partition_keys(frame, time_key)
        trade_date_expr = pl.col(time_key).cast(pl.Utf8)

        partitions: list[PartitionInfo] = []

        for partition_key in partition_keys:
            partition_frame = frame.filter(
                trade_date_expr.str.slice(0, 4) == partition_key
            )
            partition_path = version_root / f"{partition_key}.parquet"

            if partition_path.exists():
                existing = pl.read_parquet(partition_path)
                merged = _merge_partitions(existing, partition_frame, time_key)
            else:
                merged = partition_frame

            atomic_write(merged, partition_path, compression=self._compression)
            checksum = sha256(partition_path.read_bytes()).hexdigest()
            partitions.append(
                PartitionInfo(
                    partition_key=partition_key,
                    partition_path=str(partition_path.relative_to(self._artifact_root)),
                    row_count=merged.height,
                    checksum=checksum,
                )
            )

        return tuple(partitions)

    # ------------------------------------------------------------------
    # Artifact metadata
    # ------------------------------------------------------------------

    def write_artifact_metadata(
        self,
        params: ArtifactMetadataParams,
    ) -> None:
        """Write run metadata as artifact_metadata.json atomically."""
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / params.spec.materialization_profile.lower()
            / params.spec.derived_id
            / f"v{params.spec.version}"
        )
        metadata_dir = version_root / "_runs" / params.run_id
        metadata_dir.mkdir(parents=True, exist_ok=True)
        partition_dicts = [
            {
                "partition_key": p.partition_key,
                "partition_path": p.partition_path,
                "row_count": p.row_count,
                "checksum": p.checksum,
            }
            for p in params.partitions
        ]
        metadata_path = metadata_dir / "artifact_metadata.json"
        atomic_bytes_write(
            orjson.dumps(
                {
                    "run_id": params.run_id,
                    "compile_identity": params.compile_identity,
                    "analysis": params.analysis,
                    "input_snapshots": [params.source_snapshot_id]
                    if params.source_snapshot_id is not None
                    else [],
                    "coverage": {
                        "start": params.request_start,
                        "end": params.request_end,
                    },
                    "partitions_written": partition_dicts,
                },
                option=orjson.OPT_INDENT_2,
            ),
            metadata_path,
        )

    def update_artifact_metadata(
        self,
        *,
        spec: DerivedSpecRecord,
        run_id: str,
        compile_identity: dict[str, Any],
        partitions: tuple[PartitionInfo, ...],
        source_snapshot_id: str | None,
        manifest_record: CompatibilityManifestRecord,
        minimal_dq_record: DerivedMinimalDQSummaryRecord,
    ) -> None:
        """Read existing metadata JSON, inject publication safety, write atomically."""
        metadata_path = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.lower()
            / spec.derived_id
            / f"v{spec.version}"
            / "_runs"
            / run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        payload["publication"] = {
            "manifest_hash": manifest_record.manifest_hash,
            "compatibility_manifest": manifest_record.payload,
            "minimal_dq_summary": {
                "run_id": minimal_dq_record.run_id,
                "passed": minimal_dq_record.passed,
                "error_count": minimal_dq_record.error_count,
                **minimal_dq_record.payload,
            },
        }
        payload["compile_identity"] = compile_identity
        payload["input_snapshots"] = (
            [source_snapshot_id] if source_snapshot_id is not None else []
        )
        payload["partitions_written"] = [
            {
                "partition_key": p.partition_key,
                "partition_path": p.partition_path,
                "row_count": p.row_count,
                "checksum": p.checksum,
            }
            for p in partitions
        ]
        atomic_bytes_write(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS),
            metadata_path,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cleanup_temp_files(temp_paths: list[Path]) -> None:
        """Remove temporary files, ignoring errors for missing files."""
        for path in temp_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to clean up temp file: %s", path, exc_info=True)

    @staticmethod
    def _existing_temp_files(candidates: list[Path]) -> list[Path]:
        """Return only the paths that actually exist on disk."""
        return [p for p in candidates if p.exists()]


def extract_partition_keys(
    frame: pl.DataFrame,
    time_key: str,
) -> tuple[str, ...]:
    """Extract unique year-based partition keys from the time column."""
    partition_series = (
        frame.select(pl.col(time_key).cast(pl.Utf8).str.slice(0, 4))
        .to_series()
        .unique()
        .sort()
    )
    return tuple(str(value) for value in partition_series.to_list())


def _merge_partitions(
    existing: pl.DataFrame,
    new_data: pl.DataFrame,
    time_key: str,
) -> pl.DataFrame:
    """
    Merge existing partition data with new incremental data.

    Uses ``pl.concat(how='diagonal_relaxed')`` for schema evolution,
    then deduplicates by ``(instrument_id, time_key)`` keeping the last
    occurrence so that newer values overwrite older ones.
    """
    combined = pl.concat([existing, new_data], how="diagonal_relaxed")
    return (
        combined.sort(time_key)
        .group_by(
            "instrument_id",
            time_key,
            maintain_order=True,
        )
        .last()
    )
