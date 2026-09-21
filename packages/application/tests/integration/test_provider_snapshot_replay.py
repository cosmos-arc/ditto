"""Real ingestion, immutable reads, certification, failure recovery and revocation."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

import polars as pl
import pytest
from ditto_application.commands.data_product_certification_builder import (
    AddressedCertificationEvidence,
    CertificationBuildRequest,
    DataProductCertificationBuilder,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.ingestion.post_ingest import process_fetched_data
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.field_evidence import CertifiedField
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
from ditto_platform.foundation import SQLiteClient, SQLitePool
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _bars,
    _pipeline,
)


def _certify(runtime, reports, snapshot, tmp_path, visible):
    artifact = tmp_path / "consumer.json"
    artifact.write_bytes(b'{"recorded":"synthetic consumer and recovery"}')
    proof = AddressedCertificationEvidence(
        "synthetic",
        "evidence://synthetic",
        artifact,
        sha256(artifact.read_bytes()).hexdigest(),
    )
    builder = DataProductCertificationBuilder(
        catalog_reader=runtime.context.catalog_reader,
        snapshot_reader=runtime.ports.snapshot_reader,
        license_reader=runtime.ports.license_reader,
        lifecycle_reader=runtime.ports.lifecycle_reader,
    )
    report = builder.build(
        CertificationBuildRequest(
            dataset_id="stock_daily",
            profile="selection-fields-v1",
            target_from=date(2026, 7, 16),
            target_to=date(2026, 7, 17),
            expected_dates=(date(2026, 7, 16), date(2026, 7, 17)),
            generated_at=visible,
            recovery_evidence=proof,
            consumer_evidence=proof,
            snapshot_ids=(snapshot.snapshot_id,),
            certified_fields=(
                CertifiedField(
                    field="close",
                    snapshot_id=snapshot.snapshot_id,
                    instrument_ids=(1000001,),
                    covered_from=date(2026, 7, 16),
                    covered_to=date(2026, 7, 17),
                    publication_at=visible,
                    available_at=visible,
                    time_precision="timestamp",
                    revised_at=visible,
                    evidence_uri=proof.evidence_uri,
                ),
            ),
        )
    )
    reports.append_report(report)
    reports.approve_report(
        report.report_id, reviewer="test-reviewer", reviewed_at=visible
    )
    return report


@pytest.mark.integration
@pytest.mark.pit
def test_delayed_revision_replay_and_failed_completion_recovery(tmp_path, monkeypatch):
    observed = datetime(2026, 7, 17, 10, tzinfo=UTC)
    with _pipeline(
        tmp_path, "stock_daily", display="allowed", snapshot_now=lambda: observed
    ) as runtime:
        pool = SQLitePool(tmp_path / "reviews.sqlite")
        try:
            reports = SQLiteCertificationStore(SQLiteClient(pool))
            ports = runtime.ports
            now = datetime(2026, 7, 18, 9, tzinfo=UTC)
            admission = FieldAdmissionQuery(
                ports.snapshot_reader,
                ports.license_reader,
                reports,
                ports.lifecycle_reader,
                now=lambda: now,
            )
            reader = ProviderSnapshotQuery(
                SnapshotReadService(
                    ports.snapshot_reader,
                    FilesystemProviderPayloadStore(tmp_path),
                    ports.lifecycle_reader,
                ),
                admission,
            )

            def ingest(frame, force=False):
                return process_fetched_data(
                    frame,
                    "stock_daily",
                    "2026-07-16",
                    force,
                    ctx=runtime.context,
                    request_end="2026-07-17",
                    chunk_id="replay",
                )

            original = _bars()
            assert ingest(original).status == "success"
            first = ports.snapshot_reader.list_snapshots()[0]
            report = _certify(runtime, reports, first, tmp_path, now)
            request = FieldAdmissionRequest(
                fields=(FieldRequirement("stock_daily", "close", first.snapshot_id),),
                instrument_ids=(1000001,),
                required_from=date(2026, 7, 16),
                required_to=date(2026, 7, 17),
                knowledge_cutoff=now,
                publication_cutoff=now,
                purpose="formal_research",
            )
            assert reader.replay(request).frames[first.snapshot_id].equals(original)
            _fail_next_completion(monkeypatch, ports.lifecycle_writer)
            future = original.with_columns(pl.lit(999.0).alias("close"))
            assert ingest(future, True).status == "failed"
            second = next(
                item for item in ports.snapshot_reader.list_snapshots() if item != first
            )
            assert (
                ports.snapshot_reader.get_predecessor(second.snapshot_id)
                == first.snapshot_id
            )
            with pytest.raises(AppQueryError, match="COMPLETE"):
                reader.read_for_audit(second.snapshot_id)
            assert reader.replay(request).frames[first.snapshot_id].equals(original)
            assert ingest(future, True).status == "success"
            assert reader.read_for_audit(second.snapshot_id).frame.equals(future)
            assert reader.replay(request).frames[first.snapshot_id].equals(original)
            events = ports.lifecycle_reader.list_complete()
            assert ingest(future).status == "success"
            assert ports.lifecycle_reader.list_complete() == events
            assert len(ports.snapshot_reader.list_snapshots()) == 2

            reports.revoke_report(
                report.report_id,
                revoked_by="test-reviewer",
                revoked_at=now,
                reason="review withdrawn",
            )
            with pytest.raises(AppQueryError, match="admission"):
                reader.replay(request)
            assert reports.get_report(report.report_id) == report
            assert reader.read_for_audit(first.snapshot_id).frame.equals(original)

            later = now + timedelta(days=1)
            _certify(runtime, reports, second, tmp_path, later)
            revised_request = replace(
                request,
                fields=(FieldRequirement("stock_daily", "close", second.snapshot_id),),
            )
            with pytest.raises(AppQueryError, match="admission"):
                reader.replay(revised_request)
            visible_request = replace(
                revised_request, knowledge_cutoff=later, publication_cutoff=later
            )
            assert (
                reader.replay(visible_request).frames[second.snapshot_id].equals(future)
            )
        finally:
            pool.close()


def _fail_next_completion(monkeypatch, writer):
    advance = writer.advance_partition
    fail = True

    def fail_complete(chunk_id, stage, **kwargs):
        nonlocal fail
        if fail and stage is PartitionLifecycleStatus.COMPLETE:
            fail = False
            raise OSError("injected COMPLETE persistence failure")
        return advance(chunk_id, stage, **kwargs)

    monkeypatch.setattr(writer, "advance_partition", fail_complete)


@pytest.mark.integration
@pytest.mark.pit
def test_replay_refuses_payload_checksum_aliased_across_schema_versions(
    tmp_path,
):
    with _pipeline(tmp_path, "stock_daily", display="allowed") as runtime:
        ports = runtime.ports
        original = _bars()
        assert (
            process_fetched_data(
                original,
                "stock_daily",
                "2026-07-16",
                False,
                ctx=runtime.context,
                request_end="2026-07-17",
                chunk_id="aliased",
            ).status
            == "success"
        )
        first = ports.snapshot_reader.list_snapshots()[0]
        reader = ProviderSnapshotQuery(
            SnapshotReadService(
                ports.snapshot_reader,
                FilesystemProviderPayloadStore(tmp_path),
                ports.lifecycle_reader,
            ),
            FieldAdmissionQuery(
                ports.snapshot_reader,
                ports.license_reader,
                SQLiteCertificationStore(
                    SQLiteClient(SQLitePool(tmp_path / "r.sqlite"))
                ),
                ports.lifecycle_reader,
            ),
        )
        assert reader.read_for_audit(first.snapshot_id).frame.equals(original)

        # A pre-guard writer could publish this same-checksum alias; replay
        # must refuse bytes that cannot prove either schema.
        ports.snapshot_writer.append_snapshot(
            ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id=first.dataset_id,
                    source=first.source,
                    request_start=first.request_start,
                    request_end=first.request_end,
                    schema_version="market.stock_daily.v2",
                    checksum=first.checksum,
                    canonical_asset=first.canonical_asset,
                    request_parameters_hash=first.request_parameters_hash,
                    response_metadata=first.response_metadata,
                    license_record_id=first.license_record_id,
                    row_count=first.row_count,
                    payload_uri=first.payload_uri,
                    payload_retained=first.payload_retained,
                    created_at=first.created_at,
                )
            )
        )

        with pytest.raises(AppQueryError, match="shared across schema versions"):
            reader.read_for_audit(first.snapshot_id)
