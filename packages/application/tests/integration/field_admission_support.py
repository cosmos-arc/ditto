"""Field admission against real immutable SQLite evidence ledgers."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ditto_application.processes.selection.admission import selection_field_payload
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.field_evidence import CertifiedField, consumer_input_digest
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool

_DAY = date(2026, 9, 18)
_VISIBLE = datetime(2026, 9, 18, 9, tzinfo=UTC)


@contextmanager
def field_evidence(
    *,
    day=_DAY,
    visible=_VISIBLE,
    display="allowed",
    compute="allowed",
    effective_to=None,
):
    directory = TemporaryDirectory(prefix="ditto-field-admission-")
    pool = SQLitePool(Path(directory.name) / "evidence.sqlite")
    client = SQLiteClient(pool)
    snapshots = SQLiteProviderSnapshotStore(client)
    licenses = SQLiteDatasetLicenseStore(client)
    reports = SQLiteCertificationStore(client)
    license_record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="stock_daily",
            source="tushare",
            terms_version="test-reviewed-v1",
            effective_from=date(2026, 1, 1),
            effective_to=effective_to,
            local_cache="allowed",
            derivative_compute=compute,
            display=display,
            redistribution="prohibited",
            notes="isolated synthetic evidence",
            reviewed_by="human",
            reviewed_at=visible,
        )
    )
    licenses.append_license(license_record)
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start=day.isoformat(),
            request_end=day.isoformat(),
            schema_version="market.stock_daily.v1",
            checksum="abc",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="abc",
            response_metadata=(),
            license_record_id=license_record.record_id,
            row_count=1,
            payload_uri="evidence://retained/synthetic",
            payload_retained=True,
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        )
    )
    snapshots.append_snapshot(snapshot)
    lifecycle = SQLitePartitionLifecycleStore(client)
    lifecycle.plan_partition(
        PartitionCheckpoint(
            chunk_id="synthetic",
            dataset_id=snapshot.dataset_id,
            source=snapshot.source,
            request_start=snapshot.request_start,
            request_end=snapshot.request_end,
            status=PartitionLifecycleStatus.PLANNED,
            last_successful_stage=None,
            attempt=1,
            retry_budget=3,
            payload_id=None,
            catalog_asset_id=None,
            lineage_run_id=None,
            ingestion_log_id=None,
            error_code=None,
            updated_at=visible,
        )
    )
    for stage in (
        PartitionLifecycleStatus.FETCHED,
        PartitionLifecycleStatus.NORMALIZED,
        PartitionLifecycleStatus.PIT_PASSED,
        PartitionLifecycleStatus.DQ_PASSED,
        PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        PartitionLifecycleStatus.CATALOG_ATTESTED,
        PartitionLifecycleStatus.LINEAGE_RECORDED,
        PartitionLifecycleStatus.SUCCESS_RECORDED,
        PartitionLifecycleStatus.COMPLETE,
    ):
        lifecycle.advance_partition(
            "synthetic",
            stage,
            occurred_at=visible,
            evidence_id=(
                f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"
                if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                else snapshot.snapshot_id
            ),
        )
    field = CertifiedField(
        field="amount",
        snapshot_id=snapshot.snapshot_id,
        instrument_ids=(600000,),
        covered_from=day,
        covered_to=day,
        available_at=visible,
        publication_at=visible,
        time_precision="timestamp",
        observed_at=visible,
        evidence_uri="evidence://field/amount",
        consumer_bindings=(("instruments.average_turnover", "a" * 64),),
    )
    check = (EvidenceCheck("recorded", "evidence://synthetic", True),)
    report = DatasetCertificationReport.create(
        dataset_id="stock_daily",
        profile="selection-fields-v1",
        coverage=DatasetCoverage(
            dataset_id="stock_daily",
            schedule="trading_days",
            target_from=day,
            target_to=day,
            native_from=day,
            native_to=day,
            actual_from=day,
            actual_to=day,
            raw_from=day,
            complete_from=day,
            expected_partitions=1,
            actual_partitions=1,
            gaps=(),
            exceptions=(),
            collected_at=visible,
        ),
        evidence=CertificationEvidence(
            source_ids=("tushare",),
            schema_versions=(snapshot.schema_version,),
            snapshot_ids=(snapshot.snapshot_id,),
            dq_rule_version="test-v1",
            dq_results=check,
            pit_replay_results=check,
            fallback_history=("none",),
            override_history=(),
            freshness_results=check,
            recovery_results=check,
            license_record_ids=(license_record.record_id,),
            consumer_results=check,
            certified_fields=(field,),
        ),
        generated_at=visible,
    )
    reports.append_report(report)
    reports.approve_report(report.report_id, reviewer="human", reviewed_at=visible)
    request = FieldAdmissionRequest(
        fields=(
            FieldRequirement(
                "stock_daily",
                "amount",
                snapshot.snapshot_id,
                "instruments.average_turnover",
                "a" * 64,
            ),
        ),
        instrument_ids=(600000,),
        required_from=day,
        required_to=day,
        knowledge_cutoff=visible,
        publication_cutoff=visible,
        purpose="formal_research",
    )
    yield (
        FieldAdmissionQuery(
            snapshots, licenses, reports, lifecycle, now=lambda: _VISIBLE
        ),
        request,
        reports,
        report,
    )
    pool.close_all()
    directory.cleanup()


@contextmanager
def certified_selection(request):
    """Supply explicitly reviewed synthetic fields for transport regression tests."""
    with field_evidence(day=request.as_of.date(), visible=request.knowledge_cutoff) as (
        query,
        _,
        reports,
        old,
    ):
        consumer_fields = (
            "universe_snapshot_id",
            "membership_version",
            "market_context_feature_set_id",
            "instruments.instrument_id",
            "instruments.instrument_name",
            "instruments.industry_id",
            "instruments.average_turnover",
            "instruments.is_st",
            "instruments.is_suspended",
            "instruments.listing_days",
            "instruments.limit_state",
            "instruments.tracking_error",
            "industries.industry_id",
            "industries.industry_name",
            "industries.relative_strength_5d",
            "industries.relative_strength_20d",
            "industries.relative_strength_60d",
            "industries.advancing_count",
            "industries.declining_count",
            "industries.member_count",
            "industries.trend_score",
            "industries.fundamental_score",
            "industries.regime_alignment_score",
            *(
                f"instruments.factor_values.{item.name}"
                for item in request.selection_spec.factor_weights
            ),
        )
        snapshot_id = old.evidence.snapshot_ids[0]
        bound = replace(
            request,
            data_fields=tuple(
                FieldRequirement("stock_daily", "amount", snapshot_id, consumer)
                for consumer in consumer_fields
            ),
            data_from=old.coverage.target_from,
            data_to=old.coverage.target_to,
            rotation_source_snapshot_ids=(snapshot_id,),
            selection_source_snapshot_ids=(snapshot_id,),
        )
        field = replace(
            old.evidence.certified_fields[0],
            instrument_ids=tuple(
                int(item.instrument_id) for item in request.instruments
            ),
            available_at=request.knowledge_cutoff,
            publication_at=request.publication_cutoff,
            consumer_bindings=tuple(
                (name, consumer_input_digest(selection_field_payload(bound, name)))
                for name in consumer_fields
            ),
        )
        reports.revoke_report(
            old.report_id,
            revoked_by="human",
            revoked_at=_VISIBLE,
            reason="synthetic request scope",
        )
        report = DatasetCertificationReport.create(
            dataset_id=old.dataset_id,
            profile=old.profile,
            coverage=old.coverage,
            evidence=replace(old.evidence, certified_fields=(field,)),
            generated_at=_VISIBLE,
        )
        reports.append_report(report)
        reports.approve_report(report.report_id, reviewer="human", reviewed_at=_VISIBLE)
        yield query, bound
