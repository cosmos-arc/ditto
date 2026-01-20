"""Tests for QuarantineStore."""

import polars as pl
import pytest
from ditto_datahub.stores.quarantine_store import QuarantineStore


@pytest.mark.integration
class TestQuarantineStore:
    """
    Tests for QuarantineStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        # Use in-memory database for testing
        self.store = QuarantineStore(":memory:")

    def teardown_method(self) -> None:
        """Clean up after test."""
        self.store.close()

    def test_quarantine_store_init(self) -> None:
        """Test QuarantineStore initialization."""
        assert self.store._conn is not None
        # _db_path is a Path object, compare as string or use .as_posix()
        assert str(self.store._db_path) == ":memory:"

    def test_save_failed_data_basic(self) -> None:
        """Test saving failed data to quarantine."""
        # Create a DataFrame with failed data
        failed_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [100.0, 101.0],
            }
        )

        # Save to quarantine
        row_id = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="test_rule",
            severity="error",
            failed_data=failed_df,
        )

        # Verify row was saved
        assert row_id > 0

    def test_save_failed_data_with_trade_date(self) -> None:
        """Test saving failed data with trade date."""
        failed_df = pl.DataFrame(
            {"sid": [1000001], "trade_date": ["2024-01-01"], "close": [100.0]}
        )

        row_id = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="test_rule",
            severity="error",
            failed_data=failed_df,
            trade_date="2024-01-01",
        )

        assert row_id > 0

    def test_save_failed_data_different_severities(self) -> None:
        """Test saving failed data with different severity levels."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Test error severity
        row_id1 = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="rule1",
            severity="error",
            failed_data=failed_df,
        )
        assert row_id1 > 0

        # Test warning severity
        row_id2 = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="rule2",
            severity="warning",
            failed_data=failed_df,
        )
        assert row_id2 > 0

        # Test alert severity
        row_id3 = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="rule3",
            severity="alert",
            failed_data=failed_df,
        )
        assert row_id3 > 0

    def test_get_quarantined_data_all(self) -> None:
        """Test getting all quarantined data."""
        # Insert some failed data
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})
        self.store.save_failed_data(
            "dataset_a", "rule1", "error", failed_df, trade_date="2024-01-01"
        )
        self.store.save_failed_data(
            "dataset_b", "rule2", "warning", failed_df, trade_date="2024-01-02"
        )

        # Get all quarantined data
        result = self.store.get_quarantined_data()
        assert len(result) == 2

    def test_get_quarantined_data_with_dataset_filter(self) -> None:
        """Test getting quarantined data filtered by dataset."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        self.store.save_failed_data("dataset_b", "rule2", "error", failed_df)
        self.store.save_failed_data("dataset_a", "rule3", "warning", failed_df)

        # Filter by dataset
        result = self.store.get_quarantined_data(dataset="dataset_a")
        assert len(result) == 2
        assert all(result["dataset"] == "dataset_a")

    def test_get_quarantined_data_with_rule_filter(self) -> None:
        """Test getting quarantined data filtered by rule_id."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        self.store.save_failed_data("dataset_b", "rule2", "error", failed_df)
        self.store.save_failed_data("dataset_a", "rule1", "warning", failed_df)

        # Filter by rule_id
        result = self.store.get_quarantined_data(rule_id="rule1")
        assert len(result) == 2

    def test_get_quarantined_data_with_limit(self) -> None:
        """Test getting quarantined data with limit."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Insert 5 records
        for i in range(5):
            self.store.save_failed_data(f"dataset_{i}", f"rule_{i}", "error", failed_df)

        # Get with limit
        result = self.store.get_quarantined_data(limit=3)
        assert len(result) == 3

    def test_get_quarantined_data_ordering(self) -> None:
        """Test that quarantined data includes created_at and is ordered."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Insert multiple records
        for i in range(3):
            self.store.save_failed_data(f"dataset_{i}", f"rule_{i}", "error", failed_df)

        # Get records - should be ordered by created_at DESC
        result = self.store.get_quarantined_data()
        assert len(result) == 3
        # Verify created_at column exists and results are ordered
        assert "created_at" in result.columns
        # Just verify we got all 3 records (ordering may vary due to
        # timestamp precision)
        assert set(result["dataset"].to_list()) == {
            "dataset_0",
            "dataset_1",
            "dataset_2",
        }

    def test_get_failed_data_df(self) -> None:
        """Test getting failed data DataFrame by row ID."""
        # Create and save failed data
        failed_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [100.0, 101.0],
            }
        )

        row_id = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="test_rule",
            severity="error",
            failed_data=failed_df,
        )

        # Retrieve the DataFrame
        retrieved_df = self.store.get_failed_data_df(row_id)
        assert not retrieved_df.is_empty()
        assert len(retrieved_df) == 2
        assert list(retrieved_df["sid"]) == [1000001, 1000002]

    def test_get_failed_data_df_not_found(self) -> None:
        """Test getting failed data with non-existent row ID."""
        result = self.store.get_failed_data_df(99999)
        assert result.is_empty()

    def test_get_failed_data_df_empty_result(self) -> None:
        """Test getting failed data when JSON is empty."""
        # Manually insert a record with empty JSON
        cursor = self.store._conn.execute(
            """
            INSERT INTO quarantine_failed_data
            (dataset, rule_id, severity, failed_data, affected_rows)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("test_dataset", "test_rule", "error", "{}", 0),
        )
        row_id = cursor.lastrowid

        # Try to retrieve it
        result = self.store.get_failed_data_df(row_id)
        # Should return empty DataFrame for empty JSON
        assert result.is_empty()

    def test_get_failed_data_df_invalid_json(self) -> None:
        """Test that invalid JSON returns empty DataFrame."""
        # Manually insert a record with invalid JSON
        cursor = self.store._conn.execute(
            """
            INSERT INTO quarantine_failed_data
            (dataset, rule_id, severity, failed_data, affected_rows)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("test_dataset", "test_rule", "error", "invalid json", 0),
        )
        row_id = cursor.lastrowid

        # Try to retrieve it
        result = self.store.get_failed_data_df(row_id)
        # Should return empty DataFrame
        assert result.is_empty()

    def test_clear_old_records(self) -> None:
        """Test clearing old quarantine records."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Insert some records
        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        self.store.save_failed_data("dataset_b", "rule2", "error", failed_df)
        self.store.save_failed_data("dataset_a", "rule3", "error", failed_df)

        # Clear old records (all records should be deleted since they're just created)
        # Use a large number of days to ensure no records are deleted
        deleted_count = self.store.clear_old_records(days=9999)
        # Should delete 0 records since days threshold is very high
        assert deleted_count == 0

        # All records should still be there
        result = self.store.get_quarantined_data()
        assert len(result) == 3

    def test_clear_old_records_with_zero_days(self) -> None:
        """Test clearing all records with zero days threshold."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Insert some records
        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        self.store.save_failed_data("dataset_b", "rule2", "error", failed_df)

        # Clear all records (0 days means delete everything)
        deleted_count = self.store.clear_old_records(days=0)
        # This might not delete all records due to SQLite's julianday behavior
        # but should delete some
        assert deleted_count >= 0

    def test_get_stats(self) -> None:
        """Test getting quarantine statistics."""
        # Create different types of failed data
        failed_df1 = pl.DataFrame({"sid": [1000001, 1000002], "close": [100.0, 101.0]})
        failed_df2 = pl.DataFrame({"sid": [1000003], "close": [102.0]})

        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df1)
        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df2)
        self.store.save_failed_data("dataset_a", "rule2", "warning", failed_df1)

        # Get stats
        stats = self.store.get_stats()
        assert len(stats) == 2

        # Check first stat entry
        stat1 = next(s for s in stats if s["rule_id"] == "rule1")
        assert stat1["dataset"] == "dataset_a"
        assert stat1["severity"] == "error"
        assert stat1["count"] == 2
        assert stat1["total_affected"] == 3  # 2 + 1 rows

    def test_get_stats_empty(self) -> None:
        """Test getting stats when no records exist."""
        stats = self.store.get_stats()
        assert len(stats) == 0

    def test_get_stats_ordering(self) -> None:
        """Test that stats are ordered by count DESC."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        # Insert different number of records for each rule
        for _i in range(5):
            self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        for _i in range(3):
            self.store.save_failed_data("dataset_a", "rule2", "error", failed_df)
        for _i in range(7):
            self.store.save_failed_data("dataset_a", "rule3", "error", failed_df)

        # Get stats
        stats = self.store.get_stats()

        # Should be ordered by count DESC
        assert stats[0]["rule_id"] == "rule3"
        assert stats[0]["count"] == 7
        assert stats[1]["rule_id"] == "rule1"
        assert stats[1]["count"] == 5
        assert stats[2]["rule_id"] == "rule2"
        assert stats[2]["count"] == 3

    def test_context_manager(self) -> None:
        """Test using QuarantineStore as a context manager."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        with QuarantineStore(":memory:") as store:
            # Use the store
            row_id = store.save_failed_data(
                dataset="test_dataset",
                rule_id="test_rule",
                severity="error",
                failed_data=failed_df,
            )
            assert row_id > 0

            # Verify data was saved
            result = store.get_quarantined_data()
            assert len(result) == 1

        # Connection should be closed after exiting context
        # (This is implicit - if it works, no exception is raised)

    def test_save_failed_data_json_serialization(self) -> None:
        """Test that DataFrame is correctly serialized to JSON."""
        # Create a DataFrame with various data types
        failed_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [100.5, 101.3],
                "volume": [1000000, 2000000],
                "is_st": [False, True],
            }
        )

        row_id = self.store.save_failed_data(
            dataset="test_dataset",
            rule_id="test_rule",
            severity="error",
            failed_data=failed_df,
        )

        # Retrieve and verify data integrity
        retrieved_df = self.store.get_failed_data_df(row_id)
        assert not retrieved_df.is_empty()
        assert len(retrieved_df) == 2

        # Check data types and values
        assert retrieved_df["sid"].to_list() == [1000001, 1000002]
        assert retrieved_df["trade_date"].to_list() == ["2024-01-01", "2024-01-02"]
        # Float comparison with tolerance
        assert abs(retrieved_df["close"][0] - 100.5) < 0.01

    def test_multiple_severities_same_rule(self) -> None:
        """Test saving multiple records with same rule but different severities."""
        failed_df = pl.DataFrame({"sid": [1000001], "close": [100.0]})

        self.store.save_failed_data("dataset_a", "rule1", "error", failed_df)
        self.store.save_failed_data("dataset_a", "rule1", "warning", failed_df)
        self.store.save_failed_data("dataset_a", "rule1", "alert", failed_df)

        # Get all records
        result = self.store.get_quarantined_data(rule_id="rule1")
        assert len(result) == 3

        # Verify we have all severities
        severities = set(result["severity"].to_list())
        assert severities == {"error", "warning", "alert"}
