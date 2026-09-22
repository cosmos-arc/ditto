"""Historical reads through actual immutable stores and current admission."""

from dataclasses import replace
from datetime import date

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import FieldAdmissionQuery
from ditto_application.queries.historical_universe import HistoricalUniverseQuery
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool
from packages.application.tests.integration.historical_universe_support import (
    VISIBLE,
    history_frames,
    retain_history,
    seed_history,
)


@pytest.mark.integration
@pytest.mark.pit
@pytest.mark.parametrize("asset_kind", ["stock", "etf"])
def test_history_uses_retained_identity_and_refuses_incomplete_revision(
    tmp_path, asset_kind
):
    pool = SQLitePool(tmp_path / "history.sqlite")
    try:
        client = SQLiteClient(pool)
        sources = seed_history(client, tmp_path, asset_kind=asset_kind)
        snapshots = SQLiteProviderSnapshotStore(client)
        lifecycle = SQLitePartitionLifecycleStore(client)
        query = HistoricalUniverseQuery(
            SnapshotReadService(
                snapshots, FilesystemProviderPayloadStore(tmp_path), lifecycle
            ),
            FieldAdmissionQuery(
                snapshots,
                SQLiteDatasetLicenseStore(client),
                SQLiteCertificationStore(client),
                lifecycle,
            ),
        )
        kwargs = {
            "as_of": date(2026, 3, 10),
            "knowledge_cutoff": VISIBLE,
            "publication_cutoff": VISIBLE,
        }
        result = query.resolve(sources, **kwargs)
        assert result.frame["instrument_id"].to_list() == [1]
        assert result.frame["investable"].to_list() == [True]
        master, _ = history_frames(asset_kind=asset_kind)
        revised = master.with_columns(pl.lit(date(2026, 3, 10)).alias("delist_date"))
        second = retain_history(
            client, tmp_path, f"{asset_kind}_basic", revised, complete=False
        )
        with pytest.raises(AppQueryError, match="COMPLETE"):
            query.resolve(
                replace(sources, master_snapshot_id=second.snapshot_id), **kwargs
            )
        # Restore the original active review; audit bytes alone never authorize use.
        retain_history(client, tmp_path, f"{asset_kind}_basic", master)
        replay = query.resolve(sources, **kwargs)
        assert replay.frame.equals(result.frame)
        assert replay.evidence == result.evidence
    finally:
        pool.close_all()
