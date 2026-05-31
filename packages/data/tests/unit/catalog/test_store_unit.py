"""Unit tests for InMemoryDataCatalog."""

from datetime import UTC, datetime

from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
)
from ditto_data.catalog.store import InMemoryDataCatalog


def _make_entry(
    dataset_id: str = "test_dataset",
    namespace: str = "test",
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(dataset_id=dataset_id, namespace=namespace),
        storage_uri=f"file:///data/{namespace}/{dataset_id}",
        schema=DataSchemaFingerprint(schema_hash="abc123", row_count=100),
        source="tushare",
        freshness_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestInMemoryDataCatalogUpsertAndGet:
    def test_upsert_and_get(self) -> None:
        catalog = InMemoryDataCatalog()
        entry = _make_entry()

        catalog.upsert_asset(entry)
        result = catalog.get_asset(entry.asset)

        assert result is not None
        assert result.asset.dataset_id == "test_dataset"
        assert result.source == "tushare"

    def test_get_nonexistent_returns_none(self) -> None:
        catalog = InMemoryDataCatalog()
        ref = DataAssetRef(dataset_id="missing", namespace="test")

        assert catalog.get_asset(ref) is None

    def test_upsert_updates_existing(self) -> None:
        catalog = InMemoryDataCatalog()
        ref = DataAssetRef(dataset_id="ds", namespace="ns")
        entry_v1 = DataCatalogEntry(
            asset=ref,
            storage_uri="v1",
            schema=DataSchemaFingerprint(schema_hash="h1"),
            source="src",
            freshness_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        entry_v2 = DataCatalogEntry(
            asset=ref,
            storage_uri="v2",
            schema=DataSchemaFingerprint(schema_hash="h2"),
            source="src",
            freshness_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

        catalog.upsert_asset(entry_v1)
        catalog.upsert_asset(entry_v2)

        result = catalog.get_asset(ref)
        assert result is not None
        assert result.storage_uri == "v2"
        assert result.schema.schema_hash == "h2"


class TestInMemoryDataCatalogList:
    def test_list_assets_all(self) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(_make_entry("ds1", "ns_a"))
        catalog.upsert_asset(_make_entry("ds2", "ns_b"))

        result = catalog.list_assets()

        assert len(result) == 2

    def test_list_assets_by_namespace(self) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(_make_entry("ds1", "ns_a"))
        catalog.upsert_asset(_make_entry("ds2", "ns_b"))
        catalog.upsert_asset(_make_entry("ds3", "ns_a"))

        result = catalog.list_assets(namespace="ns_a")

        assert len(result) == 2
        assert all(e.asset.namespace == "ns_a" for e in result)

    def test_list_assets_empty(self) -> None:
        catalog = InMemoryDataCatalog()

        result = catalog.list_assets()

        assert result == ()


class TestInMemoryDataCatalogProtocols:
    def test_isinstance_reader(self) -> None:
        catalog = InMemoryDataCatalog()
        assert isinstance(catalog, DataCatalogReader)

    def test_isinstance_writer(self) -> None:
        catalog = InMemoryDataCatalog()
        assert isinstance(catalog, DataCatalogWriter)
