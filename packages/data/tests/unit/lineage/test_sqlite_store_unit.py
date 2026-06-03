"""Unit tests for persistent SQLite data lineage store."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    DataLineageReader,
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_data.lineage.sqlite_store import SQLiteDataLineage
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _event(
    run_id: str,
    *,
    input_asset: DataAssetRef,
    output_asset: DataAssetRef,
    timestamp: datetime,
) -> LineageEvent:
    return LineageEvent(
        run_id=run_id,
        operation="materialize",
        inputs=(LineageInputRef(asset=input_asset, role="raw"),),
        outputs=(LineageOutputRef(asset=output_asset, role="published"),),
        timestamp=timestamp,
    )


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


class TestSQLiteDataLineagePersistence:
    def test_records_survive_reopened_sqlite_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "lineage.sqlite"
        raw = DataAssetRef(
            dataset_id="bars",
            namespace="market",
            partition_keys=("trade_date=2026-06-01",),
        )
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        event = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        )

        writer_client, writer_pool = _client(db_path)
        try:
            SQLiteDataLineage(writer_client).record_event(event)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            lineage = SQLiteDataLineage(reader_client)

            assert lineage.list_events_for_asset(raw) == (event,)
            assert lineage.list_events_for_asset(clean) == (event,)
        finally:
            reader_pool.close()

    def test_lists_events_in_append_order_not_timestamp_order(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "lineage.sqlite")
        raw = DataAssetRef(dataset_id="bars", namespace="market")
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        lineage = SQLiteDataLineage(client)
        event_1 = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        )
        event_2 = _event(
            "run-2",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        )

        try:
            lineage.record_event(event_1)
            lineage.record_event(event_2)

            assert lineage.list_events_for_asset(raw) == (event_1, event_2)
        finally:
            pool.close()

    def test_lists_events_for_run_in_append_order(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "lineage.sqlite")
        raw = DataAssetRef(dataset_id="bars", namespace="market")
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        features = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        lineage = SQLiteDataLineage(client)
        event_1 = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        )
        event_2 = _event(
            "run-2",
            input_asset=clean,
            output_asset=features,
            timestamp=datetime(2026, 6, 1, 9, 1, tzinfo=UTC),
        )
        event_3 = _event(
            "run-1",
            input_asset=clean,
            output_asset=features,
            timestamp=datetime(2026, 6, 1, 9, 2, tzinfo=UTC),
        )

        try:
            lineage.record_event(event_1)
            lineage.record_event(event_2)
            lineage.record_event(event_3)

            assert lineage.list_events_for_run("run-1") == (event_1, event_3)
            assert lineage.list_events_for_run("missing") == ()
        finally:
            pool.close()


class TestSQLiteDataLineageProtocols:
    def test_satisfies_lineage_reader_and_recorder_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "lineage.sqlite")
        try:
            lineage = SQLiteDataLineage(client)

            assert isinstance(lineage, DataLineageReader)
            assert isinstance(lineage, DataLineageRecorder)
        finally:
            pool.close()
