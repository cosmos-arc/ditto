"""Tests for IngestionLogStore."""

import pytest
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestIngestionLogStore:
    """
    Tests for IngestionLogStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        # Create in-memory database for testing
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IngestionLogStore(self.client)

    def test_ingestion_log_store_init(self) -> None:
        """Test IngestionLogStore initialization."""
        assert self.store._client is not None

    def test_save_log_success(self) -> None:
        """Test saving successful ingestion log."""
        log = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
                checksum="abc123",
                rows=1000,
            )
        )

        assert log.dataset == "test_dataset"
        assert log.source == "tushare"
        assert log.trade_date == "2024-01-01"
        assert log.status == IngestionStatus.SUCCESS
        assert log.checksum == "abc123"
        assert log.rows == 1000
        assert log.attempts == 1
        assert log.first_attempt_at is not None
        assert log.last_attempt_at is not None

    def test_save_log_failure(self) -> None:
        """Test saving failed ingestion log."""
        log = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="NETWORK_ERROR",
                error_message="Connection failed",
            )
        )

        assert log.status == IngestionStatus.FAIL
        assert log.error_code == "NETWORK_ERROR"
        assert log.error_message == "Connection failed"
        assert log.attempts == 1

    def test_save_log_update_existing(self) -> None:
        """Test updating existing log record."""
        # First save
        log1 = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="ERROR1",
            )
        )

        # Update with new status (error_code becomes None for success)
        log2 = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
                checksum="abc123",
                rows=1000,
            )
        )

        # Verify attempts incremented
        assert log2.attempts == 2
        assert log2.first_attempt_at == log1.first_attempt_at
        # last_attempt_at should be updated (may be same timestamp if quick)
        assert log2.last_attempt_at is not None
        assert log2.status == IngestionStatus.SUCCESS
        assert log2.checksum == "abc123"
        # error_code should be None for success status
        assert log2.error_code is None

    def test_save_log_multiple_retries(self) -> None:
        """Test multiple retry attempts."""
        # First attempt
        log1 = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="ERROR1",
            )
        )

        # Second attempt
        log2 = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="ERROR2",
            )
        )

        # Third attempt - success
        log3 = self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
                checksum="final",
                rows=1000,
            )
        )

        assert log1.attempts == 1
        assert log2.attempts == 2
        assert log3.attempts == 3
        # When status is SUCCESS, error_code becomes None
        assert log3.error_code is None

    def test_get_log(self) -> None:
        """Test getting ingestion log."""
        # Save a log
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
                checksum="abc123",
                rows=1000,
            )
        )

        # Retrieve it
        log = self.store.get_log(
            dataset="test_dataset", source="tushare", trade_date="2024-01-01"
        )

        assert log is not None
        assert log.dataset == "test_dataset"
        assert log.source == "tushare"
        assert log.trade_date == "2024-01-01"
        assert log.status == IngestionStatus.SUCCESS

    def test_get_log_not_found(self) -> None:
        """Test getting non-existent log returns None."""
        log = self.store.get_log(
            dataset="nonexistent", source="tushare", trade_date="2024-01-01"
        )
        assert log is None

    def test_get_failed_dates(self) -> None:
        """Test getting failed trade dates."""
        # Insert some failed logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="E1",
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
                error_code="E2",
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.FAIL,
                error_code="E3",
            )
        )

        # Get failed dates
        failed_dates = self.store.get_failed_dates(
            dataset="test_dataset", source="tushare"
        )

        assert len(failed_dates) == 3
        assert "2024-01-01" in failed_dates
        assert "2024-01-02" in failed_dates
        assert "2024-01-04" in failed_dates
        assert "2024-01-03" not in failed_dates

    def test_get_failed_dates_with_max_attempts(self) -> None:
        """Test getting failed dates filtered by max attempts."""
        # Insert logs with different attempt counts
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )  # 2 attempts
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )  # 3 attempts

        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )

        # Get failed dates with max_attempts=2
        failed_dates = self.store.get_failed_dates(
            dataset="test_dataset", source="tushare", max_attempts=2
        )

        # Only 2024-01-02 should be returned (1 attempt < 2)
        assert len(failed_dates) == 1
        assert failed_dates[0] == "2024-01-02"

    def test_get_failed_dates_with_limit(self) -> None:
        """Test getting failed dates with limit."""
        # Insert multiple failed logs
        for i in range(5):
            self.store.save_log(
                IngestionLog(
                    dataset="test_dataset",
                    source="tushare",
                    trade_date=f"2024-01-0{i + 1}",
                    status=IngestionStatus.FAIL,
                )
            )

        # Get with limit
        failed_dates = self.store.get_failed_dates(
            dataset="test_dataset", source="tushare", limit=3
        )

        assert len(failed_dates) == 3

    def test_get_success_rate(self) -> None:
        """Test calculating success rate."""
        # Insert mixed logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-05",
                status=IngestionStatus.FAIL,
            )
        )

        # Get success rate
        rate = self.store.get_success_rate(dataset="test_dataset", source="tushare")

        # 3 success out of 5 = 0.6
        assert abs(rate - 0.6) < 0.01

    def test_get_success_rate_with_start_date(self) -> None:
        """Test calculating success rate with start date filter."""
        # Insert logs for different dates
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get success rate from 2024-01-03 onwards
        rate = self.store.get_success_rate(
            dataset="test_dataset", source="tushare", start_date="2024-01-03"
        )

        # 2 success out of 2 = 1.0
        assert rate == 1.0

    def test_get_success_rate_no_records(self) -> None:
        """Test success rate when no records exist."""
        rate = self.store.get_success_rate(dataset="nonexistent", source="tushare")
        assert rate == 0.0

    def test_get_stats(self) -> None:
        """Test getting ingestion statistics."""
        # Insert mixed logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-05",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get stats
        stats = self.store.get_stats(dataset="test_dataset", source="tushare")

        assert stats["success_count"] == 3
        assert stats["fail_count"] == 2
        assert stats["total_count"] == 5

    def test_get_stats_no_records(self) -> None:
        """Test getting stats when no records exist."""
        stats = self.store.get_stats(dataset="nonexistent", source="tushare")

        assert stats["success_count"] == 0
        assert stats["fail_count"] == 0
        assert stats["total_count"] == 0

    def test_get_ingested_dates_all(self) -> None:
        """Test getting all ingested dates."""
        # Insert logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get all dates
        dates = self.store.get_ingested_dates(dataset="test_dataset", source="tushare")

        assert len(dates) == 3
        assert "2024-01-01" in dates
        assert "2024-01-02" in dates
        assert "2024-01-03" in dates

    def test_get_ingested_dates_with_status_filter(self) -> None:
        """Test getting ingested dates filtered by status."""
        # Insert mixed logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.FAIL,
            )
        )

        # Get only successful dates
        success_dates = self.store.get_ingested_dates(
            dataset="test_dataset", source="tushare", status=IngestionStatus.SUCCESS
        )

        assert len(success_dates) == 2
        assert "2024-01-01" in success_dates
        assert "2024-01-03" in success_dates

        # Get only failed dates
        fail_dates = self.store.get_ingested_dates(
            dataset="test_dataset", source="tushare", status=IngestionStatus.FAIL
        )

        assert len(fail_dates) == 2
        assert "2024-01-02" in fail_dates
        assert "2024-01-04" in fail_dates

    def test_get_ingested_dates_ordering(self) -> None:
        """Test that ingested dates are ordered ASC."""
        # Insert logs in random order
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-05",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get dates - should be ordered ASC
        dates = self.store.get_ingested_dates(dataset="test_dataset", source="tushare")

        assert dates == [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
        ]

    def test_get_failed_logs(self) -> None:
        """Test getting failed ingestion logs."""
        # Insert failed logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
                error_code="E1",
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
                error_code="E2",
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get failed logs
        failed_logs = self.store.get_failed_logs(
            dataset="test_dataset", source="tushare"
        )

        assert len(failed_logs) == 2
        assert all(log.status == IngestionStatus.FAIL for log in failed_logs)
        assert failed_logs[0].error_code == "E1"
        assert failed_logs[1].error_code == "E2"

    def test_get_failed_logs_with_max_attempts(self) -> None:
        """Test getting failed logs filtered by max attempts."""
        # Insert log with multiple attempts
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )  # 2 attempts
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )  # 3 attempts

        # Get failed logs with max_attempts=2
        failed_logs = self.store.get_failed_logs(
            dataset="test_dataset", source="tushare", max_attempts=2
        )

        # Should return empty because all attempts >= 2
        assert len(failed_logs) == 0

    def test_get_failed_logs_with_limit(self) -> None:
        """Test getting failed logs with limit."""
        # Insert multiple failed logs
        for i in range(5):
            self.store.save_log(
                IngestionLog(
                    dataset="test_dataset",
                    source="tushare",
                    trade_date=f"2024-01-0{i + 1}",
                    status=IngestionStatus.FAIL,
                )
            )

        # Get with limit
        failed_logs = self.store.get_failed_logs(
            dataset="test_dataset", source="tushare", limit=3
        )

        assert len(failed_logs) == 3

    def test_different_sources(self) -> None:
        """Test handling logs from different sources."""
        # Insert logs from different sources
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="eastmoney",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get tushare logs
        tushare_dates = self.store.get_ingested_dates(
            dataset="test_dataset", source="tushare"
        )
        assert len(tushare_dates) == 2

        # Get eastmoney logs
        eastmoney_dates = self.store.get_ingested_dates(
            dataset="test_dataset", source="eastmoney"
        )
        assert len(eastmoney_dates) == 1

    def test_get_last_success_date(self) -> None:
        """Test getting last successful trade date."""
        # Insert logs with different dates and statuses
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-03",
                status=IngestionStatus.SUCCESS,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-04",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-05",
                status=IngestionStatus.SUCCESS,
            )
        )

        # Get last success date
        last_success = self.store.get_last_success_date(
            dataset="test_dataset", source="tushare"
        )

        # Should return 2024-01-05 (last SUCCESS)
        assert last_success == "2024-01-05"

    def test_get_last_success_date_no_records(self) -> None:
        """Test getting last success date when no records exist."""
        last_success = self.store.get_last_success_date(
            dataset="nonexistent", source="tushare"
        )
        assert last_success is None

    def test_get_last_success_date_no_success_records(self) -> None:
        """Test getting last success date when only FAIL records exist."""
        # Insert only FAIL logs
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-01",
                status=IngestionStatus.FAIL,
            )
        )
        self.store.save_log(
            IngestionLog(
                dataset="test_dataset",
                source="tushare",
                trade_date="2024-01-02",
                status=IngestionStatus.FAIL,
            )
        )

        # Get last success date
        last_success = self.store.get_last_success_date(
            dataset="test_dataset", source="tushare"
        )

        # Should return None (no SUCCESS records)
        assert last_success is None

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
