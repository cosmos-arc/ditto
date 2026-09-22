"""Explicit research dataset build orchestration."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, time
from typing import NamedTuple
from zoneinfo import ZoneInfo

import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.records import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_analysis.research.specs import (
    DatasetSnapshot,
    KnownAtPolicy,
    SpineSnapshot,
    SpineSpec,
)
from ditto_data.services.metadata_service import MetadataService
from ditto_features.errors import DerivedNotFoundError
from ditto_features.services import (
    DerivedArtifactReader,
    VersionResolutionStrategy,
)
from ditto_kernel.exceptions import DittoError

from ditto_application.config import now_iso
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.research_dataset_helpers import (
    _attach_known_at,
    _build_dataset_report,
    _DatasetSnapshotContract,
    _hydrate_dataset_spec,
    _hydrate_spine_spec,
    _normalize_trade_dates,
    _pit_join,
)
from ditto_application.queries.historical_universe import (
    HistoricalUniverseQuery,
    HistoricalUniverseSources,
)

__all__ = ["ResearchDatasetBuildProcess"]

_BUILD_REPORT_FILENAME = "build_report.json"


class _ResolvedDerivedInputs(NamedTuple):
    """derived inputs 解析结果 — 提供精确类型以通过 pyright strict 检查."""

    frame: pl.DataFrame
    versions: dict[str, int]
    inputs: tuple[dict[str, str | int | list[str]], ...]
    source_ids: tuple[str, ...]


@contextmanager
def _build_stage(stage: str, identity: str) -> Generator[None]:
    """Keep domain errors intact and identify the failed recovery boundary."""
    try:
        yield
    except DittoError as error:
        error.details.update(stage=stage, identity=identity)
        raise
    except OSError as error:
        raise AppProcessError(
            f"Research dataset {stage} failed: {error}",
            stage=stage,
            identity=identity,
            recoverable=True,
        ) from error


class ResearchDatasetBuildProcess:
    """Build immutable research spine and dataset snapshots."""

    def __init__(
        self,
        *,
        metadata_service: MetadataService,
        research_catalog_service: ResearchCatalogService,
        artifact_reader: DerivedArtifactReader,
        research_artifact_service: ResearchArtifactService,
        historical_universe: HistoricalUniverseQuery,
    ) -> None:
        self._metadata_service = metadata_service
        self._research_catalog_service = research_catalog_service
        self._artifact_reader = artifact_reader
        self._artifact_service = research_artifact_service
        self._historical_universe = historical_universe

    def build(
        self,
        *,
        dataset_id: str,
        start: str,
        end: str,
        version_overrides: dict[str, int] | None = None,
        explicit_cutoff: str | None = None,
        universe_sources: HistoricalUniverseSources | None = None,
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
        known_at_policy = (
            KnownAtPolicy.EXPLICIT_CUTOFF
            if explicit_cutoff is not None
            else dataset_spec.known_at_policy
        )
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise AppProcessError("research dataset start must not be after end")
        if known_at_policy == KnownAtPolicy.EXPLICIT_CUTOFF:
            if explicit_cutoff is None:
                raise AppProcessError("explicit_cutoff is required")
            date.fromisoformat(explicit_cutoff[:10])
        if universe_sources is None:
            raise AppProcessError(
                "HISTORY_SNAPSHOT_MISSING: research requires pinned universe sources"
            )
        if universe_sources.universe_id != spine_spec.universe_id:
            raise AppProcessError("HISTORY_SCOPE_CONFLICT")
        spine_snapshot = self._build_spine_snapshot(
            spine_spec=spine_spec,
            start=start,
            end=end,
            sources=universe_sources,
            explicit_cutoff=explicit_cutoff,
        )
        spine_frame = self._artifact_service.read_parquet(spine_snapshot.data_path)
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
            resolved_inputs=(
                *resolved.inputs,
                {
                    "input_kind": "universe",
                    "universe_id": universe_sources.universe_id,
                    "source_snapshot_ids": list(universe_sources.snapshot_ids),
                },
            ),
            source_snapshot_ids=tuple(
                sorted(set(resolved.source_ids) | set(universe_sources.snapshot_ids))
            ),
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
        resolved_inputs: list[dict[str, str | int | list[str]]] = []
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
            input_sources = self._artifact_service.read_source_snapshot_ids(
                artifact_path
            )
            resolved_inputs.append(
                {
                    "derived_id": derived_id,
                    "version": resolved_version,
                    "artifact_path": artifact_path,
                    "source_snapshot_ids": list(input_sources),
                }
            )
            source_snapshot_ids.update(input_sources)
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

    def _build_spine_snapshot(
        self,
        *,
        spine_spec: SpineSpec,
        start: str,
        end: str,
        sources: HistoricalUniverseSources,
        explicit_cutoff: str | None,
    ) -> SpineSnapshot:
        calendar_frame = self._metadata_service.calendar.list_calendar_range(
            start=start,
            end=end,
            only_open=True,
        )
        trade_dates = _normalize_trade_dates(calendar_frame)
        # One immutable source set per build: pinned payloads are read once and
        # each day resolves only the members its own cutoff had observed.
        pinned_sources = self._historical_universe.pin(sources)
        daily_frames: list[pl.DataFrame] = []
        daily_evidence: list[dict[str, object]] = []
        for day in trade_dates["trade_date"].to_list():
            cutoff = (
                datetime.fromisoformat(explicit_cutoff)
                if explicit_cutoff is not None
                else datetime.combine(day, time.min, ZoneInfo("Asia/Shanghai"))
            )
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            result = pinned_sources.resolve(
                as_of=day,
                knowledge_cutoff=cutoff,
                publication_cutoff=cutoff,
            )
            daily_frames.append(
                result.frame.with_columns(
                    pl.lit(day).alias("trade_date"),
                    pl.col("exclusion_reasons")
                    .list.join("|")
                    .alias("universe_exclusion_reasons"),
                ).select(
                    "instrument_id",
                    "trade_date",
                    "investable",
                    "universe_exclusion_reasons",
                )
            )
            daily_evidence.append(result.evidence)
        if not daily_frames:
            raise AppProcessError("HISTORY_CALENDAR_EMPTY")
        spine_frame = pl.concat(daily_frames).sort(["instrument_id", "trade_date"])

        metadata: dict[str, object] = {
            "spine_id": spine_spec.spine_id,
            "universe_id": spine_spec.universe_id,
            "universe_history": daily_evidence,
            "calendar": spine_spec.calendar,
            "grain": spine_spec.grain,
            "entity_key": spine_spec.entity_key,
            "version": spine_spec.version,
            "start": start,
            "end": end,
            "row_count": spine_frame.height,
        }
        with _build_stage("spine_publication", spine_spec.spine_id):
            published = self._artifact_service.publish_research_snapshot(
                namespace=f"derived/research/spines/{spine_spec.spine_id}",
                prefix="rsp",
                identity_field="spine_snapshot_id",
                frame=spine_frame,
                metadata=metadata,
                created_at=now_iso(),
            )
        snapshot_id, relative_path, manifest_hash, created_at = published
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
        with _build_stage("spine_catalog_commit", snapshot_id):
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
        metadata: dict[str, object] = {
            "dataset_id": dataset_id,
            "dataset_spec_version": dataset_spec_version,
            "spine_spec_version": spine_spec_version,
            "spine_snapshot_id": spine_snapshot.spine_snapshot_id,
            "start": spine_snapshot.start,
            "end": spine_snapshot.end,
            "row_count": dataset_frame.height,
            "known_at_policy": snapshot_contract.known_at_policy.value,
            "effective_cutoff": snapshot_contract.effective_cutoff,
            "resolved_versions": snapshot_contract.resolved_versions,
            "resolved_inputs": list(snapshot_contract.resolved_inputs),
            "source_snapshot_ids": list(snapshot_contract.source_snapshot_ids),
            "builder_version": snapshot_contract.builder_version,
        }
        with _build_stage("dataset_publication", dataset_id):
            published = self._artifact_service.publish_research_snapshot(
                namespace=f"derived/research/datasets/{dataset_id}",
                prefix="rds",
                identity_field="snapshot_id",
                frame=dataset_frame,
                metadata=metadata,
                created_at=now_iso(),
                extra_json_files={_BUILD_REPORT_FILENAME: build_report},
            )
        snapshot_id, relative_path, manifest_hash, created_at = published
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
        with _build_stage("dataset_catalog_commit", snapshot_id):
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
