"""Tests for QuarantineStore."""

import tempfile
from pathlib import Path

import polars as pl
from ditto_datahub.stores.quarantine_store import QuarantineStore


class TestQuarantineStore:
    """Test cases for QuarantineStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Use in-memory database for testing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as db:
            self.temp_db = db
        self.temp_db.close()
        self.store = QuarantineStore(self.temp_db.name)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.store.close()
        Path(self.temp_db.name).unlink(missing_ok=True)

    def test_init_creates_table(self) -> None:
        """Test initialization creates quarantine table."""
        # Query table schema
        cursor = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='quarantine_failed_data'"
        )
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == "quarantine_failed_data"

    def test_save_and_get_quarantined_data(self) -> None:
        """Test saving and retrieving quarantined data."""
        df = pl.DataFrame(
            {
                "sid": [1, 2, 3],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0, 30.0],
            }
        )

        row_id = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="not_null",
            severity="error",
            failed_data=df,
            trade_date="2024-01-01",
        )

        assert row_id > 0

        # Get quarantined data
        result = self.store.get_quarantined_data(dataset="test_dataset")

        assert result.height == 1
        assert result[0, "dataset"] == "test_dataset"
        assert result[0, "rule_id"] == "not_null"
        assert result[0, "severity"] == "error"
        assert result[0, "affected_rows"] == 3

    def test_get_failed_data_df(self) -> None:
        """Test retrieving failed data as DataFrame."""
        df = pl.DataFrame(
            {
                "sid": [1, 2],
                "value": [100, 200],
            }
        )

        row_id = self.store.save_failed_data(
            dataset="test",
            rule_id="unique",
            severity="error",
            failed_data=df,
        )

        # Get back the DataFrame
        retrieved_df = self.store.get_failed_data_df(row_id)

        assert retrieved_df is not None
        assert retrieved_df.height == 2
        assert list(retrieved_df.columns) == ["sid", "value"]

    def test_filter_by_dataset_and_rule(self) -> None:
        """Test filtering by dataset and rule."""
        df1 = pl.DataFrame({"sid": [1]})
        df2 = pl.DataFrame({"sid": [2]})

        self.store.save_failed_data("dataset_a", "rule_1", "error", df1)
        self.store.save_failed_data("dataset_a", "rule_2", "warning", df2)
        self.store.save_failed_data("dataset_b", "rule_1", "error", df1)

        # Filter by dataset
        result = self.store.get_quarantined_data(dataset="dataset_a")
        assert result.height == 2

        # Filter by both
        result = self.store.get_quarantined_data(dataset="dataset_a", rule_id="rule_1")
        assert result.height == 1

    def test_clear_old_records(self) -> None:
        """Test clearing old records."""
        df = pl.DataFrame({"sid": [1]})

        # Save some records
        self.store.save_failed_data("test", "rule_1", "error", df)
        self.store.save_failed_data("test", "rule_2", "error", df)

        # Clear old records (0 days = all)
        deleted_count = self.store.clear_old_records(days=0)

        assert deleted_count == 2

        # Verify no records left
        result = self.store.get_quarantined_data()
        assert result.height == 0

    def test_get_stats(self) -> None:
        """Test getting quarantine statistics."""
        df = pl.DataFrame({"sid": [1, 2, 3]})

        self.store.save_failed_data("dataset_a", "rule_1", "error", df)
        self.store.save_failed_data("dataset_a", "rule_1", "error", df)
        self.store.save_failed_data("dataset_b", "rule_2", "warning", df)

        stats = self.store.get_stats()

        assert len(stats) > 0
        # Should have stats for dataset_a/rule_1/error
        stat_a = next(s for s in stats if s["dataset"] == "dataset_a")
        assert stat_a["count"] == 2
        assert stat_a["total_affected"] == 6

    def test_context_manager(self) -> None:
        """Test using store as context manager."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as db_path:
            pass
        db_path.close()

        with QuarantineStore(db_path.name) as store:
            df = pl.DataFrame({"sid": [1]})
            store.save_failed_data("test", "rule", "error", df)

        # Connection should be closed after context
        # Verify we can reopen and read data
        with QuarantineStore(db_path.name) as store:
            result = store.get_quarantined_data()
            assert result.height == 1

        Path(db_path.name).unlink()
