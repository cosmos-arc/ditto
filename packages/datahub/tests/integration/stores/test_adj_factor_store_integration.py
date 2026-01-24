"""Integration tests for AdjFactorStore (Parquet seam)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestAdjFactorStoreIntegration:
    """Tests for AdjFactorStore integration with Parquet files."""

    @pytest.fixture
    def data_root(self, tmp_path: Path) -> Path:
        """Create temporary data root directory."""
        return tmp_path / "data"

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool (required by infrastructure)."""
        return SQLitePool(db_path=":memory:")

    @pytest.fixture
    def store(self, data_root: Path, pool: SQLitePool) -> AdjFactorStore:
        """Create AdjFactorStore instance."""
        return AdjFactorStore(data_root=data_root)

    def test_write_creates_parquet_file(
        self, store: AdjFactorStore, data_root: Path
    ) -> None:
        """Test that write creates Parquet file."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "adj_factor": [1.0, 1.05],
            }
        )

        result = store.write("adj_factor", df, year=2024)

        # Verify file was created
        file_path = data_root / "adj_factor" / "2024.parquet"
        assert file_path.exists()

        # Verify result
        assert result.added == 2
        assert result.updated == 0
        assert result.file_path == str(file_path)
        assert len(result.checksum) > 0

    def test_write_empty_dataframe(self, store: AdjFactorStore) -> None:
        """Test writing empty DataFrame."""
        df = pl.DataFrame(schema={"sid": pl.Int32, "trade_date": pl.Date})

        result = store.write("adj_factor", df, year=2024)

        assert result.added == 0
        assert result.updated == 0
        assert result.file_path == ""
        assert result.checksum == ""

    def test_write_read_roundtrip(self, store: AdjFactorStore) -> None:
        """Test write and read roundtrip."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                ],
                "adj_factor": [1.0, 1.05, 1.0],
            }
        )

        # Write
        store.write("adj_factor", df, year=2024)

        # Read
        result = store.read("adj_factor")

        assert len(result) == 3
        assert result["sid"].to_list() == [1_000_001, 1_000_001, 1_000_002]

    def test_read_with_sid_filter(self, store: AdjFactorStore) -> None:
        """Test reading with SID filter."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_002, 1_000_003],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                ],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )

        store.write("adj_factor", df, year=2024)

        # Read with SID filter
        result = store.read("adj_factor", sids=[1_000_001, 1_000_002])

        assert len(result) == 2
        assert set(result["sid"].to_list()) == {1_000_001, 1_000_002}

    def test_read_with_date_filter(self, store: AdjFactorStore) -> None:
        """Test reading with date filter."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_001],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 15),
                    date(2024, 2, 1),
                ],
                "adj_factor": [1.0, 1.05, 1.1],
            }
        )

        store.write("adj_factor", df, year=2024)

        # Read with date range
        result = store.read(
            "adj_factor", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        assert result["trade_date"].max() == date(2024, 1, 15)

    def test_read_empty_dataset(self, store: AdjFactorStore) -> None:
        """Test reading from non-existent dataset."""
        result = store.read("nonexistent_dataset")
        assert result.is_empty()

    def test_write_with_keep_first_duplicate_strategy(
        self, store: AdjFactorStore
    ) -> None:
        """Test write with OnDuplicate.KEEP_FIRST."""
        # First write
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.0],
            }
        )
        store.write("adj_factor", df1, year=2024, on_duplicate=OnDuplicate.ERROR)

        # Second write with KEEP_FIRST (should keep original)
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.05],  # Different value
            }
        )
        result = store.write(
            "adj_factor", df2, year=2024, on_duplicate=OnDuplicate.KEEP_FIRST
        )

        assert result.added == 0
        assert result.updated == 0

        # Verify original value is kept
        read_result = store.read("adj_factor")
        assert read_result["adj_factor"][0] == 1.0

    def test_write_with_keep_last_duplicate_strategy(
        self, store: AdjFactorStore
    ) -> None:
        """Test write with OnDuplicate.KEEP_LAST."""
        # First write
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.0],
            }
        )
        store.write("adj_factor", df1, year=2024, on_duplicate=OnDuplicate.ERROR)

        # Second write with KEEP_LAST (should overwrite)
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.05],  # Different value
            }
        )
        result = store.write(
            "adj_factor", df2, year=2024, on_duplicate=OnDuplicate.KEEP_LAST
        )

        assert result.added == 0
        assert result.updated == 1

        # Verify new value is kept
        read_result = store.read("adj_factor")
        assert read_result["adj_factor"][0] == 1.05

    def test_write_with_error_duplicate_strategy_raises(
        self, store: AdjFactorStore
    ) -> None:
        """Test write with OnDuplicate.ERROR raises on duplicate."""
        # First write
        df1 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.0],
            }
        )
        store.write("adj_factor", df1, year=2024)

        # Second write with ERROR (should raise)
        df2 = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.05],
            }
        )

        with pytest.raises(ValueError) as exc_info:
            store.write("adj_factor", df2, year=2024, on_duplicate=OnDuplicate.ERROR)

        assert "Duplicate data" in str(exc_info.value)

    def test_write_removes_batch_duplicates(self, store: AdjFactorStore) -> None:
        """Test that write removes duplicates within batch."""
        # DataFrame with duplicate keys
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 1),  # Duplicate
                    date(2024, 1, 1),
                ],
                "adj_factor": [1.0, 1.05, 1.0],
            }
        )

        store.write("adj_factor", df, year=2024)

        # Should only have 2 unique records
        read_result = store.read("adj_factor")
        assert len(read_result) == 2

    def test_get_years(self, store: AdjFactorStore, data_root: Path) -> None:
        """Test getting available years."""
        # Create files for multiple years
        for year in [2022, 2023, 2024]:
            df = pl.DataFrame(
                {
                    "sid": [1_000_001],
                    "trade_date": [date(year, 1, 1)],
                    "adj_factor": [1.0],
                }
            )
            store.write("adj_factor", df, year=year)

        years = store.get_years("adj_factor")
        assert years == [2022, 2023, 2024]

    def test_get_checksum(self, store: AdjFactorStore) -> None:
        """Test getting checksum of year partition."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.0],
            }
        )

        store.write("adj_factor", df, year=2024)

        checksum = store.get_checksum("adj_factor", 2024)
        assert len(checksum) == 32  # MD5 hex string length

    def test_count(self, store: AdjFactorStore) -> None:
        """Test counting records."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                ],
                "adj_factor": [1.0, 1.05, 1.0],
            }
        )

        store.write("adj_factor", df, year=2024)

        # Count all
        count = store.count("adj_factor")
        assert count == 3

        # Count with SID filter
        count_filtered = store.count("adj_factor", sids=[1_000_001])
        assert count_filtered == 2

    def test_list_sids(self, store: AdjFactorStore) -> None:
        """Test listing unique SIDs."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_002, 1_000_002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "adj_factor": [1.0, 1.05, 1.0, 1.05],
            }
        )

        store.write("adj_factor", df, year=2024)

        sids = store.list_sids("adj_factor")
        assert sids == [1_000_001, 1_000_002]

    def test_delete(self, store: AdjFactorStore, data_root: Path) -> None:
        """Test deleting year partition."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.0],
            }
        )

        store.write("adj_factor", df, year=2024)

        # Delete
        deleted = store.delete("adj_factor", 2024)
        assert deleted is True

        # Verify file is gone
        file_path = data_root / "adj_factor" / "2024.parquet"
        assert not file_path.exists()

    def test_read_multiple_years(self, store: AdjFactorStore) -> None:
        """Test reading across multiple year partitions."""
        # Write data across 2 years
        for year in [2023, 2024]:
            df = pl.DataFrame(
                {
                    "sid": [1_000_001],
                    "trade_date": [date(year, 6, 1)],
                    "adj_factor": [1.0],
                }
            )
            store.write("adj_factor", df, year=year)

        # Read across both years
        result = store.read(
            "adj_factor", start_date="2023-01-01", end_date="2024-12-31"
        )

        assert len(result) == 2

    def test_get_date_range(self, store: AdjFactorStore) -> None:
        """Test getting date range."""
        df = pl.DataFrame(
            {
                "sid": [1_000_001, 1_000_001, 1_000_001],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 6, 15),
                    date(2024, 12, 31),
                ],
                "adj_factor": [1.0, 1.05, 1.1],
            }
        )

        store.write("adj_factor", df, year=2024)

        start_date, end_date = store.get_date_range("adj_factor")
        assert start_date == "2024-01-01"
        assert end_date == "2024-12-31"
