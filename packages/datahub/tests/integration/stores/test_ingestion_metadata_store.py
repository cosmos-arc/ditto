"""Tests for IngestionMetadataStore (deprecated component)."""

# ruff: noqa: E402  # 测试文件允许 warnings.filterwarnings 在 import 之前

import warnings

# Suppress deprecation warnings when testing deprecated components
warnings.filterwarnings("ignore", category=DeprecationWarning)

from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.sources.metadata import IngestionMetadata
from ditto_datahub.stores.ingestion_metadata_store import IngestionMetadataStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestIngestionMetadataStore:
    """Test cases for IngestionMetadataStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # ruff: noqa: PLC0415  # 测试方法内导入
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.pool = SQLitePool(str(self.db_path))
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IngestionMetadataStore(self.client)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.pool.close()
        # Clean up temp directory
        # ruff: noqa: PLC0415  # 测试方法内导入
        import shutil

        shutil.rmtree(self.temp_dir.name, ignore_errors=True)

    def test_get_metadata_returns_none_when_not_exists(self) -> None:
        """Test get_metadata returns None for non-existent dataset."""
        metadata = self.store.get_metadata("nonexistent", "tushare")
        assert metadata is None

    def test_save_and_get_metadata(self) -> None:
        """Test saving and retrieving metadata."""
        original = IngestionMetadata(
            dataset="etf_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="abc123",
            last_rows=5000,
            last_updated_at="2024-12-27T18:00:00",
        )

        self.store.save_metadata(original)
        retrieved = self.store.get_metadata("etf_daily", "tushare")

        assert retrieved is not None
        assert retrieved.dataset == "etf_daily"
        assert retrieved.source == "tushare"
        assert retrieved.last_trade_date == "2024-12-27"
        assert retrieved.last_checksum == "abc123"
        assert retrieved.last_rows == 5000
        assert retrieved.last_updated_at == "2024-12-27T18:00:00"

    def test_save_metadata_upserts_existing(self) -> None:
        """Test save_metadata updates existing record."""
        original = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-26",
            last_checksum="old_hash",
            last_rows=3000,
            last_updated_at="2024-12-26T18:00:00",
        )

        self.store.save_metadata(original)

        # Update with new data
        updated = IngestionMetadata(
            dataset="stock_daily",
            source="tushare",
            last_trade_date="2024-12-27",
            last_checksum="new_hash",
            last_rows=6000,
            last_updated_at="2024-12-27T18:00:00",
        )

        self.store.save_metadata(updated)
        retrieved = self.store.get_metadata("stock_daily", "tushare")

        assert retrieved is not None
        assert retrieved.last_trade_date == "2024-12-27"
        assert retrieved.last_checksum == "new_hash"
        assert retrieved.last_rows == 6000

    def test_list_pending_datasets_with_no_data(self) -> None:
        """Test list_pending_datasets returns empty when no metadata exists."""
        pending = self.store.list_pending_datasets("2024-12-27")
        assert pending == []

    def test_list_pending_datasets_filters_by_date(self) -> None:
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

        self.store.save_metadata(metadata1)
        self.store.save_metadata(metadata2)

        # List pending for 2024-12-27
        pending = self.store.list_pending_datasets("2024-12-27")

        # Only etf_daily should be pending (last date is 2024-12-26)
        assert len(pending) == 1
        assert pending[0] == ("etf_daily", "tushare")

    def test_list_pending_datasets_with_none_date(self) -> None:
        """Test list_pending_datasets includes datasets with None date."""
        metadata = IngestionMetadata(
            dataset="new_dataset",
            source="tushare",
            last_trade_date=None,
            last_checksum=None,
            last_rows=0,
            last_updated_at="2024-12-27T10:00:00",
        )

        self.store.save_metadata(metadata)
        pending = self.store.list_pending_datasets("2024-12-27")

        assert len(pending) == 1
        assert pending[0] == ("new_dataset", "tushare")

    def test_list_all_datasets(self) -> None:
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

        self.store.save_metadata(metadata1)
        self.store.save_metadata(metadata2)

        all_datasets = self.store.list_all_datasets()

        assert len(all_datasets) == 2
        assert ("etf_daily", "tushare") in all_datasets
        assert ("stock_daily", "tushare") in all_datasets
