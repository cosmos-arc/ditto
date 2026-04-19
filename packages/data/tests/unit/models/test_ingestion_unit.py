"""Unit tests for Models - ingestion."""

import dataclasses

import pytest
from ditto_data.errors import DataChangedError, NotTradingDayError
from ditto_data.models.ingestion import (
    IngestionCursor,
    IngestionLog,
    IngestionStatus,
)


@pytest.mark.unit
class TestIngestionStatus:
    """Tests for IngestionStatus enum."""

    def test_success_enum_value(self) -> None:
        """Test SUCCESS enum has correct value."""
        assert IngestionStatus.SUCCESS == "SUCCESS"

    def test_fail_enum_value(self) -> None:
        """Test FAIL enum has correct value."""
        assert IngestionStatus.FAIL == "FAIL"

    def test_has_two_members(self) -> None:
        """Test IngestionStatus has exactly two members."""
        assert len(IngestionStatus) == 2

    def test_is_string_enum(self) -> None:
        """Test IngestionStatus is a string enum."""
        assert isinstance(IngestionStatus.SUCCESS.value, str)
        assert isinstance(IngestionStatus.FAIL.value, str)


@pytest.mark.unit
class TestIngestionLog:
    """Tests for IngestionLog dataclass."""

    def test_create_success_log(self) -> None:
        """Test creating a success ingestion log."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )

        assert log.dataset == "stock_daily"
        assert log.source == "tushare"
        assert log.trade_date == "2024-01-02"
        assert log.status == IngestionStatus.SUCCESS
        assert log.checksum == "abc123"
        assert log.rows == 1000
        assert log.error_code is None
        assert log.error_message is None
        assert log.attempts == 1

    def test_create_fail_log(self) -> None:
        """Test creating a failed ingestion log."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network timeout",
        )

        assert log.status == IngestionStatus.FAIL
        assert log.error_code == "FETCH_ERROR"
        assert log.error_message == "Network timeout"
        assert log.checksum is None
        assert log.rows is None

    def test_default_attempts_is_one(self) -> None:
        """Test that default attempts value is 1."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        assert log.attempts == 1

    def test_attempts_can_be_incremented(self) -> None:
        """Test that attempts can be set to higher values."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network timeout",
            attempts=3,
        )
        assert log.attempts == 3

    def test_log_with_timestamps(self) -> None:
        """Test creating log with timestamps."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
            first_attempt_at="2024-01-02T10:00:00Z",
            last_attempt_at="2024-01-02T10:01:00Z",
        )
        assert log.first_attempt_at == "2024-01-02T10:00:00Z"
        assert log.last_attempt_at == "2024-01-02T10:01:00Z"

    def test_frozen_dataclass_is_immutable(self) -> None:
        """Test that IngestionLog is frozen (immutable)."""
        log = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            log.dataset = "other_dataset"


@pytest.mark.unit
class TestIngestionCursor:
    """Tests for IngestionCursor dataclass."""

    def test_create_cursor_with_success(self) -> None:
        """Test creating cursor after successful ingestion."""
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-02",
            last_attempted="2024-01-02",
            updated_at="2024-01-02T10:00:00Z",
        )

        assert cursor.dataset == "stock_daily"
        assert cursor.source == "tushare"
        assert cursor.last_success == "2024-01-02"
        assert cursor.last_attempted == "2024-01-02"

    def test_create_cursor_without_success(self) -> None:
        """Test creating cursor when no successful ingestion yet."""
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success=None,
            last_attempted="2024-01-02",
            updated_at="2024-01-02T10:00:00Z",
        )

        assert cursor.last_success is None
        assert cursor.last_attempted == "2024-01-02"

    def test_create_cursor_never_attempted(self) -> None:
        """Test creating cursor when never attempted."""
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success=None,
            last_attempted=None,
            updated_at="2024-01-02T10:00:00Z",
        )

        assert cursor.last_success is None
        assert cursor.last_attempted is None

    def test_frozen_dataclass_is_immutable(self) -> None:
        """Test that IngestionCursor is frozen (immutable)."""
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success=None,
            last_attempted=None,
            updated_at="2024-01-02T10:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cursor.last_success = "2024-01-03"


@pytest.mark.unit
class TestNotTradingDayError:
    """Tests for NotTradingDayError exception."""

    def test_exception_contains_trade_date(self) -> None:
        """Test that exception message contains the trade date."""
        error = NotTradingDayError("2024-01-06")
        assert "2024-01-06" in str(error)
        assert "is not a trading day" in str(error)

    def test_exception_stores_trade_date(self) -> None:
        """Test that exception stores the trade date."""
        error = NotTradingDayError("2024-01-06")
        assert error.trade_date == "2024-01-06"

    def test_exception_is_subclass_of_exception(self) -> None:
        """Test that NotTradingDayError is an Exception."""
        error = NotTradingDayError("2024-01-06")
        assert isinstance(error, Exception)
        # Can be raised and caught
        try:
            raise error
        except NotTradingDayError:
            pass
        except Exception:
            pytest.fail("Should be caught by NotTradingDayError")


@pytest.mark.unit
class TestDataChangedError:
    """Tests for DataChangedError exception."""

    def test_exception_contains_all_info(self) -> None:
        """Test that exception message contains all relevant info."""
        error = DataChangedError(
            trade_date="2024-01-02",
            old_checksum="abc123",
            new_checksum="def456",
        )
        message = str(error)
        assert "2024-01-02" in message
        assert "abc123" in message
        assert "def456" in message
        assert "checksum" in message
        assert "force=True" in message

    def test_exception_stores_attributes(self) -> None:
        """Test that exception stores all attributes."""
        error = DataChangedError(
            trade_date="2024-01-02",
            old_checksum="abc123",
            new_checksum="def456",
        )
        assert error.trade_date == "2024-01-02"
        assert error.old_checksum == "abc123"
        assert error.new_checksum == "def456"

    def test_exception_is_subclass_of_exception(self) -> None:
        """Test that DataChangedError is an Exception."""
        error = DataChangedError(
            trade_date="2024-01-02",
            old_checksum="abc123",
            new_checksum="def456",
        )
        assert isinstance(error, Exception)
        # Can be raised and caught
        try:
            raise error
        except DataChangedError:
            pass
        except Exception:
            pytest.fail("Should be caught by DataChangedError")
