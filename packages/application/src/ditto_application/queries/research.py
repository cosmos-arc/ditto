"""
App-layer research dataset snapshot facade.

ADR: narrow import allowance
  This module imports directly from ditto_analysis.research and
  ditto_data.services (MetadataService).  The ditto_analysis dependency is
  confined to the research query path only — no production orchestration
  code depends on ditto_analysis.  If an alternative analysis backend
  emerges, introduce application-owned Protocol ports (ResearchCatalogPort,
  ResearchArtifactPort) at that time.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.domain import (
    DatasetSnapshot,
    KnownAtPolicy,
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
    SpineSnapshot,
    SpineSpec,
)
from ditto_data.services.metadata_service import MetadataService
from ditto_features.errors import DerivedNotFoundError
from ditto_features.services import (
    DerivedArtifactReader,
    VersionResolutionStrategy,
)

from ditto_application.config import now_iso
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.research_helpers import (
    _attach_known_at,
    _build_dataset_report,
    _DatasetSnapshotContract,
    _hydrate_dataset_spec,
    _hydrate_spine_spec,
    _manifest_hash,
    _normalize_trade_dates,
    _pit_join,
)

__all__ = ["ResearchDatasetFacade"]

_BUILD_REPORT_FILENAME = "build_report.json"
_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _ResolvedDerivedInputs(NamedTuple):
    """derived inputs 解析结果 — 提供精确类型以通过 pyright strict 检查."""

    frame: pl.DataFrame
    versions: dict[str, int]
    inputs: tuple[dict[str, str | int], ...]
    source_ids: tuple[str, ...]


def _sanitize_table_name(dataset_id: str) -> str:
    """
    Convert dataset_id to a safe SQLite table name.

    Replaces ``-`` with ``_`` and validates the result matches
    a legal SQL identifier pattern.  Raises ``ValueError`` for
    identifiers that could enable SQL injection.
    """
    table_name = dataset_id.replace("-", "_")
    if not _VALID_TABLE_NAME.match(table_name):
        raise AppQueryError(f"Invalid dataset_id for table name: {dataset_id!r}")
    return table_name


class ResearchDatasetFacade:
    """Build immutable research spine and dataset snapshots."""

    def __init__(
        self,
        *,
        metadata_service: MetadataService,
        research_catalog_service: ResearchCatalogService,
        artifact_reader: DerivedArtifactReader,
        research_artifact_service: ResearchArtifactService,
    ) -> None:
        self._metadata_service = metadata_service
        self._research_catalog_service = research_catalog_service
        self._artifact_reader = artifact_reader
        self._artifact_service = research_artifact_service

    def build(
        self,
        *,
        dataset_id: str,
        start: str,
        end: str,
        version_overrides: dict[str, int] | None = None,
        explicit_cutoff: str | None = None,
    ) -> DatasetSnapshot:
        """Build one immutable research dataset snapshot."""
        dataset_spec = _hydrate_dataset_spec(
            self._require_dataset_spec_record(dataset_id),
        )
        dataset_spec.validate_spec()
        spine_spec = _hydrate_spine_spec(
            self._require_spine_spec_record(dataset_spec.spine_id),
        )
        spine_spec.validate_spec()
        spine_snapshot = self._build_spine_snapshot(
            spine_spec=spine_spec,
            start=start,
            end=end,
        )
        spine_frame = self._artifact_service.read_parquet(spine_snapshot.data_path)
        known_at_policy = (
            KnownAtPolicy.EXPLICIT_CUTOFF
            if explicit_cutoff is not None
            else dataset_spec.known_at_policy
        )
        dataset_frame = _attach_known_at(
            frame=spine_frame,
            known_at_policy=known_at_policy,
            explicit_cutoff=explicit_cutoff,
        ).with_row_index("sample_row_id")
        universe_ids = tuple(
            int(i) for i in dataset_frame["instrument_id"].unique().to_list()
        )
        resolved = self._resolve_derived_inputs(
            derived_ids=dataset_spec.derived_ids,
            universe_ids=universe_ids,
            end=end,
            overrides=version_overrides or {},
            dataset_frame=dataset_frame,
        )
        dataset_frame = resolved.frame.drop("sample_row_id").sort(
            ["instrument_id", "trade_date"]
        )
        snapshot_contract = _DatasetSnapshotContract(
            known_at_policy=known_at_policy,
            effective_cutoff=explicit_cutoff,
            resolved_versions=resolved.versions,
            resolved_inputs=resolved.inputs,
            source_snapshot_ids=resolved.source_ids,
        )
        build_report = _build_dataset_report(
            dataset_frame=dataset_frame,
            derived_ids=dataset_spec.derived_ids,
            spine_row_count=spine_snapshot.row_count,
            snapshot_contract=snapshot_contract,
        )
        return self._write_dataset_snapshot(
            dataset_id=dataset_id,
            spine_snapshot=spine_snapshot,
            dataset_spec_version=dataset_spec.version,
            spine_spec_version=spine_spec.version,
            dataset_frame=dataset_frame,
            snapshot_contract=snapshot_contract,
            build_report=build_report,
        )

    def _resolve_derived_inputs(
        self,
        *,
        derived_ids: tuple[str, ...],
        universe_ids: tuple[int, ...],
        end: str,
        overrides: dict[str, int],
        dataset_frame: pl.DataFrame,
    ) -> _ResolvedDerivedInputs:
        """解析 derived inputs，依次 PIT join 到 dataset_frame."""
        resolved_versions: dict[str, int] = {}
        resolved_inputs: list[dict[str, str | int]] = []
        source_snapshot_ids: set[str] = set()
        for derived_id in derived_ids:
            resolved_version = overrides.get(derived_id)
            if resolved_version is None:
                resolved_version = self._artifact_reader.resolve_serving_version(
                    derived_id,
                    strategy=VersionResolutionStrategy.FALLBACK_TO_ACTIVE,
                )
            resolved_versions[derived_id] = resolved_version
            artifact_path = self._artifact_service.resolve_artifact_relative_path(
                derived_id,
                resolved_version,
            )
            if artifact_path is None:
                artifact_path = (
                    f"derived/artifacts/unknown/{derived_id}/v{resolved_version}"
                )
            resolved_inputs.append(
                {
                    "derived_id": derived_id,
                    "version": resolved_version,
                    "artifact_path": artifact_path,
                }
            )
            source_snapshot_ids.update(
                self._artifact_service.read_source_snapshot_ids(artifact_path)
            )
            source_frame = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=resolved_version,
                instrument_ids=universe_ids,
                end=end,
            )
            dataset_frame = _pit_join(
                left_frame=dataset_frame,
                source_frame=source_frame,
                derived_id=derived_id,
            )
        return _ResolvedDerivedInputs(
            frame=dataset_frame,
            versions=resolved_versions,
            inputs=tuple(resolved_inputs),
            source_ids=tuple(sorted(source_snapshot_ids)),
        )

    def load_build_report(self, snapshot: DatasetSnapshot) -> dict[str, object]:
        """Load the persisted build report for one dataset snapshot."""
        snapshot_dir = snapshot.data_path.rsplit("/", 1)[0]
        report_relative = f"{snapshot_dir}/{_BUILD_REPORT_FILENAME}"
        return self._artifact_service.read_json(report_relative)

    def export(
        self,
        snapshot: DatasetSnapshot,
        fmt: str,
        path: Path,
    ) -> None:
        """
        导出研究数据集快照到指定格式.

        Args:
            snapshot: 数据集快照.
            fmt: 导出格式 ("csv", "sqlite").
            path: 输出文件路径.

        Raises:
            ValueError: 不支持的格式.

        """
        df = self._artifact_service.read_parquet(snapshot.data_path)
        if fmt == "csv":
            df.write_csv(str(path))
        elif fmt == "sqlite":
            self._export_sqlite(df, snapshot.dataset_id, path)
        else:
            raise AppQueryError(f"不支持的导出格式: {fmt}")

    @staticmethod
    def _export_sqlite(
        df: pl.DataFrame,
        dataset_id: str,
        path: Path,
    ) -> None:
        """将 DataFrame 导出为 SQLite 表."""
        table_name = _sanitize_table_name(dataset_id)
        conn = sqlite3.connect(str(path))
        records = df.to_dicts()
        if records:
            columns = list(records[0].keys())
            col_str = ",".join(columns)
            placeholders = ",".join(["?"] * len(columns))
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table_name} ({col_str})",
            )
            conn.executemany(
                f"INSERT INTO {table_name} VALUES ({placeholders})",
                [tuple(r.values()) for r in records],
            )
            conn.commit()
        conn.close()

    def _persist_artifact_snapshot(
        self,
        *,
        frame: pl.DataFrame,
        relative_path: str,
        metadata: dict[str, object],
        extra_json_files: dict[str, dict[str, object]] | None = None,
    ) -> str:
        """写入 parquet + metadata JSON（含 manifest_hash），返回 manifest_hash."""
        self._artifact_service.write_parquet(relative_path, frame)
        snapshot_dir = relative_path.rsplit("/", 1)[0]
        manifest_hash = _manifest_hash(metadata)
        self._artifact_service.write_json(
            f"{snapshot_dir}/metadata.json",
            {**metadata, "manifest_hash": manifest_hash},
        )
        if extra_json_files:
            for filename, content in extra_json_files.items():
                self._artifact_service.write_json(
                    f"{snapshot_dir}/{filename}",
                    content,
                )
        return manifest_hash

    def _build_spine_snapshot(
        self,
        *,
        spine_spec: SpineSpec,
        start: str,
        end: str,
    ) -> SpineSnapshot:
        calendar_frame = self._metadata_service.calendar.list_calendar_range(
            start=start,
            end=end,
            only_open=True,
        )
        trade_dates = _normalize_trade_dates(calendar_frame)
        instrument_ids = self._metadata_service.get_universe(
            spine_spec.universe_id,
            asof=end,
        )
        if trade_dates.is_empty() or not instrument_ids:
            spine_frame = pl.DataFrame(
                schema={
                    "instrument_id": pl.Int64,
                    "trade_date": pl.Date,
                }
            )
        else:
            spine_frame = (
                trade_dates.join(
                    pl.DataFrame({"instrument_id": instrument_ids}),
                    how="cross",
                )
                .select(["instrument_id", "trade_date"])
                .sort(["instrument_id", "trade_date"])
            )

        created_at = now_iso()
        snapshot_id = f"rsp-{uuid4().hex[:12]}"
        relative_path = (
            f"derived/research/spines/{spine_spec.spine_id}"
            f"/snapshots/{snapshot_id}/data.parquet"
        )
        metadata: dict[str, object] = {
            "spine_snapshot_id": snapshot_id,
            "spine_id": spine_spec.spine_id,
            "version": spine_spec.version,
            "start": start,
            "end": end,
            "row_count": spine_frame.height,
            "data_path": relative_path,
            "created_at": created_at,
        }
        manifest_hash = self._persist_artifact_snapshot(
            frame=spine_frame,
            relative_path=relative_path,
            metadata=metadata,
        )
        record = ResearchSpineSnapshotRecord(
            spine_snapshot_id=snapshot_id,
            spine_id=spine_spec.spine_id,
            snapshot_start=start,
            snapshot_end=end,
            row_count=spine_frame.height,
            data_path=relative_path,
            manifest_hash=manifest_hash,
            created_at=created_at,
            version=spine_spec.version,
        )
        self._research_catalog_service.save_spine_snapshot(record)
        return SpineSnapshot(
            spine_snapshot_id=snapshot_id,
            spine_id=spine_spec.spine_id,
            start=start,
            end=end,
            row_count=spine_frame.height,
            data_path=relative_path,
            manifest_hash=manifest_hash,
            created_at=created_at,
            version=spine_spec.version,
        )

    def _write_dataset_snapshot(
        self,
        *,
        dataset_id: str,
        spine_snapshot: SpineSnapshot,
        dataset_spec_version: int,
        spine_spec_version: int,
        dataset_frame: pl.DataFrame,
        snapshot_contract: _DatasetSnapshotContract,
        build_report: dict[str, object],
    ) -> DatasetSnapshot:
        created_at = now_iso()
        snapshot_id = f"rds-{uuid4().hex[:12]}"
        relative_path = (
            f"derived/research/datasets/{dataset_id}"
            f"/snapshots/{snapshot_id}/data.parquet"
        )
        metadata: dict[str, object] = {
            "snapshot_id": snapshot_id,
            "dataset_id": dataset_id,
            "dataset_spec_version": dataset_spec_version,
            "spine_spec_version": spine_spec_version,
            "spine_snapshot_id": spine_snapshot.spine_snapshot_id,
            "start": spine_snapshot.start,
            "end": spine_snapshot.end,
            "row_count": dataset_frame.height,
            "data_path": relative_path,
            "known_at_policy": snapshot_contract.known_at_policy.value,
            "effective_cutoff": snapshot_contract.effective_cutoff,
            "resolved_versions": snapshot_contract.resolved_versions,
            "resolved_inputs": list(snapshot_contract.resolved_inputs),
            "source_snapshot_ids": list(snapshot_contract.source_snapshot_ids),
            "builder_version": snapshot_contract.builder_version,
            "created_at": created_at,
        }
        manifest_hash = self._persist_artifact_snapshot(
            frame=dataset_frame,
            relative_path=relative_path,
            metadata=metadata,
            extra_json_files={_BUILD_REPORT_FILENAME: build_report},
        )
        record = ResearchDatasetSnapshotRecord(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
            dataset_spec_version=dataset_spec_version,
            spine_snapshot_id=spine_snapshot.spine_snapshot_id,
            snapshot_start=spine_snapshot.start,
            snapshot_end=spine_snapshot.end,
            row_count=dataset_frame.height,
            data_path=relative_path,
            manifest_hash=manifest_hash,
            known_at_policy=snapshot_contract.known_at_policy.value,
            effective_cutoff=snapshot_contract.effective_cutoff,
            spine_spec_version=spine_spec_version,
            resolved_versions=snapshot_contract.resolved_versions,
            resolved_inputs=snapshot_contract.resolved_inputs,
            source_snapshot_ids=snapshot_contract.source_snapshot_ids,
            builder_version=snapshot_contract.builder_version,
            created_at=created_at,
        )
        self._research_catalog_service.save_dataset_snapshot(record)
        return DatasetSnapshot(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
            dataset_spec_version=dataset_spec_version,
            spine_snapshot_id=spine_snapshot.spine_snapshot_id,
            start=spine_snapshot.start,
            end=spine_snapshot.end,
            row_count=dataset_frame.height,
            data_path=relative_path,
            manifest_hash=manifest_hash,
            known_at_policy=snapshot_contract.known_at_policy,
            effective_cutoff=snapshot_contract.effective_cutoff,
            spine_spec_version=spine_spec_version,
            resolved_versions=snapshot_contract.resolved_versions,
            resolved_inputs=snapshot_contract.resolved_inputs,
            source_snapshot_ids=snapshot_contract.source_snapshot_ids,
            builder_version=snapshot_contract.builder_version,
            created_at=created_at,
        )

    def _require_dataset_spec_record(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSpecRecord:
        record = self._research_catalog_service.get_dataset_spec(dataset_id)
        if record is None:
            raise DerivedNotFoundError(derived_id=dataset_id)
        return record

    def _require_spine_spec_record(self, spine_id: str) -> ResearchSpineSpecRecord:
        record = self._research_catalog_service.get_spine_spec(spine_id)
        if record is None:
            raise DerivedNotFoundError(derived_id=spine_id)
        return record
