"""Tests for derived publication orchestration facade."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_application.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_data.ingestion.publication_safety_record_service import (
    PublicationSafetyRecordService,
    PublicationSafetyRuntimeStores,
)
from ditto_data.models.derived import (
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_data.models.publication_safety import (
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
)
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
)
from ditto_data.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_data.storage.runtime.derived_sqlite import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)
from ditto_data.storage.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    MinimalDQReader,
    MinimalDQWriter,
    ShadowReportReader,
    ShadowReportWriter,
)
from ditto_data.storage.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_features.materialization.models import (
    DerivedRunMode,
    DerivedRunStatus,
    DerivedRunTrigger,
    DerivedVersionStatus,
)
from ditto_features.publication_safety import CertificationStage
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile
from ditto_platform.foundation import SQLitePool


@pytest.fixture
def sqlite_client(tmp_path: Path):
    """Provide a schema-initialized SQLite client for publication facade tests."""
    schema_path = (
        Path(__file__).resolve().parents[6]
        / "packages"
        / "data"
        / "src"
        / "ditto_data"
        / "scripts"
        / "schema.sql"
    )
    pool = SQLitePool(str(tmp_path / "test.sqlite"), schema_path=schema_path)
    pool.init_schema()
    yield SQLiteClient(pool)
    pool.close()


def _catalog_service(sqlite_client) -> DerivedCatalogService:
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
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


def _seed_version(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
    profile: MaterializationProfile = MaterializationProfile.SERIES,
    status: str,
    is_online: bool,
    is_primary: bool,
) -> None:
    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=profile,
        expression="market.close",
    )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-14T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status=status,
            engine_version="expr-v1",
            is_online=is_online,
            is_primary=is_primary,
            created_at="2026-03-14T12:00:00+08:00",
            updated_at=None,
        )
    )


def _save_success_run(
    catalog_service: DerivedCatalogService,
    *,
    derived_id: str,
    version: int,
) -> None:
    catalog_service.save_run(
        DerivedRunRecord(
            run_id=f"drv-{derived_id}-{version}",
            derived_id=derived_id,
            version=version,
            mode=DerivedRunMode.FULL.value,
            trigger=DerivedRunTrigger.MANUAL.value,
            request_start="2026-03-10",
            request_end="2026-03-11",
            compute_start="2026-03-10",
            compute_end="2026-03-11",
            source_snapshot_id=None,
            status=DerivedRunStatus.SUCCESS.value,
            rows_written=2,
            partitions_written=("2026",),
            error_message=None,
            created_at="2026-03-14T12:10:00+08:00",
            started_at="2026-03-14T12:10:00+08:00",
            finished_at="2026-03-14T12:11:00+08:00",
        )
    )


def _save_manifest(
    publication_record_service: PublicationSafetyRecordService,
    *,
    derived_id: str,
    version: int,
    manifest_hash: str,
    complete: bool = True,
) -> None:
    payload = {
        "engine_codegen_version": "codegen-v1",
        "analysis_version": "analysis-v1",
        "polars_version": "1.30.0",
        "expr_serialization_format": "expr-json-v1",
        "operator_fingerprint": f"operator-{version}",
        "global_compile_flags": {"grain": "1d"},
        "calendar_id": "cn_stock",
        "timezone": "Asia/Shanghai",
        "time_semantics_version": "time-v1",
        "python_version": "3.13.0",
        "platform": "linux",
        "builder_version": "unified-derived-v1",
        "manifest_hash": manifest_hash,
    }
    if not complete:
        payload["operator_fingerprint"] = None
    publication_record_service.save_manifest(
        CompatibilityManifestRecord(
            derived_id=derived_id,
            version=version,
            manifest_hash=manifest_hash,
            payload=payload,
            created_at="2026-03-14T12:00:00+08:00",
        )
    )


def _save_minimal_dq_summary(
    publication_record_service: PublicationSafetyRecordService,
    *,
    derived_id: str,
    version: int,
    run_id: str = "drv-001",
    passed: bool,
    failed_checks: tuple[str, ...] = (),
    computable_value_count: int = 2,
) -> None:
    publication_record_service.save_minimal_dq_summary(
        DerivedMinimalDQSummaryRecord(
            derived_id=derived_id,
            version=version,
            run_id=run_id,
            passed=passed,
            error_count=len(failed_checks),
            payload={
                "row_count": 2,
                "primary_key_columns": ["instrument_id", "trade_date"],
                "missing_primary_key_columns": [],
                "null_primary_key_count": 0,
                "duplicate_key_count": 0,
                "null_value_count": 0,
                "nan_value_count": 0,
                "computable_value_count": computable_value_count,
                "failed_checks": list(failed_checks),
            },
            created_at="2026-03-14T12:05:00+08:00",
        )
    )


def _write_artifact(
    data_root: Path,
    *,
    derived_id: str,
    version: int,
    values: list[float],
    profile: MaterializationProfile = MaterializationProfile.SERIES,
) -> None:
    version_root = (
        data_root
        / "derived"
        / "artifacts"
        / profile.value.lower()
        / derived_id
        / f"v{version}"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
            "value": values,
            "availability_time": [date(2026, 3, 10), date(2026, 3, 11)],
        }
    ).write_parquet(version_root / "2026.parquet")


class TestDerivedPublicationFacade:
    """Tests for Phase 5 publication orchestration."""

    def test_shadow_ready_requires_manifest_and_minimal_dq(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Shadow ready should block when manifest or minimal DQ is not ready."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=_shadow_slot_service(sqlite_client),
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            manifest_hash="manifest-v3",
            complete=False,
        )

        certification = facade.certify(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.SHADOW_READY,
        )

        check_map = {check.name: check for check in certification.checks}
        assert certification.is_passed() is False
        assert check_map["minimal_dq_passed"].passed is False
        assert check_map["manifest_complete"].passed is False
        assert "shadow_diff_passed" not in check_map

    def test_publish_ready_requires_shadow_diff_and_profile_rules(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Publish ready should require shadow diff plus factor/SERIES checks."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=2,
            manifest_hash="manifest-v2",
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            manifest_hash="manifest-v3",
        )
        _save_minimal_dq_summary(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            passed=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=2,
            values=[10.0, 11.0],
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=3,
            values=[10.0, 11.0],
        )

        facade.shadow_publish(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )
        blocked = facade.certify(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        blocked_checks = {check.name: check for check in blocked.checks}
        assert blocked.is_passed() is False
        assert blocked_checks["shadow_ready_passed"].passed is True
        assert blocked_checks["shadow_diff_passed"].passed is False
        assert blocked_checks["factor_distribution_stability"].passed is False
        assert blocked_checks["series_shadow_parity"].passed is False

        facade.run_shadow_compare(
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
        )
        ready = facade.certify(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        ready_checks = {check.name: check for check in ready.checks}
        assert ready.is_passed() is True
        assert ready_checks["shadow_diff_passed"].passed is True
        assert ready_checks["factor_distribution_stability"].passed is True
        assert ready_checks["series_shadow_parity"].passed is True

    def test_offline_profile_uses_sample_audit_instead_of_shadow_diff(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """OFFLINE publish ready should use sample audit semantics."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_offline",
            version=2,
            profile=MaterializationProfile.OFFLINE,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_offline",
            version=3,
            profile=MaterializationProfile.OFFLINE,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_offline",
            version=2,
            manifest_hash="manifest-v2",
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_offline",
            version=3,
            manifest_hash="manifest-v3",
        )
        _save_minimal_dq_summary(
            publication_record_service,
            derived_id="factor.alpha_offline",
            version=3,
            passed=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_offline",
            version=2,
            values=[10.0, 11.0],
            profile=MaterializationProfile.OFFLINE,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_offline",
            version=3,
            values=[10.0, 11.0],
            profile=MaterializationProfile.OFFLINE,
        )

        facade.shadow_publish(
            derived_id="factor.alpha_offline",
            candidate_version=3,
        )
        facade.run_shadow_compare(
            derived_id="factor.alpha_offline",
            start="2026-03-10",
            end="2026-03-11",
        )
        certification = facade.certify(
            derived_id="factor.alpha_offline",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        check_names = {check.name for check in certification.checks}
        assert certification.is_passed() is True
        assert "sample_audit_passed" in check_names
        assert "shadow_diff_passed" not in check_names

    def test_factor_series_pack_includes_distribution_and_parity_checks(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Factor SERIES publish pack should include distribution and parity checks."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_pack",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_pack",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_pack",
            version=2,
            manifest_hash="manifest-v2",
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_pack",
            version=3,
            manifest_hash="manifest-v3",
        )
        _save_minimal_dq_summary(
            publication_record_service,
            derived_id="factor.alpha_pack",
            version=3,
            passed=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_pack",
            version=2,
            values=[10.0, 11.0],
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_pack",
            version=3,
            values=[10.0, 11.0],
        )

        facade.shadow_publish(
            derived_id="factor.alpha_pack",
            candidate_version=3,
        )
        facade.run_shadow_compare(
            derived_id="factor.alpha_pack",
            start="2026-03-10",
            end="2026-03-11",
        )
        certification = facade.certify(
            derived_id="factor.alpha_pack",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        assert certification.pack.check_names == (
            "minimal_dq_passed",
            "manifest_complete",
            "shadow_ready_passed",
            "shadow_diff_passed",
            "factor_distribution_stability",
            "series_shadow_parity",
        )

    def test_shadow_compare_persists_report_and_publish_ready_certification(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Facade should compare artifacts and certify a clean candidate."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=2,
            manifest_hash="manifest-v2",
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            manifest_hash="manifest-v3",
        )
        _save_minimal_dq_summary(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            passed=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=2,
            values=[10.0, 11.0],
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=3,
            values=[10.0, 11.0],
        )

        slot = facade.shadow_publish(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )
        report = facade.run_shadow_compare(
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
        )
        certification = facade.certify(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        assert slot.baseline_version == 2
        assert report.error_count == 0
        assert report.value_diff_rate == 0.0
        stored_report = publication_record_service.get_latest_shadow_report(
            "factor.alpha_publish",
            3,
            2,
        )
        assert stored_report is not None
        assert stored_report.report_id == report.report_id
        assert certification.is_passed() is True
        stored_certification = (
            publication_record_service.get_latest_certification_report(
                "factor.alpha_publish",
                3,
                CertificationStage.PUBLISH_READY.value,
            )
        )
        assert stored_certification is not None
        assert stored_certification.payload["passed"] is True

    def test_promote_switches_primary_pointer_and_disables_shadow_slot(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Promote should atomically switch the primary pointer."""
        catalog_service = _catalog_service(sqlite_client)
        publication_record_service = _publication_record_service(tmp_path)
        shadow_slot_service = _shadow_slot_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=publication_record_service,
            shadow_slot_service=shadow_slot_service,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=False,
            is_primary=False,
        )
        _save_success_run(
            catalog_service,
            derived_id="factor.alpha_publish",
            version=3,
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=2,
            manifest_hash="manifest-v2",
        )
        _save_manifest(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            manifest_hash="manifest-v3",
        )
        _save_minimal_dq_summary(
            publication_record_service,
            derived_id="factor.alpha_publish",
            version=3,
            passed=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=2,
            values=[10.0, 11.0],
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_publish",
            version=3,
            values=[10.0, 11.0],
        )

        facade.shadow_publish(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )
        facade.run_shadow_compare(
            derived_id="factor.alpha_publish",
            start="2026-03-10",
            end="2026-03-11",
        )
        facade.certify(
            derived_id="factor.alpha_publish",
            version=3,
            stage=CertificationStage.PUBLISH_READY,
        )

        promoted = facade.promote(
            derived_id="factor.alpha_publish",
            candidate_version=3,
        )

        assert promoted.version == 3
        assert promoted.status == DerivedVersionStatus.PUBLISHED
        current_primary = catalog_service.get_version("factor.alpha_publish", 3)
        previous_primary = catalog_service.get_version("factor.alpha_publish", 2)
        assert current_primary is not None
        assert previous_primary is not None
        assert current_primary.is_primary is True
        assert current_primary.is_online is True
        assert previous_primary.is_primary is False
        assert previous_primary.status == DerivedVersionStatus.PUBLISHED
        assert shadow_slot_service.get_active_slot("factor.alpha_publish") is None

    def test_rollback_reuses_existing_primary_pointer_model(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Rollback should move the primary pointer without changing status."""
        catalog_service = _catalog_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=_publication_record_service(tmp_path),
            shadow_slot_service=_shadow_slot_service(sqlite_client),
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_rollback",
            version=1,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=False,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_rollback",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )

        rolled_back = facade.rollback(
            derived_id="factor.alpha_rollback",
            target_version=1,
        )

        current_primary = catalog_service.get_version("factor.alpha_rollback", 1)
        previous_primary = catalog_service.get_version("factor.alpha_rollback", 2)
        assert rolled_back.version == 1
        assert rolled_back.status == DerivedVersionStatus.PUBLISHED
        assert rolled_back.is_primary is True
        assert current_primary is not None
        assert previous_primary is not None
        assert current_primary.is_primary is True
        assert current_primary.status == DerivedVersionStatus.PUBLISHED
        assert previous_primary.is_primary is False
        assert previous_primary.status == DerivedVersionStatus.PUBLISHED

    def test_deprecate_does_not_delete_candidate_artifacts(
        self,
        sqlite_client,
        tmp_path: Path,
    ) -> None:
        """Deprecate should mark a non-primary published version offline."""
        catalog_service = _catalog_service(sqlite_client)
        facade = DerivedPublicationFacade(
            catalog_service=catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=catalog_service,
                artifact_root=tmp_path,
            ),
            publication_record_service=_publication_record_service(tmp_path),
            shadow_slot_service=_shadow_slot_service(sqlite_client),
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_deprecate",
            version=2,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=False,
        )
        _seed_version(
            catalog_service,
            derived_id="factor.alpha_deprecate",
            version=3,
            status=DerivedVersionStatus.PUBLISHED,
            is_online=True,
            is_primary=True,
        )
        _write_artifact(
            tmp_path,
            derived_id="factor.alpha_deprecate",
            version=2,
            values=[10.0, 11.0],
        )
        artifact_path = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "factor.alpha_deprecate"
            / "v2"
            / "2026.parquet"
        )

        deprecated = facade.deprecate(
            derived_id="factor.alpha_deprecate",
            version=2,
        )

        current_version = catalog_service.get_version("factor.alpha_deprecate", 2)
        primary_version = catalog_service.get_version("factor.alpha_deprecate", 3)
        assert deprecated.status == DerivedVersionStatus.DEPRECATED
        assert deprecated.is_online is False
        assert deprecated.is_primary is False
        assert current_version is not None
        assert primary_version is not None
        assert current_version.status == DerivedVersionStatus.DEPRECATED
        assert current_version.is_online is False
        assert primary_version.is_primary is True
        assert artifact_path.exists() is True
