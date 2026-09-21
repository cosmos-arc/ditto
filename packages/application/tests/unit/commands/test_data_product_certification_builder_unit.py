"""Tests for machine-built R2 product certification reports."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest
from ditto_application.commands.data_product_certification_builder import (
    AddressedCertificationEvidence,
    CertificationBuildRequest,
    DataProductCertificationBuilder,
    load_certified_field_claims,
)
from ditto_application.exceptions import AppProcessError
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)


def _fixture(
    tmp_path,
    *,
    canonical_row_count: int = 1,
    provider_row_count: int = 1,
):
    now = datetime(2026, 8, 1, tzinfo=UTC)
    asset = DataAssetRef(
        dataset_id="stock_daily",
        namespace="market",
        partition_keys=(
            "start_date=2015-01-05",
            "end_date=2015-01-05",
        ),
    )
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        DataCatalogEntry(
            asset=asset,
            storage_uri="stock_daily/2015",
            schema=DataSchemaFingerprint(
                schema_hash="schema:sha256:value",
                row_count=canonical_row_count,
                created_at=now,
                schema_version="market.stock_daily.v1",
                columns=("trade_date", "close"),
            ),
            source="tushare",
            freshness_at=now,
            source_snapshot_id="catalog-snapshot",
        )
    )
    license_record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="stock_daily",
            source="tushare",
            terms_version="reviewed-v1",
            effective_from=date(2026, 8, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="restricted",
            redistribution="prohibited",
            notes="Reviewed local research use.",
            reviewed_by="chevy",
            reviewed_at=now,
        )
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2015-01-05",
            request_end="2015-01-05",
            schema_version="market.stock_daily.v1",
            checksum="payload-checksum",
            canonical_asset=asset,
            request_parameters_hash="sha256:request",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=license_record.record_id,
            row_count=provider_row_count,
            payload_uri="stock_daily/2015",
            payload_retained=True,
            created_at=now,
        )
    )
    chunk_id = "chunk:tushare:stock_daily:2015-01"
    checkpoint = PartitionCheckpoint(
        chunk_id=chunk_id,
        dataset_id="stock_daily",
        source="tushare",
        request_start="2015-01-05",
        request_end="2015-01-05",
        status=PartitionLifecycleStatus.COMPLETE,
        last_successful_stage=PartitionLifecycleStatus.COMPLETE,
        attempt=1,
        retry_budget=3,
        payload_id="payload:payload-checksum:stock_daily/2015",
        catalog_asset_id="catalog:market:stock_daily",
        lineage_run_id="lineage:1",
        ingestion_log_id="log:1",
        error_code=None,
        updated_at=now,
    )
    events = tuple(
        PartitionLifecycleEvent(
            event_id=index,
            chunk_id=chunk_id,
            from_status=None,
            to_status=status,
            attempt=1,
            evidence_id=None,
            error_code=None,
            occurred_at=now,
        )
        for index, status in enumerate(
            (
                PartitionLifecycleStatus.PIT_PASSED,
                PartitionLifecycleStatus.DQ_PASSED,
                PartitionLifecycleStatus.COMPLETE,
            ),
            start=1,
        )
    )
    snapshot_reader = SimpleNamespace(
        list_snapshots=lambda **_kwargs: (snapshot,),
    )
    license_reader = SimpleNamespace(
        get_license=lambda record_id: (
            license_record if record_id == license_record.record_id else None
        )
    )
    lifecycle = SimpleNamespace(
        list_complete=lambda **_kwargs: (checkpoint,),
        list_incomplete=lambda **_kwargs: (),
        list_events=lambda requested: events if requested == chunk_id else (),
    )
    recovery = tmp_path / "recovery.json"
    consumer = tmp_path / "consumer.json"
    recovery.write_bytes(b'{"passed":true,"kind":"recovery"}')
    consumer.write_bytes(b'{"passed":true,"kind":"consumer"}')
    return (
        DataProductCertificationBuilder(
            catalog_reader=catalog,
            snapshot_reader=snapshot_reader,
            license_reader=license_reader,
            lifecycle_reader=lifecycle,
        ),
        CertificationBuildRequest(
            dataset_id="stock_daily",
            profile="r2-modern-a-share-v1",
            target_to=date(2015, 1, 5),
            expected_dates=(date(2015, 1, 5),),
            generated_at=now,
            recovery_evidence=AddressedCertificationEvidence(
                name="backup_restore_hash_parity",
                evidence_uri="evidence://r2/recovery.json",
                local_path=recovery,
                sha256_hex=sha256(recovery.read_bytes()).hexdigest(),
            ),
            consumer_evidence=AddressedCertificationEvidence(
                name="consumer_read_smoke",
                evidence_uri="evidence://r2/consumer.json",
                local_path=consumer,
                sha256_hex=sha256(consumer.read_bytes()).hexdigest(),
            ),
        ),
    )


@pytest.mark.unit
def test_builder_derives_report_from_complete_content_addressed_chain(tmp_path) -> None:
    builder, request = _fixture(tmp_path)

    report = builder.build(request)

    assert report.dataset_id == "stock_daily"
    assert report.coverage.is_complete
    assert report.evidence.all_checks_passed
    assert report.evidence.source_ids == ("tushare",)
    assert "universe" in report.evidence.pit_replay_results[0].name
    assert report.evidence.recovery_results[0].evidence_uri.endswith("recovery.json")


@pytest.mark.unit
def test_builder_preserves_explicit_bounded_certification_window(tmp_path) -> None:
    builder, request = _fixture(tmp_path)
    bounded_from = date(2015, 1, 5)

    report = builder.build(replace(request, target_from=bounded_from))

    assert report.coverage.target_from == bounded_from
    assert report.coverage.complete_from == bounded_from


@pytest.mark.unit
def test_builder_allows_provider_rows_filtered_from_canonical_asset(tmp_path) -> None:
    builder, request = _fixture(tmp_path, provider_row_count=2)

    report = builder.build(request)

    assert report.coverage.is_complete


@pytest.mark.unit
def test_builder_rejects_canonical_rows_exceeding_provider_payload(tmp_path) -> None:
    builder, request = _fixture(
        tmp_path,
        canonical_row_count=2,
        provider_row_count=1,
    )

    with pytest.raises(AppProcessError, match="exceeds provider payload"):
        builder.build(request)


@pytest.mark.unit
def test_builder_rejects_external_artifact_hash_mismatch(tmp_path) -> None:
    builder, request = _fixture(tmp_path)
    request.recovery_evidence.local_path.write_bytes(b"mutated")

    with pytest.raises(AppProcessError, match="hash mismatch"):
        builder.build(request)


@pytest.mark.unit
def test_builder_rejects_unknown_snapshot_allowlist_entry(tmp_path) -> None:
    builder, request = _fixture(tmp_path)

    with pytest.raises(AppProcessError, match="unknown IDs"):
        builder.build(replace(request, snapshot_ids=("missing-snapshot",)))


def test_builder_rejects_field_claim_without_exact_schema_evidence(tmp_path) -> None:
    from ditto_data.catalog.field_evidence import CertifiedField

    builder, request = _fixture(tmp_path)
    original = builder.build(request)
    field = CertifiedField(
        field="unobserved_column",
        snapshot_id=original.evidence.snapshot_ids[0],
        instrument_ids=(600000,),
        covered_from=request.target_to,
        covered_to=request.target_to,
        available_at=None,
        publication_at=None,
        time_precision="unknown",
        evidence_uri=request.consumer_evidence.evidence_uri,
    )
    with pytest.raises(AppProcessError, match="exact catalog schema"):
        builder.build(replace(request, certified_fields=(field,)))
    admitted = replace(field, field="close")
    assert builder.build(
        replace(request, certified_fields=(admitted,))
    ).evidence.certified_fields == (admitted,)
    with pytest.raises(AppProcessError, match="verified consumer evidence"):
        builder.build(
            replace(
                request, certified_fields=(replace(admitted, evidence_uri="unknown"),)
            )
        )
    with pytest.raises(AppProcessError, match="unique"):
        builder.build(replace(request, certified_fields=(admitted, admitted)))


def test_builder_binds_input_digests_to_retained_verified_consumer_artifact(tmp_path):
    import orjson
    from ditto_data.catalog.field_evidence import CertifiedField, consumer_input_digest

    builder, request = _fixture(tmp_path)
    original = builder.build(request)
    payload = {"consumer_field": "instruments.close", "observed": [[600000, 10.5]]}
    raw = orjson.dumps({"field_inputs": [payload]})
    request.consumer_evidence.local_path.write_bytes(raw)
    field = CertifiedField(
        field="close",
        snapshot_id=original.evidence.snapshot_ids[0],
        instrument_ids=(600000,),
        covered_from=request.target_to,
        covered_to=request.target_to,
        available_at=None,
        publication_at=None,
        time_precision="unknown",
        evidence_uri=request.consumer_evidence.evidence_uri,
        consumer_bindings=(("instruments.close", consumer_input_digest(payload)),),
    )
    bound = replace(
        request,
        certified_fields=(field,),
        consumer_evidence=replace(
            request.consumer_evidence, sha256_hex=sha256(raw).hexdigest()
        ),
    )
    assert builder.build(bound).evidence.certified_fields == (field,)
    forged = replace(field, consumer_bindings=(("instruments.close", "f" * 64),))
    with pytest.raises(AppProcessError, match="does not match retained evidence"):
        builder.build(replace(bound, certified_fields=(forged,)))


def test_load_certified_field_claims_parses_only_reviewed_claim_arrays(tmp_path):
    import orjson
    from ditto_data.catalog.field_evidence import CertifiedField

    claim = {
        "field": "amount",
        "snapshot_id": "snapshot:sha256:abc",
        "instrument_ids": [600000],
        "covered_from": "2026-09-18",
        "covered_to": "2026-09-18",
        "available_at": None,
        "publication_at": None,
        "time_precision": "timestamp",
        "evidence_uri": "artifact+sha256://consumer/abc",
    }
    path = tmp_path / "claims.json"
    path.write_bytes(orjson.dumps([claim]))

    assert load_certified_field_claims(path) == (
        CertifiedField(
            field="amount",
            snapshot_id="snapshot:sha256:abc",
            instrument_ids=(600000,),
            covered_from=date(2026, 9, 18),
            covered_to=date(2026, 9, 18),
            available_at=None,
            publication_at=None,
            time_precision="timestamp",
            evidence_uri="artifact+sha256://consumer/abc",
        ),
    )

    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b"{}")
    with pytest.raises(AppProcessError, match="array of objects"):
        load_certified_field_claims(malformed)
    reversed_interval = tmp_path / "reversed.json"
    reversed_interval.write_bytes(
        orjson.dumps([claim | {"covered_from": "2026-09-19"}])
    )
    with pytest.raises(AppProcessError, match="reversed"):
        load_certified_field_claims(reversed_interval)
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"[]")
    with pytest.raises(AppProcessError, match="must not be empty"):
        load_certified_field_claims(empty)
