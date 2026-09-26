"""Register licensed retained evidence for isolated system fixtures."""

from datetime import date, datetime
from pathlib import Path

import polars as pl
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


def retain_fixture_payload(
    client: SQLiteClient,
    state_root: Path,
    *,
    dataset_id: str,
    source: str,
    payload: pl.DataFrame,
    created_at: datetime,
) -> None:
    dates = payload.get_column("trade_date").cast(pl.String).to_list()
    start, end = min(dates), max(dates)
    license_record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id=dataset_id,
            source=source,
            terms_version="isolated-test-v1",
            effective_from=date.fromisoformat(start),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="allowed",
            redistribution="prohibited",
            notes="isolated recorded acceptance data",
            reviewed_by="fixture",
            reviewed_at=created_at,
        )
    )
    SQLiteDatasetLicenseStore(client).append_license(license_record)
    artifact = FilesystemProviderPayloadStore(state_root).retain_payload(
        dataset_id=dataset_id, source=source, payload=payload
    )
    SQLiteProviderSnapshotStore(client).append_snapshot(
        ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset_id,
                source=source,
                request_start=start,
                request_end=end,
                schema_version=f"fixture.{dataset_id}.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(dataset_id=dataset_id, namespace="market"),
                request_parameters_hash=f"fixture:{dataset_id}:recorded",
                response_metadata=(("fixture", "isolated-recorded"),),
                license_record_id=license_record.record_id,
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=created_at,
            )
        )
    )
