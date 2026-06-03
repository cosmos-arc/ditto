"""Unit tests for persistent SQLite data catalog store."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _entry(
    dataset_id: str = "stock_daily",
    namespace: str = "market",
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=("trade_date=2026-06-01",),
        ),
        storage_uri=f"{dataset_id}/2026",
        schema=DataSchemaFingerprint(
            schema_hash="schema:stock_daily:v1",
            row_count=2,
            created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            schema_version="market.stock_daily.v1",
            columns=("instrument_id", "trade_date", "close"),
        ),
        source="tushare",
        freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        source_snapshot_id="snapshot:tushare:stock_daily:2026-06-01:abc",
    )


class TestSQLiteDataCatalogPersistence:
    def test_entries_survive_reopened_sqlite_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "catalog.sqlite"
        entry = _entry()

        writer_client, writer_pool = _client(db_path)
        try:
            SQLiteDataCatalog(writer_client).upsert_asset(entry)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            catalog = SQLiteDataCatalog(reader_client)

            assert catalog.get_asset(entry.asset) == entry
            assert catalog.list_assets(namespace="market") == (entry,)
            assert catalog.list_assets(namespace="fundamental") == ()
        finally:
            reader_pool.close()

    def test_upsert_replaces_existing_entry(self, tmp_path: Path) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        catalog = SQLiteDataCatalog(client)
        entry_v1 = _entry()
        entry_v2 = DataCatalogEntry(
            asset=entry_v1.asset,
            storage_uri="stock_daily/2026/replacement",
            schema=DataSchemaFingerprint(
                schema_hash="schema:stock_daily:v2",
                row_count=3,
                created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
                schema_version="market.stock_daily.v2",
                columns=("instrument_id", "trade_date", "close", "volume"),
            ),
            source="tushare",
            freshness_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
            source_snapshot_id="snapshot:tushare:stock_daily:2026-06-01:def",
        )

        try:
            catalog.upsert_asset(entry_v1)
            catalog.upsert_asset(entry_v2)

            persisted = catalog.get_asset(entry_v1.asset)
            assert persisted == entry_v2
            assert (
                persisted.source_snapshot_id
                == "snapshot:tushare:stock_daily:2026-06-01:def"
            )
        finally:
            pool.close()

    def test_rejects_known_dataset_outside_declared_storage_location(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        catalog = SQLiteDataCatalog(client)
        entry = replace(
            _entry(),
            storage_uri="lake://fundamental/stock_daily/2026.parquet",
        )

        try:
            with pytest.raises(ValueError, match="storage_uri"):
                catalog.upsert_asset(entry)

            assert catalog.get_asset(entry.asset) is None
        finally:
            pool.close()


class TestSQLiteDataCatalogProtocols:
    def test_satisfies_catalog_reader_and_writer_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            catalog = SQLiteDataCatalog(client)

            assert isinstance(catalog, DataCatalogReader)
            assert isinstance(catalog, DataCatalogWriter)
        finally:
            pool.close()
