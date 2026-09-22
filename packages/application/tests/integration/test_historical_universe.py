"""Historical reads through actual immutable stores and current admission."""

from dataclasses import replace
from datetime import date

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import FieldAdmissionQuery
from ditto_application.queries.historical_universe import (
    HistoricalUniverseQuery,
    HistoricalUniverseSources,
)
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


@pytest.mark.integration
@pytest.mark.pit
@pytest.mark.parametrize("asset_kind", ["stock", "etf"])
def test_retained_relationship_boundaries_and_future_knowledge(tmp_path, asset_kind):
    from datetime import UTC, datetime

    pool = SQLitePool(tmp_path / "relations.sqlite")
    try:
        client = SQLiteClient(pool)
        master, status = history_frames((1, 2), asset_kind=asset_kind)
        # The old relation ends on Jan 15. The replacement is only knowable Jan 16.
        relation = master.select(
            "instrument_id",
            "effective_from",
            "effective_to",
            "publication_at",
            "available_at",
        ).with_columns(
            pl.lit("csi300").alias("index_id"),
            pl.when(pl.col("instrument_id") == 1)
            .then(pl.lit(date(2026, 1, 15)))
            .otherwise(None)
            .alias("effective_to"),
        )
        replacement = relation.filter(pl.col("instrument_id") == 1).with_columns(
            pl.lit(date(2026, 1, 15)).alias("effective_from"),
            pl.lit(None, dtype=pl.Date).alias("effective_to"),
            pl.lit(datetime(2026, 1, 16, tzinfo=UTC)).alias("available_at"),
        )
        if asset_kind == "stock":
            sources = seed_history(client, tmp_path, asset_kind=asset_kind, ids=(1, 2))
            membership = retain_history(
                client, tmp_path, "index_weight", pl.concat([relation, replacement])
            )
            sources = replace(
                sources,
                membership_snapshot_id=membership.snapshot_id,
                index_id="csi300",
            )
        else:
            # Known interval change: an ETF switches away from the requested index.
            old = master.with_columns(
                pl.when(pl.col("instrument_id") == 1)
                .then(pl.lit(date(2026, 1, 15)))
                .otherwise(None)
                .alias("effective_to")
            )
            new = master.filter(pl.col("instrument_id") == 1).with_columns(
                pl.lit(date(2026, 1, 15)).alias("effective_from"),
                pl.lit("csi500").alias("tracking_index"),
            )
            primary = retain_history(
                client, tmp_path, "etf_basic", pl.concat([old, new])
            )
            trading = retain_history(client, tmp_path, "etf_daily", status)
            sources = HistoricalUniverseSources(
                "universe.cn.all",
                "etf",
                primary.snapshot_id,
                trading.snapshot_id,
                index_id="csi300",
            )
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

        def resolve(day, cutoff):
            return query.resolve(
                sources,
                as_of=date(2026, 1, day),
                knowledge_cutoff=datetime(2026, 1, cutoff, tzinfo=UTC),
                publication_cutoff=VISIBLE,
            )

        before = resolve(14, 14)
        boundary = resolve(15, 15)
        later = resolve(16, 16)
        assert before.frame["investable"].to_list() == [True, True]
        assert boundary.frame["investable"].to_list() == [False, True]
        assert boundary.frame["exclusion_reasons"].to_list()[0] == [
            "NOT_INDEX_MEMBER" if asset_kind == "stock" else "OTHER_TRACKING_INDEX"
        ]
        assert later.frame["investable"].to_list() == (
            [True, True] if asset_kind == "stock" else [False, True]
        )
        replay = resolve(15, 15)
        assert replay.snapshot_id == boundary.snapshot_id
        assert replay.frame.equals(boundary.frame)
    finally:
        pool.close_all()
