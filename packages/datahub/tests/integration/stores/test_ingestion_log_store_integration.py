"""Integration tests for IngestionLogStore (SQLite seam)."""

import pytest
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.mark.integration
class TestIngestionLogStoreIntegration:
    """Tests for IngestionLogStore integration with SQLite."""

    @pytest.fixture
    def pool(self) -> SQLitePool:
        """Create in-memory SQLite pool for testing."""
        return SQLitePool(connection_string="file::memory:?cache=shared", pool_size=1)

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
        """Create SQLite client."""
        return SQLiteClient(pool)

    @pytest.fixture
    def store(self, client: SQLiteClient) -> IngestionLogStore:
        """Create IngestionLogStore instance."""
        # Note: IngestionLogStore creates tables in __init__
        return IngestionLogStore(client)

    def test_save_and_get_log(self, store: IngestionLogStore) -> None:
        """Test saving and retrieving an ingestion log."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=5000,
        )

        saved_log = store.save_log(log)

        # Verify saved log has timestamps and attempts
        assert saved_log.attempts == 1
        assert saved_log.first_attempt_at is not None
        assert saved_log.last_attempt_at is not None

        # Retrieve log
        retrieved = store.get_log("stock_daily", "tushare", "2024-01-01")
        assert retrieved is not None
        assert retrieved.dataset == "stock_daily"
        assert retrieved.status == IngestionStatus.SUCCESS
        assert retrieved.rows == 5000

    def test_save_log_upsert_increments_attempts(
        self, store: IngestionLogStore
    ) -> None:
        """Test that saving same log increments attempts."""
        log1 = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.FAIL,
            error_code="NETWORK_ERROR",
            error_message="Connection timeout",
        )

        saved1 = store.save_log(log1)
        assert saved1.attempts == 1

        # Save again (simulate retry)
        log2 = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.SUCCESS,
            checksum="def456",
            rows=5000,
        )

        saved2 = store.save_log(log2)
        assert saved2.attempts == 2
        assert saved2.status == IngestionStatus.SUCCESS

    def test_get_log_not_found(self, store: IngestionLogStore) -> None:
        """Test getting non-existent log returns None."""
        log = store.get_log("stock_daily", "tushare", "2099-01-01")
        assert log is None

    def test_get_failed_dates(self, store: IngestionLogStore) -> None:
        """Test getting failed trade dates."""
        # Save some logs
        for date, status in [
            ("2024-01-01", IngestionStatus.SUCCESS),
            ("2024-01-02", IngestionStatus.FAIL),
            ("2024-01-03", IngestionStatus.FAIL),
            ("2024-01-04", IngestionStatus.SUCCESS),
        ]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=status,
                error_code="ERROR" if status == IngestionStatus.FAIL else None,
                error_message="Test error" if status == IngestionStatus.FAIL else None,
            )
            store.save_log(log)

        # Get failed dates
        failed_dates = store.get_failed_dates("stock_daily", "tushare", limit=10)
        assert len(failed_dates) == 2
        assert failed_dates == ["2024-01-02", "2024-01-03"]

    def test_get_failed_dates_respects_max_attempts(
        self, store: IngestionLogStore
    ) -> None:
        """Test that get_failed_dates respects max_attempts."""
        # Create failed log with 3 attempts
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.FAIL,
        )

        # Simulate 3 attempts by saving 3 times
        store.save_log(log)
        store.save_log(log)
        saved = store.save_log(log)

        assert saved.attempts == 3

        # Should not return dates with >= 3 attempts
        failed_dates = store.get_failed_dates("stock_daily", "tushare", max_attempts=3)
        assert len(failed_dates) == 0

    def test_get_success_rate(self, store: IngestionLogStore) -> None:
        """Test calculating success rate."""
        # Save mixed logs
        for i in range(10):
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=f"2024-01-{i + 1:02d}",
                status=IngestionStatus.SUCCESS if i < 8 else IngestionStatus.FAIL,
                checksum="abc" if i < 8 else None,
                rows=1000 if i < 8 else None,
            )
            store.save_log(log)

        # Get success rate
        rate = store.get_success_rate("stock_daily", "tushare")
        assert rate == 0.8  # 8 out of 10

    def test_get_success_rate_with_start_date(self, store: IngestionLogStore) -> None:
        """Test success rate with start date filter."""
        # Save logs
        for date in ["2024-01-01", "2024-01-02", "2024-02-01"]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=IngestionStatus.SUCCESS,
                checksum="abc",
                rows=1000,
            )
            store.save_log(log)

        # Get success rate from February onwards
        rate = store.get_success_rate("stock_daily", "tushare", start_date="2024-02-01")
        assert rate == 1.0  # Only one record

    def test_get_success_rate_empty_dataset(self, store: IngestionLogStore) -> None:
        """Test success rate for empty dataset."""
        rate = store.get_success_rate("nonexistent_dataset", "tushare")
        assert rate == 0.0

    def test_get_stats(self, store: IngestionLogStore) -> None:
        """Test getting ingestion statistics."""
        # Save logs
        for i in range(5):
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=f"2024-01-0{i + 1}",
                status=IngestionStatus.SUCCESS if i < 3 else IngestionStatus.FAIL,
            )
            store.save_log(log)

        # Get stats
        stats = store.get_stats("stock_daily", "tushare")
        assert stats["success_count"] == 3
        assert stats["fail_count"] == 2
        assert stats["total_count"] == 5

    def test_get_ingested_dates(self, store: IngestionLogStore) -> None:
        """Test getting all ingested dates."""
        # Save logs
        for date in ["2024-01-01", "2024-01-02", "2024-01-03"]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=IngestionStatus.SUCCESS,
                checksum="abc",
                rows=1000,
            )
            store.save_log(log)

        # Get all dates
        dates = store.get_ingested_dates("stock_daily", "tushare")
        assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]

    def test_get_ingested_dates_with_status_filter(
        self, store: IngestionLogStore
    ) -> None:
        """Test getting ingested dates with status filter."""
        # Save mixed logs
        for date, status in [
            ("2024-01-01", IngestionStatus.SUCCESS),
            ("2024-01-02", IngestionStatus.FAIL),
            ("2024-01-03", IngestionStatus.SUCCESS),
        ]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=status,
            )
            store.save_log(log)

        # Get only successful dates
        success_dates = store.get_ingested_dates(
            "stock_daily", "tushare", status=IngestionStatus.SUCCESS
        )
        assert success_dates == ["2024-01-01", "2024-01-03"]

        # Get only failed dates
        fail_dates = store.get_ingested_dates(
            "stock_daily", "tushare", status=IngestionStatus.FAIL
        )
        assert fail_dates == ["2024-01-02"]

    def test_get_failed_logs(self, store: IngestionLogStore) -> None:
        """Test getting failed logs."""
        # Save logs
        for date in ["2024-01-01", "2024-01-02", "2024-01-03"]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=IngestionStatus.FAIL,
                error_code="ERROR",
                error_message=f"Error on {date}",
            )
            store.save_log(log)

        # Get failed logs
        failed_logs = store.get_failed_logs("stock_daily", "tushare", limit=10)
        assert len(failed_logs) == 3
        assert all(log.status == IngestionStatus.FAIL for log in failed_logs)

    def test_get_last_success_date(self, store: IngestionLogStore) -> None:
        """Test getting last success date."""
        # Save logs
        for date in ["2024-01-01", "2024-01-05", "2024-01-03"]:
            log = IngestionLog(
                dataset="stock_daily",
                source="tushare",
                trade_date=date,
                status=IngestionStatus.SUCCESS,
                checksum="abc",
                rows=1000,
            )
            store.save_log(log)

        # Get last success date
        last_date = store.get_last_success_date("stock_daily", "tushare")
        assert last_date == "2024-01-05"

    def test_get_last_success_date_no_success(self, store: IngestionLogStore) -> None:
        """Test getting last success date when no successes."""
        # Save only failed logs
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-01",
            status=IngestionStatus.FAIL,
        )
        store.save_log(log)

        last_date = store.get_last_success_date("stock_daily", "tushare")
        assert last_date is None

    def test_row_to_log_conversion(self, store: IngestionLogStore) -> None:
        """Test _row_to_log conversion."""
        row = {
            "dataset": "stock_daily",
            "source": "tushare",
            "trade_date": "2024-01-01",
            "status": "SUCCESS",
            "checksum": "abc123",
            "rows": 5000,
            "error_code": None,
            "error_message": None,
            "attempts": 1,
            "first_attempt_at": "2024-01-01T00:00:00",
            "last_attempt_at": "2024-01-01T00:00:00",
        }

        log = store._row_to_log(row)
        assert log.dataset == "stock_daily"
        assert log.status == IngestionStatus.SUCCESS
        assert log.attempts == 1
