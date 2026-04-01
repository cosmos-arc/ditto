"""Port-side research dataset snapshot facade."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

import orjson
import polars as pl
from ditto_datahub.errors import DerivedNotFoundError, DerivedValidationError
from ditto_datahub.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_datahub.services import DerivedArtifactReader, ResearchCatalogService
from ditto_datahub.services.derived import VersionResolutionStrategy
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.research_artifact_service import ResearchArtifactService
from ditto_engine.engine.research import (
    DatasetSnapshot,
    KnownAtPolicy,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
)
from ditto_engine.engine.specs import CalendarId, GrainId

from ._utils import now_iso

__all__ = ["ResearchDatasetFacade"]

_RESEARCH_BUILDER_VERSION = "unified-derived-research-v1"
_BUILD_REPORT_FILENAME = "build_report.json"


@dataclass(frozen=True)
class _DatasetSnapshotContract:
    """Frozen contract payload persisted with each dataset snapshot."""

    known_at_policy: KnownAtPolicy
    effective_cutoff: str | None
    resolved_versions: dict[str, int]
    resolved_inputs: tuple[dict[str, str | int], ...]
    source_snapshot_ids: tuple[str, ...]
    builder_version: str = _RESEARCH_BUILDER_VERSION


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
        )
        dataset_frame = dataset_frame.with_row_index("sample_row_id")

        universe_ids = tuple(
            int(instrument_id)
            for instrument_id in dataset_frame["instrument_id"].unique().to_list()
        )
        resolved_versions: dict[str, int] = {}
        resolved_inputs: list[dict[str, str | int]] = []
        source_snapshot_ids: set[str] = set()
        overrides = version_overrides or {}
        for derived_id in dataset_spec.derived_ids:
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

        dataset_frame = dataset_frame.drop("sample_row_id").sort(
            ["instrument_id", "trade_date"]
        )
        snapshot_contract = _DatasetSnapshotContract(
            known_at_policy=known_at_policy,
            effective_cutoff=explicit_cutoff,
            resolved_versions=resolved_versions,
            resolved_inputs=tuple(resolved_inputs),
            source_snapshot_ids=tuple(sorted(source_snapshot_ids)),
        )
        build_report = _build_dataset_report(
            dataset_frame=dataset_frame,
            derived_ids=dataset_spec.derived_ids,
            spine_row_count=spine_snapshot.row_count,
            snapshot_contract=snapshot_contract,
        )
        snapshot = self._write_dataset_snapshot(
            dataset_id=dataset_id,
            spine_snapshot=spine_snapshot,
            dataset_spec_version=dataset_spec.version,
            spine_spec_version=spine_spec.version,
            dataset_frame=dataset_frame,
            snapshot_contract=snapshot_contract,
            build_report=build_report,
        )
        return snapshot

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
            raise ValueError(f"不支持的导出格式: {fmt}")

    @staticmethod
    def _export_sqlite(
        df: pl.DataFrame,
        dataset_id: str,
        path: Path,
    ) -> None:
        """将 DataFrame 导出为 SQLite 表."""
        conn = sqlite3.connect(str(path))
        table_name = dataset_id.replace("-", "_")
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

    def _build_spine_snapshot(
        self,
        *,
        spine_spec: SpineSpec,
        start: str,
        end: str,
    ) -> SpineSnapshot:
        calendar_frame = self._metadata_service.list_calendar_range(
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
        self._artifact_service.write_parquet(relative_path, spine_frame)
        snapshot_dir = relative_path.rsplit("/", 1)[0]
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
        manifest_hash = _manifest_hash(metadata)
        self._artifact_service.write_json(
            f"{snapshot_dir}/metadata.json",
            {**metadata, "manifest_hash": manifest_hash},
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
        self._artifact_service.write_parquet(relative_path, dataset_frame)
        snapshot_dir = relative_path.rsplit("/", 1)[0]
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
        manifest_hash = _manifest_hash(metadata)
        self._artifact_service.write_json(
            f"{snapshot_dir}/metadata.json",
            {**metadata, "manifest_hash": manifest_hash},
        )
        self._artifact_service.write_json(
            f"{snapshot_dir}/{_BUILD_REPORT_FILENAME}",
            build_report,
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


def _hydrate_spine_spec(record: ResearchSpineSpecRecord) -> SpineSpec:
    return SpineSpec(
        spine_id=record.spine_id,
        universe_id=record.universe_id,
        version=record.version,
        calendar=cast(CalendarId, record.calendar),
        grain=cast(GrainId, record.grain),
        entity_key=record.entity_key,
        description=record.description,
    )


def _hydrate_dataset_spec(record: ResearchDatasetSpecRecord) -> ResearchDatasetSpec:
    return ResearchDatasetSpec(
        dataset_id=record.dataset_id,
        spine_id=record.spine_id,
        derived_ids=record.derived_ids,
        version=record.version,
        join_policy=record.join_policy,
        known_at_policy=KnownAtPolicy(record.known_at_policy),
        late_arrival_policy=LateArrivalPolicy(record.late_arrival_policy),
        description=record.description,
    )


def _normalize_trade_dates(calendar_frame: pl.DataFrame) -> pl.DataFrame:
    if calendar_frame.is_empty():
        return pl.DataFrame(schema={"trade_date": pl.Date})
    trade_dates = calendar_frame.select(
        pl.col("trade_date").cast(pl.Utf8).str.slice(0, 10).str.to_date()
    )
    return trade_dates


def _attach_known_at(
    *,
    frame: pl.DataFrame,
    known_at_policy: KnownAtPolicy,
    explicit_cutoff: str | None,
) -> pl.DataFrame:
    if known_at_policy == KnownAtPolicy.EXPLICIT_CUTOFF:
        if explicit_cutoff is None:
            raise ValueError(
                "explicit_cutoff is required when "
                + "known_at_policy is explicit_cutoff"
            )
        return frame.with_columns(
            pl.lit(_coerce_date(explicit_cutoff)).alias("known_at")
        )
    return frame.with_columns(pl.col("trade_date").alias("known_at"))


def _pit_join(
    *,
    left_frame: pl.DataFrame,
    source_frame: pl.DataFrame,
    derived_id: str,
) -> pl.DataFrame:
    if source_frame.is_empty():
        return left_frame.with_columns(pl.lit(None).cast(pl.Float64).alias(derived_id))

    value_column = _source_value_column(source_frame)
    prepared_source = source_frame.select(
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("trade_date")
        .cast(pl.Utf8)
        .str.slice(0, 10)
        .str.to_date()
        .alias("source_trade_date"),
        pl.coalesce(
            [
                pl.col("availability_time"),
                pl.col("trade_date"),
            ]
        )
        .cast(pl.Utf8)
        .str.slice(0, 10)
        .str.to_date()
        .alias("source_availability_time"),
        pl.col(value_column).cast(pl.Float64).alias(derived_id),
    ).sort(["instrument_id", "source_availability_time", "source_trade_date"])

    joined = left_frame.sort(["instrument_id", "known_at", "trade_date"]).join_asof(
        prepared_source,
        left_on="known_at",
        right_on="source_availability_time",
        by="instrument_id",
        strategy="backward",
    )
    return joined.select([*left_frame.columns, derived_id]).sort("sample_row_id")


def _source_value_column(source_frame: pl.DataFrame) -> str:
    if "value" in source_frame.columns:
        return "value"
    key_columns = {"instrument_id", "trade_date", "availability_time"}
    for column in source_frame.columns:
        if column not in key_columns:
            return column
    raise DerivedValidationError(
        "source frame does not contain a research value column",
        field="columns",
        value=str(source_frame.columns),
        reason="no non-key column found to serve as research value",
    )


def _manifest_hash(metadata: Mapping[str, object]) -> str:
    payload = orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def _build_dataset_report(
    *,
    dataset_frame: pl.DataFrame,
    derived_ids: tuple[str, ...],
    spine_row_count: int,
    snapshot_contract: _DatasetSnapshotContract,
) -> dict[str, object]:
    null_counts = _collect_null_counts(
        dataset_frame=dataset_frame,
        derived_ids=derived_ids,
    )
    return {
        "row_count": dataset_frame.height,
        "spine_row_count": spine_row_count,
        "null_counts": null_counts,
        "resolved_versions": snapshot_contract.resolved_versions,
        "known_at_policy": snapshot_contract.known_at_policy.value,
        "effective_cutoff": snapshot_contract.effective_cutoff,
        "source_snapshot_ids": list(snapshot_contract.source_snapshot_ids),
        "builder_version": snapshot_contract.builder_version,
    }


def _collect_null_counts(
    *,
    dataset_frame: pl.DataFrame,
    derived_ids: tuple[str, ...],
) -> dict[str, int]:
    if not derived_ids:
        return {}
    summary_frame = dataset_frame.select(
        [
            pl.col(derived_id).is_null().sum().alias(derived_id)
            for derived_id in derived_ids
        ]
    )
    summary_row = summary_frame.row(0, named=True)
    return {derived_id: int(summary_row[derived_id]) for derived_id in derived_ids}


def _coerce_date(value: str) -> date:
    return date.fromisoformat(value[:10])
