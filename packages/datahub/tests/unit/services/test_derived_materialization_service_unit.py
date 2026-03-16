"""Tests for the Phase 3 derived materialization service."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import orjson
import polars as pl
from ditto_core.engine.materialization import DerivedMaterializationRequest
from ditto_core.engine.materialization.models import (
    DerivedRunMode,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_core.engine.publication_safety import CompatibilityManifest
from ditto_core.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_datahub.models.derived import (
    DerivedCheckpointRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_datahub.services import PublicationSafetyRecordService
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_datahub.services.publication_safety_record_service import (
    PublicationSafetyRuntimeStores,
)
from ditto_datahub.stores.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_datahub.stores.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    MinimalDQReader,
    MinimalDQWriter,
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_datahub.stores.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
from ditto_port.services.derived import (
    DerivedMaterializationService,
    InMemoryDerivedInputProvider,
    RuntimeDerivedInputProvider,
    SQLiteCompileCacheService,
)


def _spec(profile: MaterializationProfile) -> DerivedSpec:
    role = (
        DerivedRole.FACTOR
        if profile != MaterializationProfile.DERIVE
        else DerivedRole.FEATURE
    )
    return DerivedSpec(
        id=f"{profile.name.lower()}.alpha_simple",
        version=3,
        role=role,
        materialization_profile=profile,
        expression="ts_delta(close, 1)",
    )


def _input_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 10),
                date(2026, 3, 11),
            ],
            "close": [10.0, 11.0, 20.0, 18.0],
        }
    )


def _write_market_truth_layers(data_root: Path) -> None:
    market_root = data_root / "market" / "stock"
    (market_root / "bars").mkdir(parents=True, exist_ok=True)
    (market_root / "adj").mkdir(parents=True, exist_ok=True)
    (market_root / "status").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "close": [10.0, 11.0],
            "volume": [100.0, 110.0],
        }
    ).write_parquet(market_root / "bars" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "adj_factor": [1.0, 1.1],
        }
    ).write_parquet(market_root / "adj" / "2026.parquet")
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "is_suspended": [False, True],
            "suspend_timing": [None, None],
            "is_st": [False, False],
            "st_type": [None, None],
            "list_status": ["L", "L"],
            "source": ["test", "test"],
            "source_ticker": ["000001.SZ", "000001.SZ"],
        }
    ).write_parquet(market_root / "status" / "2026.parquet")


def _write_upstream_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    availability_offset_days: int,
) -> None:
    version_root = (
        data_root / "derived" / "artifacts" / "series" / derived_id / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "value": [1.0, 2.0],
            "availability_time": [
                date(2026, 3, 10) + timedelta(days=availability_offset_days),
                date(2026, 3, 11) + timedelta(days=availability_offset_days),
            ],
        }
    ).write_parquet(version_root / "2026.parquet")


def _catalog_service(sqlite_client, artifact_root: Path) -> DerivedCatalogService:
    del artifact_root
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_spec(
    catalog_service: DerivedCatalogService,
    spec: DerivedSpec,
    *,
    status: str = DerivedVersionStatus.PUBLISHED,
    is_online: bool = True,
    is_primary: bool = True,
) -> None:
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=spec.id,
            version=spec.version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{spec.id}:v{spec.version}",
            spec_json=asdict(spec),
            created_at="2026-03-13T10:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=spec.id,
            version=spec.version,
            status=status,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-13T10:00:00+08:00",
            updated_at=None,
        )
    )


def _publication_record_service(data_root: Path) -> PublicationSafetyRecordService:
    return PublicationSafetyRecordService(
        PublicationSafetyRuntimeStores(
            manifest_reader=ManifestReader(base_path=data_root),
            manifest_writer=ManifestWriter(base_path=data_root),
            minimal_dq_reader=MinimalDQReader(base_path=data_root),
            minimal_dq_writer=MinimalDQWriter(base_path=data_root),
            shadow_report_reader=ShadowReportReader(base_path=data_root),
            shadow_report_writer=ShadowReportWriter(base_path=data_root),
            certification_reader=CertificationReader(base_path=data_root),
            certification_writer=CertificationWriter(base_path=data_root),
        )
    )


def _shadow_slot_service(sqlite_client) -> DerivedShadowSlotService:
    return DerivedShadowSlotService(
        slot_reader=SQLiteDerivedShadowSlotReader(sqlite_client),
        slot_writer=SQLiteDerivedShadowSlotWriter(sqlite_client),
    )


class TestDerivedMaterializationService:
    """Tests for unified derived materialization."""

    def test_series_materialization_writes_artifact_and_runtime_metadata(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable profiles should write artifacts, checkpoint, and state."""
        spec = _spec(MaterializationProfile.SERIES)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        assert result.rows_written == 4
        assert result.partitions_written == ("2026",)
        state = catalog_service.get_state(spec.id)
        assert state is not None
        assert state.latest_run_status == "SUCCESS"
        partitions = catalog_service.list_partitions(spec.id, 3, result.run_id)
        assert len(partitions) == 1
        artifact_path = tmp_path / partitions[0].partition_path
        assert artifact_path.exists()
        metadata_path = (
            artifact_path.parent / "_runs" / result.run_id / "artifact_metadata.json"
        )
        assert metadata_path.exists()
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["compile_identity"]["cache_key"]

    def test_derive_materialization_is_ephemeral_only(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """DERIVE profile should keep runtime records without durable artifact/state."""
        spec = _spec(MaterializationProfile.DERIVE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        assert result.partitions_written == ()
        assert catalog_service.get_state(spec.id) is None
        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == ()
        ephemeral_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "derive"
            / spec.id
            / "v3"
            / "_ephemeral"
        )
        assert ephemeral_root.exists()

    def test_checkpoint_rows_are_persisted(self, sqlite_client, tmp_path: Path) -> None:
        """Checkpoint rows should be visible after a durable run."""
        spec = _spec(MaterializationProfile.OFFLINE)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.SCHEDULED,
                source_snapshot_id="market:20260311-001",
            )
        )

        checkpoints = catalog_service.list_checkpoints(spec.id, 3)
        assert checkpoints == (
            DerivedCheckpointRecord(
                derived_id=spec.id,
                version=3,
                partition_key="2026",
                status="done",
                rows_written=4,
                checksum=checkpoints[0].checksum,
                error_message=None,
                started_at=checkpoints[0].started_at,
                completed_at=checkpoints[0].completed_at,
            ),
        )
        assert result.profile == MaterializationProfile.OFFLINE

    def test_runtime_input_provider_reads_market_truth_and_persists_refs(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Runtime input provider should read truth-layer parquet and persist refs."""
        spec = DerivedSpec(
            id="factor.market_truth_gate",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression=(
                "if_else("
                "market.is_suspended, "
                "market.close, "
                "market.close * market.adj_factor"
                ")"
            ),
        )
        _write_market_truth_layers(tmp_path)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=RuntimeDerivedInputProvider(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
                data_root=tmp_path,
            ),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=3,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        stock_daily_edges = catalog_service.list_dependencies_by_ref(
            "market.stock_daily"
        )
        adj_factor_edges = catalog_service.list_dependencies_by_ref("market.adj_factor")
        stock_status_edges = catalog_service.list_dependencies_by_ref(
            "market.stock_status"
        )

        assert {(edge.derived_id, edge.version) for edge in stock_daily_edges} == {
            (spec.id, spec.version)
        }
        assert {(edge.derived_id, edge.version) for edge in adj_factor_edges} == {
            (spec.id, spec.version)
        }
        assert {(edge.derived_id, edge.version) for edge in stock_status_edges} == {
            (spec.id, spec.version)
        }

        partition = catalog_service.list_partitions(
            spec.id,
            spec.version,
            result.run_id,
        )[0]
        artifact = pl.read_parquet(tmp_path / partition.partition_path)
        assert "availability_time" in artifact.columns
        assert (
            artifact.select(pl.col("availability_time") == pl.col("trade_date"))
            .to_series()
            .all()
        )

    def test_runtime_input_provider_preserves_upstream_availability_time(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Derived upstream inputs should keep upstream availability time."""
        upstream = DerivedSpec(
            id="factor.alpha_upstream",
            version=4,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close",
        )
        downstream = DerivedSpec(
            id="factor.alpha_downstream",
            version=5,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="@factor.alpha_upstream + 1",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, upstream)
        _seed_spec(catalog_service, downstream)
        catalog_service.save_state(
            DerivedStateRecord(
                derived_id=upstream.id,
                active_version=upstream.version,
                coverage_start="2026-03-10",
                coverage_end="2026-03-11",
                watermark="2026-03-11",
                latest_run_id="drv-upstream",
                latest_run_status="SUCCESS",
                total_rows=2,
                updated_at="2026-03-13T10:00:00+08:00",
            )
        )
        _write_upstream_artifact(
            tmp_path,
            derived_id=upstream.id,
            version=upstream.version,
            availability_offset_days=1,
        )
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=RuntimeDerivedInputProvider(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
                data_root=tmp_path,
            ),
            artifact_root=tmp_path,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=downstream.id,
                version=downstream.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id=None,
            )
        )

        upstream_edges = catalog_service.list_dependencies_by_ref(upstream.id)
        assert {(edge.derived_id, edge.version) for edge in upstream_edges} == {
            (downstream.id, downstream.version)
        }

        partition = catalog_service.list_partitions(
            downstream.id,
            downstream.version,
            result.run_id,
        )[0]
        artifact = pl.read_parquet(tmp_path / partition.partition_path)
        assert artifact["availability_time"].to_list() == [
            date(2026, 3, 11),
            date(2026, 3, 12),
        ]

    def test_materialization_persists_manifest_and_shadow_slot(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable materialization should auto-save manifest and shadow slot."""
        baseline = DerivedSpec(
            id="factor.alpha_publish",
            version=2,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close",
        )
        candidate = DerivedSpec(
            id="factor.alpha_publish",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_delta(close, 1)",
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, baseline, status=DerivedVersionStatus.PUBLISHED)
        _seed_spec(
            catalog_service,
            candidate,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({candidate.id: _input_frame()}),
            artifact_root=tmp_path,
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=candidate.id,
                version=candidate.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        manifest_record = publication_record_service.get_manifest(
            candidate.id,
            candidate.version,
        )
        assert manifest_record is not None
        manifest = CompatibilityManifest(**manifest_record.payload)
        assert manifest.is_complete() is True

        partition = catalog_service.list_partitions(
            candidate.id,
            candidate.version,
            result.run_id,
        )[0]
        metadata_path = (
            (tmp_path / partition.partition_path).parent
            / "_runs"
            / result.run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["publication"]["manifest_hash"] == manifest_record.manifest_hash
        assert (
            payload["publication"]["compatibility_manifest"] == manifest_record.payload
        )

        shadow_slot = shadow_slot_service.get_active_slot(candidate.id)
        assert shadow_slot is not None
        assert shadow_slot.candidate_version == candidate.version
        assert shadow_slot.baseline_version == baseline.version

    def test_durable_materialization_persists_minimal_dq_summary(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Durable materialization should persist a passing minimal DQ summary."""
        spec = _spec(MaterializationProfile.SERIES)
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        publication_record_service = _publication_record_service(tmp_path)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: _input_frame()}),
            artifact_root=tmp_path,
            publication_record_service=publication_record_service,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=spec.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        summary_record = publication_record_service.get_latest_minimal_dq_summary(
            spec.id,
            spec.version,
        )

        assert summary_record is not None
        assert summary_record.run_id == result.run_id
        assert summary_record.passed is True
        assert summary_record.error_count == 0
        assert summary_record.payload["row_count"] == 4
        assert summary_record.payload["null_value_count"] == 2
        assert summary_record.payload["nan_value_count"] == 0
        assert summary_record.payload["computable_value_count"] == 2
        assert summary_record.payload["failed_checks"] == []

        partition = catalog_service.list_partitions(
            spec.id,
            spec.version,
            result.run_id,
        )[0]
        metadata_path = (
            (tmp_path / partition.partition_path).parent
            / "_runs"
            / result.run_id
            / "artifact_metadata.json"
        )
        payload = orjson.loads(metadata_path.read_bytes())
        assert payload["publication"]["minimal_dq_summary"]["passed"] is True
        assert payload["publication"]["minimal_dq_summary"]["error_count"] == 0

    def test_empty_or_invalid_output_is_marked_as_failed_minimal_dq(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Materialization should persist a failing minimal DQ summary."""
        spec = DerivedSpec(
            id="series.alpha_invalid",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="close",
        )
        invalid_frame = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "close": [10.0, float("nan"), 20.0, 18.0],
            }
        )
        catalog_service = _catalog_service(sqlite_client, tmp_path)
        _seed_spec(catalog_service, spec)
        publication_record_service = _publication_record_service(tmp_path)
        service = DerivedMaterializationService(
            catalog_service=catalog_service,
            compile_cache_service=SQLiteCompileCacheService(sqlite_client),
            input_provider=InMemoryDerivedInputProvider({spec.id: invalid_frame}),
            artifact_root=tmp_path,
            publication_record_service=publication_record_service,
        )

        result = service.materialize(
            DerivedMaterializationRequest(
                derived_id=spec.id,
                version=spec.version,
                mode=DerivedRunMode.FULL,
                request_start="2026-03-10",
                request_end="2026-03-11",
                trigger=DerivedRunTrigger.MANUAL,
                source_snapshot_id="market:20260311-001",
            )
        )

        summary_record = publication_record_service.get_latest_minimal_dq_summary(
            spec.id,
            spec.version,
        )

        assert result.rows_written == 4
        assert summary_record is not None
        assert summary_record.run_id == result.run_id
        assert summary_record.passed is False
        assert summary_record.error_count == 1
        assert summary_record.payload["nan_value_count"] == 1
        assert summary_record.payload["computable_value_count"] == 3
        assert summary_record.payload["failed_checks"] == ["value_has_no_nan"]
