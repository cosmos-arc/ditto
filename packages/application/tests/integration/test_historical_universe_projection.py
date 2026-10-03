"""Raw provider shapes project into PIT intervals for the historical pool."""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.queries.historical_universe import HistoricalUniverseQuery
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool
from packages.application.tests.integration.historical_universe_support import (
    retain_history,
)

_AS_OF = date(2026, 9, 30)
_CUTOFF = datetime(2026, 10, 3, 12, tzinfo=UTC)


def _resolver(
    mapping: dict[str, int],
):
    def resolve(tickers: list[str], *, source: str, asof: str) -> dict[str, int]:
        return {ticker: mapping[ticker] for ticker in tickers if ticker in mapping}

    return resolve


@pytest.mark.integration
@pytest.mark.pit
def test_raw_daily_shapes_project_into_same_day_intervals(tmp_path: Path) -> None:
    """Real stock_basic/stock_status payload shapes resolve without golden frames."""
    pool = SQLitePool(tmp_path / "history.sqlite")
    try:
        client = SQLiteClient(pool)
        master = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "600000.SH"],
                "name": ["Ping An Bank", "Delisted Corp"],
                "exchange": ["SZSE", "XSHG"],
                "list_date": [date(1991, 4, 3), date(2000, 1, 10)],
                "delist_date": [None, date(2026, 6, 30)],
                "list_status": ["L", "D"],
            }
        )
        status = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "600000.SH", "999999.SH"],
                "trade_date": [_AS_OF] * 3,
                "is_suspended": [False, False, True],
                "is_st": [False, False, None],
                "list_status": ["L", "D", "L"],
            }
        )
        master_snapshot = retain_history(client, tmp_path, "stock_basic", master)
        status_snapshot = retain_history(client, tmp_path, "stock_status", status)
        snapshots = SQLiteProviderSnapshotStore(client)
        lifecycle = SQLitePartitionLifecycleStore(client)
        query = HistoricalUniverseQuery(
            SnapshotReadService(
                snapshots, FilesystemProviderPayloadStore(tmp_path), lifecycle
            ),
            SnapshotReadinessQuery(snapshots, lifecycle),
            ticker_resolver=_resolver(
                {"000001.SZ": 1_000_001, "600000.SH": 600_001, "999999.SH": 999_999}
            ),
        )
        result = query.resolve(
            _sources(master_snapshot.snapshot_id, status_snapshot.snapshot_id),
            as_of=_AS_OF,
            knowledge_cutoff=_CUTOFF,
            publication_cutoff=_CUTOFF,
        )
        rows = {row["instrument_id"]: row for row in result.frame.to_dicts()}
        # Delisted members stay in the roster (survivorship bias guard) and
        # carry their honest exclusion; unresolved tickers stay out.
        assert set(rows) == {1_000_001, 600_001}
        assert rows[1_000_001]["investable"] is True
        assert rows[600_001]["investable"] is False
        assert "DELISTED" in rows[600_001]["exclusion_reasons"]
    finally:
        pool.close_all()


@pytest.mark.integration
@pytest.mark.pit
def test_later_observation_does_not_leak_into_earlier_cutoff(tmp_path: Path) -> None:
    """A snapshot observed after the cutoff is invisible to that replay."""
    pool = SQLitePool(tmp_path / "history.sqlite")
    try:
        client = SQLiteClient(pool)
        master = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "list_date": [date(1991, 4, 3)],
                "delist_date": [None],
                "list_status": ["L"],
            }
        )
        late_master = retain_history(
            client,
            tmp_path,
            "stock_basic",
            master,
            observed=datetime(2026, 10, 5, tzinfo=UTC),
        )
        late_status = retain_history(
            client,
            tmp_path,
            "stock_status",
            pl.DataFrame(
                {
                    "source_ticker": ["000001.SZ"],
                    "trade_date": [_AS_OF],
                    "is_suspended": [False],
                }
            ),
            observed=datetime(2026, 10, 5, tzinfo=UTC),
        )
        snapshots = SQLiteProviderSnapshotStore(client)
        lifecycle = SQLitePartitionLifecycleStore(client)
        query = HistoricalUniverseQuery(
            SnapshotReadService(
                snapshots, FilesystemProviderPayloadStore(tmp_path), lifecycle
            ),
            SnapshotReadinessQuery(snapshots, lifecycle),
            ticker_resolver=_resolver({"000001.SZ": 1_000_001}),
        )
        with pytest.raises(Exception, match="HISTORY_NOT_OBSERVED"):
            query.resolve(
                _sources(late_master.snapshot_id, late_status.snapshot_id),
                as_of=_AS_OF,
                knowledge_cutoff=_CUTOFF,
                publication_cutoff=_CUTOFF,
            )
    finally:
        pool.close_all()


def _sources(master_id: str, status_id: str):
    from ditto_application.queries.historical_universe import HistoricalUniverseSources

    return HistoricalUniverseSources(
        universe_id="universe.cn.all",
        asset_kind="stock",
        master_snapshot_ids=(master_id,),
        status_snapshot_ids=(status_id,),
    )


@pytest.mark.integration
def test_universe_replace_constituents_replays_same_effective_date(tmp_path) -> None:
    """#415: replaying a member update on the same date must not hit UNIQUE."""
    from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter

    pool = SQLitePool(tmp_path / "universe.sqlite")
    try:
        client = SQLiteClient(pool)
        client.execute(
            """CREATE TABLE universe (
                universe_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                universe_type TEXT,
                source_ref TEXT
            )"""
        )
        client.execute(
            """CREATE TABLE universe_constituent (
                universe_id TEXT,
                instrument_id INTEGER,
                effective_from TEXT,
                effective_to TEXT,
                weight REAL,
                source TEXT,
                source_ticker TEXT,
                PRIMARY KEY (universe_id, instrument_id, effective_from)
            )"""
        )
        client.commit()
        client.execute(
            """INSERT INTO universe (universe_id, name, description,
               universe_type, source_ref) VALUES ('u1', 'Test', NULL, 'custom', NULL)"""
        )
        client.commit()
        writer = UniverseWriter(client, MagicMock())
        records = [
            {"instrument_id": 10, "effective_from": "2026-09-30"},
            {"instrument_id": 20, "effective_from": "2026-09-30"},
        ]
        writer.replace_constituents("u1", records, "2026-09-30")
        # Same-date replay with a different roster replaces instead of failing.
        writer.replace_constituents("u1", [records[0]], "2026-09-30")
        rows = client.execute(
            """SELECT instrument_id, effective_to FROM universe_constituent
            WHERE universe_id = 'u1' ORDER BY instrument_id"""
        ).fetchall()
        assert [row[0] for row in rows] == [10]
        # Same-date replay replaces the day's rows outright: the surviving row
        # is open-ended, and no UNIQUE conflict was raised.
        assert rows[0][1] is None
    finally:
        pool.close_all()
