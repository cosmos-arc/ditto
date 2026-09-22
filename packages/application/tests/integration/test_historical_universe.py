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
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadReader,
)
from ditto_data.catalog.snapshot_reader import SnapshotContents, SnapshotReadService
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool
from packages.application.tests.integration.historical_universe_support import (
    VISIBLE,
    certify_snapshots,
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
                replace(sources, master_snapshot_ids=(second.snapshot_id,)), **kwargs
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
                membership_snapshot_ids=(membership.snapshot_id,),
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
                (primary.snapshot_id,),
                (trading.snapshot_id,),
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


class _CountingSnapshotReader(SnapshotReadService):
    """Count payload reads to prove pinned sources are loaded once per pin."""

    reads: int

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        lifecycle: PartitionLifecycleReader,
    ) -> None:
        super().__init__(snapshots, payloads, lifecycle)
        self.reads = 0

    def read(self, snapshot_id: str) -> SnapshotContents:
        self.reads += 1
        return super().read(snapshot_id)


@pytest.mark.integration
@pytest.mark.pit
def test_snapshot_chain_resolves_day_visible_member_and_pins_reads_once(tmp_path):
    """A pinned chain replays the snapshot each cutoff had actually observed."""
    from datetime import UTC, datetime

    pool = SQLitePool(tmp_path / "chain.sqlite")
    try:
        client = SQLiteClient(pool)
        master, status = history_frames()
        primary = retain_history(client, tmp_path, "stock_basic", master)
        first = retain_history(
            client,
            tmp_path,
            "stock_status",
            status,
            observed=datetime(2026, 1, 14, 12, tzinfo=UTC),
            certify=False,
        )
        # Same effective key, revised suspension only knowable Jan 15 noon and
        # only present in a snapshot observed Jan 16: no local knowledge leak.
        revised = status.with_columns(
            pl.lit(True).alias("is_suspended"),
            pl.lit(datetime(2026, 1, 15, 12, tzinfo=UTC)).alias("available_at"),
            pl.lit(datetime(2026, 1, 15, 12, tzinfo=UTC)).alias("publication_at"),
        )
        second = retain_history(
            client,
            tmp_path,
            "stock_status",
            revised,
            observed=datetime(2026, 1, 16, 4, tzinfo=UTC),
            certify=False,
        )
        certify_snapshots(
            client,
            "stock_status",
            (
                (first, status, datetime(2026, 1, 14, 12, tzinfo=UTC)),
                (second, revised, datetime(2026, 1, 16, 4, tzinfo=UTC)),
            ),
        )
        snapshots = SQLiteProviderSnapshotStore(client)
        lifecycle = SQLitePartitionLifecycleStore(client)
        reader = _CountingSnapshotReader(
            snapshots, FilesystemProviderPayloadStore(tmp_path), lifecycle
        )
        query = HistoricalUniverseQuery(
            reader,
            FieldAdmissionQuery(
                snapshots,
                SQLiteDatasetLicenseStore(client),
                SQLiteCertificationStore(client),
                lifecycle,
            ),
        )
        chain = HistoricalUniverseSources(
            "universe.cn.all",
            "stock",
            (primary.snapshot_id,),
            (first.snapshot_id, second.snapshot_id),
        )
        pinned = query.pin(chain)
        assert reader.reads == 3

        before = pinned.resolve(
            as_of=date(2026, 1, 14),
            knowledge_cutoff=datetime(2026, 1, 15, tzinfo=UTC),
            publication_cutoff=datetime(2026, 1, 15, tzinfo=UTC),
        )
        assert before.frame["investable"].to_list() == [True]
        after = pinned.resolve(
            as_of=date(2026, 1, 16),
            knowledge_cutoff=datetime(2026, 1, 16, 12, tzinfo=UTC),
            publication_cutoff=datetime(2026, 1, 16, 12, tzinfo=UTC),
        )
        assert after.frame["investable"].to_list() == [False]
        assert after.frame["exclusion_reasons"].to_list() == [["SUSPENDED"]]
        assert after.evidence["admission"][1]["snapshot_id"] == second.snapshot_id
        assert before.evidence["admission"][1]["snapshot_id"] == first.snapshot_id
        # Pinned payloads serve every projection: no extra reads per day.
        assert reader.reads == 3
        # A cutoff before any member was observed locally still fails closed.
        with pytest.raises(AppQueryError, match="HISTORY_NOT_OBSERVED"):
            pinned.resolve(
                as_of=date(2026, 1, 13),
                knowledge_cutoff=datetime(2026, 1, 13, 12, tzinfo=UTC),
                publication_cutoff=datetime(2026, 1, 13, 12, tzinfo=UTC),
            )
    finally:
        pool.close_all()
