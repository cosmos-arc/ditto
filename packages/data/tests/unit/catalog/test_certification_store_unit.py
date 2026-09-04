"""Coverage and immutable certification store tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.coverage import CoverageCollector, CoverageException
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.catalog.store import InMemoryDataCatalog
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _entry(dataset_id: str, trade_date: date) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace="market",
            partition_keys=(f"trade_date={trade_date.isoformat()}",),
        ),
        storage_uri=f"{dataset_id}/{trade_date.year}",
        schema=DataSchemaFingerprint(
            schema_hash=f"{dataset_id}.v1",
            row_count=10,
            schema_version=f"market.{dataset_id}.v1",
        ),
        source="tushare",
        freshness_at=datetime(2026, 7, 18, tzinfo=UTC),
        source_snapshot_id=f"snapshot:{dataset_id}:{trade_date.isoformat()}",
    )


def _complete_coverage():
    catalog = InMemoryDataCatalog()
    expected = (date(2016, 1, 4), date(2016, 1, 5), date(2016, 1, 6))
    for partition_date in (expected[0], expected[2]):
        catalog.upsert_asset(_entry("stock_status", partition_date))
    exception = CoverageException(
        code="EXCHANGE_SOURCE_GAP",
        owner="data-platform",
        evidence_uri="evidence://coverage/2016-01-05",
        start_date=expected[1],
        end_date=expected[1],
    )
    return CoverageCollector(catalog).collect(
        "stock_status",
        target_to=expected[-1],
        expected_dates=expected,
        exceptions=(exception,),
    )


def _report(*, generated_at: datetime, dq_uri: str = "evidence://dq/pass"):
    return DatasetCertificationReport.create(
        dataset_id="stock_status",
        profile="r2-modern-a-share-v1",
        coverage=_complete_coverage(),
        evidence=CertificationEvidence(
            source_ids=("tushare",),
            schema_versions=("market.stock_status.v1",),
            snapshot_ids=("snapshot:stock_status:2016",),
            dq_rule_version="stock-status-dq-v1",
            dq_results=(EvidenceCheck("l1-l2", dq_uri, passed=True),),
            pit_replay_results=(
                EvidenceCheck("universe-replay", "evidence://pit/pass", passed=True),
            ),
            fallback_history=("fallback=none",),
            override_history=(),
            freshness_results=(
                EvidenceCheck("freshness", "evidence://freshness/pass", passed=True),
            ),
            recovery_results=(
                EvidenceCheck("restore", "evidence://restore/pass", passed=True),
            ),
            license_record_ids=("license:tushare:stock_status:1",),
            consumer_results=(
                EvidenceCheck("r1-shadow", "evidence://r1/pass", passed=True),
            ),
        ),
        generated_at=generated_at,
    )


def test_schedule_aware_coverage_tracks_gap_and_approved_exception() -> None:
    coverage = _complete_coverage()

    assert coverage.expected_partitions == 3
    assert coverage.actual_partitions == 2
    assert coverage.gaps == (date(2016, 1, 5),)
    assert coverage.unapproved_gaps == ()
    assert coverage.raw_from == date(2016, 1, 4)
    assert coverage.complete_from == date(2016, 1, 1)
    assert coverage.is_complete is True


def test_range_catalog_asset_proves_each_expected_partition_in_chunk() -> None:
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        DataCatalogEntry(
            asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=(
                    "start_date=2015-01-05",
                    "end_date=2015-01-07",
                ),
            ),
            storage_uri="stock_daily/2015",
            schema=DataSchemaFingerprint(
                schema_hash="stock_daily.v1",
                row_count=30,
                schema_version="market.stock_daily.v1",
            ),
            source="tushare",
            freshness_at=datetime(2026, 8, 1, tzinfo=UTC),
            source_snapshot_id="snapshot:tushare:stock_daily:range",
        )
    )
    expected = (date(2015, 1, 5), date(2015, 1, 6), date(2015, 1, 7))

    coverage = CoverageCollector(catalog).collect(
        "stock_daily",
        target_to=expected[-1],
        expected_dates=expected,
    )

    assert coverage.actual_partitions == 3
    assert coverage.gaps == ()
    assert coverage.complete_from == date(2015, 1, 1)
    assert coverage.is_complete


def test_coverage_can_certify_an_explicit_bounded_window() -> None:
    catalog = InMemoryDataCatalog()
    for partition_date in (date(2024, 3, 28), date(2024, 3, 29)):
        catalog.upsert_asset(_entry("stock_daily", partition_date))

    coverage = CoverageCollector(catalog).collect(
        "stock_daily",
        target_from=date(2024, 3, 28),
        target_to=date(2024, 3, 29),
        expected_dates=(date(2024, 3, 28), date(2024, 3, 29)),
    )

    assert coverage.target_from == date(2024, 3, 28)
    assert coverage.complete_from == date(2024, 3, 28)
    assert coverage.expected_partitions == 2
    assert coverage.is_complete


def test_provider_request_range_proves_point_partition_asset_coverage() -> None:
    catalog = InMemoryDataCatalog()
    entry = _entry("calendar", date(2015, 12, 31))
    catalog.upsert_asset(entry)
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="calendar",
            source="tushare",
            request_start="2015-01-01",
            request_end="2015-12-31",
            schema_version="market.calendar.v1",
            checksum="sha256:calendar-2015",
            canonical_asset=entry.asset,
            request_parameters_hash="a" * 64,
            response_metadata=(),
            license_record_id="license:tushare:calendar:reviewed",
            row_count=10,
            payload_uri=None,
            payload_retained=False,
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    class _Snapshots:
        def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
            return snapshot if snapshot_id == snapshot.snapshot_id else None

        def list_snapshots(
            self,
            *,
            dataset_id: str | None = None,
            source: str | None = None,
            canonical_asset: DataAssetRef | None = None,
        ) -> tuple[ProviderSnapshot, ...]:
            del source
            if dataset_id not in {None, "calendar"}:
                return ()
            if canonical_asset not in {None, snapshot.canonical_asset}:
                return ()
            return (snapshot,)

    expected = (date(2015, 1, 5), date(2015, 6, 1), date(2015, 12, 31))

    coverage = CoverageCollector(catalog, _Snapshots()).collect(
        "calendar",
        target_to=expected[-1],
        expected_dates=expected,
    )

    assert coverage.actual_partitions == 3
    assert coverage.gaps == ()
    assert coverage.complete_from == date(2015, 1, 1)


def test_report_hash_is_frozen_and_rejects_fact_mutation() -> None:
    report = _report(generated_at=datetime(2026, 7, 18, 9, tzinfo=UTC))

    with pytest.raises(ValueError, match="content_hash"):
        replace(report, content_hash="tampered")


def test_active_profile_rejects_conflicting_report_content() -> None:
    store = _store()
    first = _report(generated_at=datetime(2026, 7, 18, 9, tzinfo=UTC))
    conflict = _report(
        generated_at=datetime(2026, 7, 18, 10, tzinfo=UTC),
        dq_uri="evidence://dq/different",
    )

    store.append_report(first)

    with pytest.raises(ValueError, match="active certification report conflict"):
        store.append_report(conflict)


def test_review_revoke_and_recertify_are_append_only() -> None:
    store = _store()
    first = store.append_report(
        _report(generated_at=datetime(2026, 7, 18, 9, tzinfo=UTC))
    )
    approved = store.approve_report(
        first.report_id,
        reviewer="data-reviewer",
        reviewed_at=datetime(2026, 7, 18, 10, tzinfo=UTC),
    )
    assert approved.action == "approved"
    assert store.get_active_report("stock_status", "r2-modern-a-share-v1") == first

    revoked = store.revoke_report(
        first.report_id,
        revoked_by="data-reviewer",
        revoked_at=datetime(2026, 7, 18, 11, tzinfo=UTC),
        reason="coverage_regression",
    )
    assert revoked.action == "revoked"
    assert store.get_active_report("stock_status", "r2-modern-a-share-v1") is None

    second = store.append_report(
        _report(generated_at=datetime(2026, 7, 18, 12, tzinfo=UTC))
    )
    store.approve_report(
        second.report_id,
        reviewer="data-reviewer",
        reviewed_at=datetime(2026, 7, 18, 13, tzinfo=UTC),
    )

    assert second.report_id != first.report_id
    assert store.list_reports("stock_status", "r2-modern-a-share-v1") == (
        first,
        second,
    )
    assert [event.action for event in store.list_events(first.report_id)] == [
        "approved",
        "revoked",
    ]


def _store() -> SQLiteCertificationStore:
    pool = SQLitePool(":memory:")
    return SQLiteCertificationStore(SQLiteClient(pool))
