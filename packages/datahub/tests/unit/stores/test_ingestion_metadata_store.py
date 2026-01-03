"""Tests for IngestionMetadataStore (deprecated component)."""

# ruff: noqa: E402  # 测试文件允许 warnings.filterwarnings 在 import 之前

import warnings

# Suppress deprecation warnings when testing deprecated components
warnings.filterwarnings("ignore", category=DeprecationWarning)

from pathlib import Path

import pytest
from ditto_datahub.sources.metadata import IngestionMetadata
from ditto_datahub.stores.ingestion_metadata_store import IngestionMetadataStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.fixture
def ingestion_metadata_store(
    sqlite_client: SQLiteClient, tmp_path: Path
) -> IngestionMetadataStore:
    """Provide IngestionMetadataStore with temporary database."""
    return IngestionMetadataStore(sqlite_client)


class TestIngestionMetadataStore:
    """Test cases for IngestionMetadataStore."""

    def test_get_metadata_returns_none_when_not_exists(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test get_metadata returns None for non-existent dataset."""
        metadata = ingestion_metadata_store.get_metadata("nonexistent", "tushare")
        assert metadata is None

    def test_save_and_get_metadata(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test saving and retrieving metadata."""
        original = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )

        ingestion_metadata_store.save_metadata(original)
        retrieved = ingestion_metadata_store.get_metadata("etf_daily", "tushare")

        assert retrieved is not None
        assert retrieved.dataset == "etf_daily"
        assert retrieved.source == "tushare"
        assert retrieved.last_trade_date == "2024-12-27"
        assert retrieved.last_checksum == "abc123"
        assert retrieved.last_rows == 5000
        assert retrieved.last_updated_at == "2024-12-27T18:00:00"

    def test_save_metadata_upserts_existing(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test save_metadata updates existing record."""
        original = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-26",
            last_checksum="old_hash",
            last_rows=3000,
            last_updated_at="2024-12-26T18:00:00",
        )

        ingestion_metadata_store.save_metadata(original)

        # Update with new data
        updated = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="new_hash",
            last_rows=6000,
            last_updated_at="2024-12-27T18:00:00",
        )

        ingestion_metadata_store.save_metadata(updated)
        retrieved = ingestion_metadata_store.get_metadata("stock_daily", "tushare")

        assert retrieved is not None
        assert retrieved.last_trade_date == "2024-12-27"
        assert retrieved.last_checksum == "new_hash"
        assert retrieved.last_rows == 6000

    def test_list_pending_datasets_with_no_data(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test list_pending_datasets returns empty when no metadata exists."""
        pending = ingestion_metadata_store.list_pending_datasets("2024-12-27")
        assert pending == []

    def test_list_pending_datasets_filters_by_date(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test list_pending_datasets filters datasets needing update."""
        # Save metadata for two datasets
        metadata1 = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-26",
            last_checksum="hash1",
            last_rows=5000,
            last_updated_at="2024-12-26T18:00:00",
        )

        metadata2 = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="hash2",
            last_rows=10000,
            last_updated_at="2024-12-27T18:00:00",
        )

        ingestion_metadata_store.save_metadata(metadata1)
        ingestion_metadata_store.save_metadata(metadata2)

        # List pending for 2024-12-27
        pending = ingestion_metadata_store.list_pending_datasets("2024-12-27")

        # Only etf_daily should be pending (last date is 2024-12-26)
        assert len(pending) == 1
        assert pending[0] == ("etf_daily", "tushare")

    def test_list_pending_datasets_with_none_date(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test list_pending_datasets includes datasets with None date."""
        metadata = IngestionMetadata(
            dataset="new_dataset",
            source="tushare",
            last_trade_date=None,
            last_checksum=None,
            last_rows=0,
            last_updated_at="2024-12-27T10:00:00",
        )

        ingestion_metadata_store.save_metadata(metadata)
        pending = ingestion_metadata_store.list_pending_datasets("2024-12-27")

        assert len(pending) == 1
        assert pending[0] == ("new_dataset", "tushare")

    def test_list_all_datasets(
        self, ingestion_metadata_store: IngestionMetadataStore
    ) -> None:
        """Test list_all_datasets returns all datasets."""
        metadata1 = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="hash1",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )

        metadata2 = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="hash2",
            last_rows=10000,
            last_updated_at="2024-12-27T18:00:00",
        )

        ingestion_metadata_store.save_metadata(metadata1)
        ingestion_metadata_store.save_metadata(metadata2)

        all_datasets = ingestion_metadata_store.list_all_datasets()

        assert len(all_datasets) == 2
        assert ("etf_daily", "tushare") in all_datasets
        assert ("stock_daily", "tushare") in all_datasets
