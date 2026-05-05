from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import assert_type

import pytest
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)


def test_data_asset_ref_is_frozen_and_uses_tuple_default() -> None:
    asset = DataAssetRef(dataset_id="bars", namespace="market")

    assert asset.partition_keys == ()
    with pytest.raises(FrozenInstanceError):
        asset.dataset_id = "ticks"  # type: ignore[misc]


def test_catalog_entry_carries_storage_implementation_free_locator_metadata() -> None:
    asset = DataAssetRef(
        dataset_id="bars",
        namespace="market",
        partition_keys=("trade_date",),
    )
    schema = DataSchemaFingerprint(schema_hash="sha256:abc", row_count=3)
    timestamp = datetime(2026, 5, 6, tzinfo=UTC)
    entry = DataCatalogEntry(
        asset=asset,
        storage_uri="lake://market/bars",
        schema=schema,
        source="fixture",
        freshness_at=timestamp,
    )

    assert entry.asset is asset
    assert entry.storage_uri == "lake://market/bars"
    assert entry.schema is schema
    assert entry.freshness_at == timestamp
    with pytest.raises(FrozenInstanceError):
        entry.source = "other"  # type: ignore[misc]


def test_catalog_protocols_accept_structural_in_memory_fake() -> None:
    class InMemoryCatalog:
        def __init__(self) -> None:
            self._entries: dict[DataAssetRef, DataCatalogEntry] = {}

        def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
            return self._entries.get(asset)

        def list_assets(
            self,
            namespace: str | None = None,
        ) -> tuple[DataCatalogEntry, ...]:
            entries = tuple(self._entries.values())
            if namespace is None:
                return entries
            return tuple(
                entry for entry in entries if entry.asset.namespace == namespace
            )

        def upsert_asset(self, entry: DataCatalogEntry) -> None:
            self._entries[entry.asset] = entry

    asset = DataAssetRef(dataset_id="fundamentals", namespace="financials")
    entry = DataCatalogEntry(
        asset=asset,
        storage_uri="lake://financials/fundamentals",
        schema=DataSchemaFingerprint(schema_hash="sha256:def"),
        source="unit-test",
        freshness_at=datetime(2026, 5, 6, tzinfo=UTC),
    )
    catalog = InMemoryCatalog()

    assert isinstance(catalog, DataCatalogReader)
    assert isinstance(catalog, DataCatalogWriter)
    writer: DataCatalogWriter = catalog
    reader: DataCatalogReader = catalog
    assert_type(writer, DataCatalogWriter)
    assert_type(reader, DataCatalogReader)

    writer.upsert_asset(entry)

    assert reader.get_asset(asset) == entry
    assert reader.list_assets("financials") == (entry,)
    assert reader.list_assets("market") == ()


def test_catalog_contracts_have_canonical_modules() -> None:
    expected_module = "ditto_data.catalog.contracts"

    assert DataAssetRef.__module__ == expected_module
    assert DataSchemaFingerprint.__module__ == expected_module
    assert DataCatalogEntry.__module__ == expected_module
    assert DataCatalogReader.__module__ == expected_module
    assert DataCatalogWriter.__module__ == expected_module
