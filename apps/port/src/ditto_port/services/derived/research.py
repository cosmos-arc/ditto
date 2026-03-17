"""Port-side research dataset snapshot facade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

import orjson
import polars as pl
from ditto_core.engine.research import (
    DatasetSnapshot,
    KnownAtPolicy,
    LateArrivalPolicy,
    ResearchDatasetSpec,
    SpineSnapshot,
    SpineSpec,
)
from ditto_core.engine.specs import CalendarId, GrainId
from ditto_datahub.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_datahub.services import DerivedArtifactReader, ResearchCatalogService
from ditto_datahub.services.derived import VersionResolutionStrategy
from ditto_datahub.services.metadata_service import MetadataService

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
        data_root: Path,
    ) -> None:
        self._metadata_service = metadata_service
        self._research_catalog_service = research_catalog_service
        self._artifact_reader = artifact_reader
        self._data_root = Path(data_root)

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
        spine_frame = pl.read_parquet(self._data_root / spine_snapshot.data_path)
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
            artifact_path = _resolve_artifact_path(
                data_root=self._data_root,
                derived_id=derived_id,
                version=resolved_version,
            )
            resolved_inputs.append(
                {
                    "derived_id": derived_id,
                    "version": resolved_version,
                    "artifact_path": artifact_path,
                }
            )
            source_snapshot_ids.update(
                _read_source_snapshot_ids(self._data_root / artifact_path)
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
        report_path = (
            _dataset_snapshot_root(self._data_root, snapshot) / _BUILD_REPORT_FILENAME
        )
        payload = orjson.loads(report_path.read_bytes())
        if not isinstance(payload, dict):
            raise ValueError(
                "invalid research build report payload for "
                + f"snapshot_id={snapshot.snapshot_id}"
            )
        return cast(dict[str, object], payload)

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

        created_at = _now_iso()
        snapshot_id = f"rsp-{uuid4().hex[:12]}"
        snapshot_path = (
            self._data_root
            / "derived"
            / "research"
            / "spines"
            / spine_spec.spine_id
            / "snapshots"
            / snapshot_id
            / "data.parquet"
        )
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        spine_frame.write_parquet(snapshot_path)
        relative_path = str(snapshot_path.relative_to(self._data_root))
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
        _write_metadata_file(
            snapshot_path.parent / "metadata.json",
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
        created_at = _now_iso()
        snapshot_id = f"rds-{uuid4().hex[:12]}"
        snapshot_path = (
            self._data_root
            / "derived"
            / "research"
            / "datasets"
            / dataset_id
            / "snapshots"
            / snapshot_id
            / "data.parquet"
        )
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_frame.write_parquet(snapshot_path)
        relative_path = str(snapshot_path.relative_to(self._data_root))
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
        _write_metadata_file(
            snapshot_path.parent / "metadata.json",
            {**metadata, "manifest_hash": manifest_hash},
        )
        _write_metadata_file(
            snapshot_path.parent / _BUILD_REPORT_FILENAME,
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
            raise KeyError(
                "research dataset spec not found for " + f"dataset_id={dataset_id}"
            )
        return record

    def _require_spine_spec_record(self, spine_id: str) -> ResearchSpineSpecRecord:
        record = self._research_catalog_service.get_spine_spec(spine_id)
        if record is None:
            raise KeyError(f"research spine spec not found for spine_id={spine_id}")
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
    raise KeyError("source frame does not contain a research value column")


def _manifest_hash(metadata: Mapping[str, object]) -> str:
    payload = orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def _write_metadata_file(path: Path, metadata: Mapping[str, object]) -> None:
    path.write_bytes(
        orjson.dumps(
            metadata,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
    )


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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _dataset_snapshot_root(data_root: Path, snapshot: DatasetSnapshot) -> Path:
    return (data_root / snapshot.data_path).parent


def _resolve_artifact_path(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
) -> str:
    artifact_root = data_root / "derived" / "artifacts"
    matches = sorted(artifact_root.glob(f"*/{derived_id}/v{version}"))
    if matches:
        return str(matches[0].relative_to(data_root))
    return f"derived/artifacts/unknown/{derived_id}/v{version}"


def _read_source_snapshot_ids(version_root: Path) -> tuple[str, ...]:
    runs_root = version_root / "_runs"
    if not runs_root.exists():
        return ()
    metadata_paths = tuple(runs_root.glob("*/artifact_metadata.json"))
    if not metadata_paths:
        return ()
    latest_metadata = max(metadata_paths, key=lambda path: path.stat().st_mtime_ns)
    payload = orjson.loads(latest_metadata.read_bytes())
    raw_snapshots = payload.get("input_snapshots", [])
    if not isinstance(raw_snapshots, list):
        return ()
    typed_raw_snapshots = cast(list[object], raw_snapshots)
    snapshot_ids: list[str] = []
    for raw_snapshot_id in typed_raw_snapshots:
        if isinstance(raw_snapshot_id, str) and raw_snapshot_id != "":
            snapshot_ids.append(raw_snapshot_id)
    return tuple(sorted(set(snapshot_ids)))


def _coerce_date(value: str) -> date:
    return date.fromisoformat(value[:10])
