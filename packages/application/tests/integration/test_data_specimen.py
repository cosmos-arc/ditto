"""Integration tests for the five-category specimen summary query."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ditto_application.queries.data_specimen import DataSpecimenQuery
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.license import (
    DatasetLicenseDraft,
    DatasetLicenseRecord,
)
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.catalog.specimen import (
    SPECIMEN_CATEGORIES,
    DataSpecimen,
    SpecimenSource,
)
from ditto_data.catalog.specimen_store import SQLiteSpecimenStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _license(client: SQLiteClient) -> DatasetLicenseRecord:
    record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="dividend",
            source="recorded",
            terms_version="v1",
            effective_from=date(2000, 1, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="allowed",
            redistribution="prohibited",
            notes="synthetic",
            reviewed_by="test",
            reviewed_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
    )
    SQLiteDatasetLicenseStore(client).append_license(record)
    return record


def _provider_snapshot(client: SQLiteClient, root: Path) -> ProviderSnapshot:
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="dividend",
            source="recorded",
            request_start="2026-01-01",
            request_end="2026-06-30",
            schema_version="v1",
            checksum="specimen-checksum",
            canonical_asset=DataAssetRef(namespace="dividend", dataset_id="dividend"),
            request_parameters_hash="specimen",
            response_metadata=(),
            license_record_id="unused",
            row_count=1,
            payload_uri=None,
            payload_retained=False,
            created_at=datetime(2026, 9, 20, tzinfo=UTC),
        )
    )
    SQLiteProviderSnapshotStore(client).append_snapshot(snapshot)
    return snapshot


def _verified_specimen(license_id: str, snapshot_id: str) -> DataSpecimen:
    return DataSpecimen(
        category="dividend_etf",
        dataset_id="dividend",
        anchor="510300.SH",
        sources=(
            SpecimenSource(
                source="recorded",
                provider_snapshot_id=snapshot_id,
            ),
        ),
        coverage_from=date(2026, 1, 1),
        coverage_to=date(2026, 6, 30),
        knowable_from=datetime(2026, 7, 1, tzinfo=UTC),
        time_precision="date",
        as_of_counterexample="cutoff before announcement keeps prior dividend",
        license_record_ids=(license_id,),
        allowed_uses=("display", "exploration"),
        verification_status="verified",
        adjudicated_by="test",
        adjudicated_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


@pytest.fixture
def stores(tmp_path: Path):
    pool = SQLitePool(str(tmp_path / "catalog.sqlite"))
    client = SQLiteClient(pool)
    try:
        yield client, tmp_path
    finally:
        pool.close_all()


def _query(client: SQLiteClient) -> DataSpecimenQuery:
    return DataSpecimenQuery(
        specimens=SQLiteSpecimenStore(client),
        snapshots=SQLiteProviderSnapshotStore(client),
        licenses=SQLiteDatasetLicenseStore(client),
    )


@pytest.mark.integration
def test_summarize_returns_all_five_categories_with_missing_explicit(
    stores,
) -> None:
    client, root = stores
    license_record = _license(client)
    snapshot = _provider_snapshot(client, root)
    SQLiteSpecimenStore(client).append_specimen(
        _verified_specimen(license_record.record_id, snapshot.snapshot_id)
    )

    summaries = _query(client).summarize()

    assert tuple(item.category for item in summaries) == SPECIMEN_CATEGORIES
    collected = {item.category: item for item in summaries}
    dividend = collected["dividend_etf"]
    assert dividend.collected is True
    assert dividend.latest is not None
    assert dividend.latest.allowed_uses == ("display", "exploration")
    assert dividend.unresolved_gaps == ()
    for category in (
        "financial_restatement",
        "delisted_security",
        "index_rebalance",
        "cross_border_etf",
    ):
        summary = collected[category]
        assert summary.collected is False
        assert summary.latest is None
        assert summary.unresolved_gaps == ("SPECIMEN_NOT_COLLECTED",)


@pytest.mark.integration
def test_dangling_references_surface_as_unresolved_gaps(stores) -> None:
    client, _root = stores
    SQLiteSpecimenStore(client).append_specimen(
        _verified_specimen(
            "license:missing:record",
            "snapshot:missing:dividend:sha256:none",
        )
    )

    summaries = {summary.category: summary for summary in _query(client).summarize()}
    dividend = summaries["dividend_etf"]

    assert dividend.unresolved_gaps == (
        "SPECIMEN_SOURCE_SNAPSHOT_MISSING",
        "SPECIMEN_LICENSE_MISSING",
    )


@pytest.mark.integration
def test_newest_adjudication_leads_the_category_history(stores) -> None:
    client, root = stores
    license_record = _license(client)
    snapshot = _provider_snapshot(client, root)
    older = _verified_specimen(license_record.record_id, snapshot.snapshot_id)
    newer = DataSpecimen(
        category="dividend_etf",
        dataset_id="dividend",
        anchor="510500.SH",
        sources=(SpecimenSource(source="recorded"),),
        gaps=("REAL_SAMPLE_NOT_COLLECTED",),
        # A re-adjudication verdict carries its own later timestamp; records
        # without one are drafts and never become the latest verdict.
        adjudicated_by="test",
        adjudicated_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    SQLiteSpecimenStore(client).append_specimen(older)
    SQLiteSpecimenStore(client).append_specimen(newer)

    summary = {item.category: item for item in _query(client).summarize()}[
        "dividend_etf"
    ]

    assert summary.latest is not None
    assert summary.latest.anchor == "510500.SH"
    assert summary.latest.verification_status == "unverified"
    assert len(summary.specimens) == 2
