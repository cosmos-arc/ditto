"""Artifact persistence writer for unified derived materialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

import orjson
import polars as pl
from ditto_core.engine.materialization import Analysis, CompileIdentity
from ditto_core.engine.specs import DerivedSpec
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)

__all__ = ["DerivedArtifactWriter", "PartitionInfo", "extract_partition_keys"]


@dataclass(frozen=True)
class PartitionInfo:
    """Metadata for a single artifact partition."""

    partition_key: str
    partition_path: str
    row_count: int
    checksum: str | None


class DerivedArtifactWriter:
    """
    Artifact persistence writer for unified derived materialization.

    Handles all file system I/O for derived artifact persistence, including
    ephemeral results (DERIVE profile), durable partitions (SERIES profile),
    run metadata JSON files, and publication safety metadata injection.
    """

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = Path(artifact_root)

    def write_ephemeral_result(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        frame: pl.DataFrame,
    ) -> None:
        """Write ephemeral (derive profile) result to parquet."""
        ephemeral_dir = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
            / "_ephemeral"
            / run_id
        )
        ephemeral_dir.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(ephemeral_dir / "result.parquet")

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
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
        )
        version_root.mkdir(parents=True, exist_ok=True)
        partitions: list[PartitionInfo] = []
        trade_date_expr = pl.col(spec.effective_time_keys[0]).cast(pl.Utf8)
        for partition_key in extract_partition_keys(frame, spec):
            partition_frame = frame.filter(
                trade_date_expr.str.slice(0, 4) == partition_key
            )
            partition_path = version_root / f"{partition_key}.parquet"
            temp_path = version_root / f"{partition_key}.tmp.parquet"
            partition_frame.write_parquet(temp_path)
            temp_path.replace(partition_path)
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
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
            / f"v{spec.version}"
        )
        metadata_dir = version_root / "_runs" / run_id
        metadata_dir.mkdir(parents=True, exist_ok=True)
        partition_dicts = [
            {
                "partition_key": p.partition_key,
                "partition_path": p.partition_path,
                "row_count": p.row_count,
                "checksum": p.checksum,
            }
            for p in partitions
        ]
        metadata_dir.joinpath("artifact_metadata.json").write_bytes(
            orjson.dumps(
                {
                    "run_id": run_id,
                    "compile_identity": asdict(compile_identity),
                    "analysis": asdict(analysis),
                    "input_snapshots": [source_snapshot_id]
                    if source_snapshot_id is not None
                    else [],
                    "coverage": {
                        "start": request_start,
                        "end": request_end,
                    },
                    "partitions_written": partition_dicts,
                },
                option=orjson.OPT_INDENT_2,
            )
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
        metadata_path = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec.materialization_profile.value.lower()
            / spec.id
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
        payload["compile_identity"] = asdict(compile_identity)
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
        metadata_path.write_bytes(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        )


def extract_partition_keys(frame: pl.DataFrame, spec: DerivedSpec) -> tuple[str, ...]:
    """Extract unique year-based partition keys from the time column."""
    partition_series = (
        frame.select(pl.col(spec.effective_time_keys[0]).cast(pl.Utf8).str.slice(0, 4))
        .to_series()
        .unique()
        .sort()
    )
    return tuple(str(value) for value in partition_series.to_list())
