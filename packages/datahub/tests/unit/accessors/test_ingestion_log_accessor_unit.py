"""Tests for IngestionLogAccessor."""

from unittest.mock import MagicMock

from ditto_datahub.accessors.ingestion_log import IngestionLogAccessor
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.stores.ingestion_log import IngestionLogStore


class TestIngestionLogAccessor:
    """Tests for IngestionLogAccessor."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_store = MagicMock(spec=IngestionLogStore)
        self.accessor = IngestionLogAccessor(self.mock_store)

    def test_init(self) -> None:
        """Test initialization."""
        assert self.accessor._store is self.mock_store

    def test_save_log_success(self) -> None:
        """Test save_log with successful ingestion."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )

        expected_result = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
            attempts=1,
            first_attempt_at="2024-01-02T10:00:00",
            last_attempt_at="2024-01-02T10:00:00",
        )
        self.mock_store.save_log.return_value = expected_result

        result = self.accessor.save_log(log)

        assert result == expected_result
        self.mock_store.save_log.assert_called_once_with(log)

    def test_save_log_failure(self) -> None:
        """Test save_log with failed ingestion."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )

        expected_result = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
            attempts=2,
            first_attempt_at="2024-01-02T10:00:00",
            last_attempt_at="2024-01-02T11:00:00",
        )
        self.mock_store.save_log.return_value = expected_result

        result = self.accessor.save_log(log)

        assert result == expected_result
        self.mock_store.save_log.assert_called_once_with(log)

    def test_get_log_found(self) -> None:
        """Test get_log when log exists."""
        expected_log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        self.mock_store.get_log.return_value = expected_log

        result = self.accessor.get_log("stock_daily", "tushare", "2024-01-02")

        assert result == expected_log
        self.mock_store.get_log.assert_called_once_with(
            "stock_daily", "tushare", "2024-01-02"
        )

    def test_get_log_not_found(self) -> None:
        """Test get_log when log does not exist."""
        self.mock_store.get_log.return_value = None

        result = self.accessor.get_log("stock_daily", "tushare", "2024-01-02")

        assert result is None
        self.mock_store.get_log.assert_called_once_with(
            "stock_daily", "tushare", "2024-01-02"
        )

    def test_get_failed_dates(self) -> None:
        """Test get_failed_dates."""
        expected_dates = ["2024-01-02", "2024-01-03", "2024-01-05"]
        self.mock_store.get_failed_dates.return_value = expected_dates

        result = self.accessor.get_failed_dates(
            dataset="stock_daily", source="tushare", limit=10, max_attempts=3
        )

        assert result == expected_dates
        self.mock_store.get_failed_dates.assert_called_once_with(
            "stock_daily", "tushare", 10, 3
        )

    def test_get_failed_dates_with_defaults(self) -> None:
        """Test get_failed_dates with default parameters."""
        expected_dates = ["2024-01-02"]
        self.mock_store.get_failed_dates.return_value = expected_dates

        result = self.accessor.get_failed_dates("stock_daily", "tushare")

        assert result == expected_dates
        self.mock_store.get_failed_dates.assert_called_once_with(
            "stock_daily", "tushare", 10, 3
        )

    def test_get_ingested_dates(self) -> None:
        """Test get_ingested_dates."""
        expected_dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        self.mock_store.get_ingested_dates.return_value = expected_dates

        result = self.accessor.get_ingested_dates("stock_daily", "tushare")

        assert result == expected_dates
        self.mock_store.get_ingested_dates.assert_called_once_with(
            "stock_daily", "tushare"
        )

    def test_get_stats(self) -> None:
        """Test get_stats."""
        expected_stats = {
            "success_count": 95,
            "fail_count": 5,
            "total_count": 100,
        }
        self.mock_store.get_stats.return_value = expected_stats

        result = self.accessor.get_stats("stock_daily", "tushare")

        assert result == expected_stats
        self.mock_store.get_stats.assert_called_once_with("stock_daily", "tushare")

    def test_get_last_success_date_found(self) -> None:
        """Test get_last_success_date when success date exists."""
        expected_date = "2024-01-15"
        self.mock_store.get_last_success_date.return_value = expected_date

        result = self.accessor.get_last_success_date("stock_daily", "tushare")

        assert result == expected_date
        self.mock_store.get_last_success_date.assert_called_once_with(
            "stock_daily", "tushare"
        )

    def test_get_last_success_date_not_found(self) -> None:
        """Test get_last_success_date when no success date exists."""
        self.mock_store.get_last_success_date.return_value = None

        result = self.accessor.get_last_success_date("stock_daily", "tushare")

        assert result is None
        self.mock_store.get_last_success_date.assert_called_once_with(
            "stock_daily", "tushare"
        )
