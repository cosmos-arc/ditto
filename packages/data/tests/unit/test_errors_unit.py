"""Tests for Data error types."""

from ditto_data.errors import (
    CalendarError,
    DatasetNotFoundError,
    InstrumentIdNotFoundError,
    PartitionNotFoundError,
    TradingDateNotFoundError,
    ValidationError,
)
from ditto_kernel.exceptions import DataError, IdentifierError


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_is_data_error(self) -> None:
        """Test ValidationError inherits from DataError."""
        error = ValidationError("Test error")
        assert isinstance(error, DataError)
        assert str(error) == "Test error"

    def test_validation_error_with_details(self) -> None:
        """Test ValidationError can store details."""
        error = ValidationError(
            "Schema validation failed",
            details={"column": "instrument_id", "expected": "Int64"},
        )
        assert error.details == {"column": "instrument_id", "expected": "Int64"}


class TestDatasetNotFoundError:
    """Tests for DatasetNotFoundError."""

    def test_dataset_not_found_error_is_data_error(self) -> None:
        """Test DatasetNotFoundError inherits from DataError."""
        error = DatasetNotFoundError("Dataset not found")
        assert isinstance(error, DataError)

    def test_dataset_not_found_error_with_dataset(self) -> None:
        """Test DatasetNotFoundError stores dataset name."""
        error = DatasetNotFoundError(dataset="stock_daily")
        assert error.details == {"dataset": "stock_daily"}


class TestPartitionNotFoundError:
    """Tests for PartitionNotFoundError."""

    def test_partition_not_found_error_is_data_error(self) -> None:
        """Test PartitionNotFoundError inherits from DataError."""
        error = PartitionNotFoundError("Partition not found")
        assert isinstance(error, DataError)

    def test_partition_not_found_error_with_details(self) -> None:
        """Test PartitionNotFoundError stores details."""
        error = PartitionNotFoundError(dataset="stock_daily", year=2024)
        assert error.details == {"dataset": "stock_daily", "year": 2024}

    def test_partition_not_found_error_partial_details(self) -> None:
        """Test PartitionNotFoundError with partial details."""
        error = PartitionNotFoundError(dataset="stock_daily")
        assert error.details == {"dataset": "stock_daily"}


class TestCalendarError:
    """Tests for CalendarError."""

    def test_calendar_error_is_data_error(self) -> None:
        """Test CalendarError inherits from DataError."""
        error = CalendarError("Calendar error")
        assert isinstance(error, DataError)
        assert str(error) == "Calendar error"

    def test_calendar_error_with_details(self) -> None:
        """Test CalendarError can store details."""
        error = CalendarError(
            "Calendar validation failed",
            details={"calendar": "cn_stock", "date": "2024-01-01"},
        )
        assert error.details == {"calendar": "cn_stock", "date": "2024-01-01"}


class TestIdentifierError:
    """Tests for IdentifierError."""

    def test_identifier_error_is_data_error(self) -> None:
        """Test IdentifierError inherits from DataError."""
        error = IdentifierError("Identifier error")
        assert isinstance(error, DataError)
        assert str(error) == "Identifier error"

    def test_identifier_error_with_details(self) -> None:
        """Test IdentifierError can store details."""
        error = IdentifierError(
            "Identifier validation failed",
            details={"identifier": "000001.SZ", "source": "tushare"},
        )
        assert error.details == {"identifier": "000001.SZ", "source": "tushare"}


class TestSidNotFoundError:
    """Tests for InstrumentIdNotFoundError."""

    def test_sid_not_found_error_is_identifier_error(self) -> None:
        """Test InstrumentIdNotFoundError inherits from IdentifierError."""
        error = InstrumentIdNotFoundError()
        assert isinstance(error, IdentifierError)
        assert isinstance(error, DataError)

    def test_sid_not_found_error_default_message(self) -> None:
        """Test InstrumentIdNotFoundError has default message."""
        error = InstrumentIdNotFoundError()
        assert str(error) == "Instrument ID not found"
        assert error.details == {}

    def test_sid_not_found_error_custom_message(self) -> None:
        """Test InstrumentIdNotFoundError with custom message."""
        error = InstrumentIdNotFoundError(message="Custom Instrument ID not found")
        assert str(error) == "Custom Instrument ID not found"
        assert error.details == {}

    def test_sid_not_found_error_with_identifier(self) -> None:
        """Test InstrumentIdNotFoundError stores identifier."""
        error = InstrumentIdNotFoundError(identifier="000001.SZ")
        assert error.details == {"identifier": "000001.SZ"}

    def test_sid_not_found_error_with_source(self) -> None:
        """Test InstrumentIdNotFoundError stores source."""
        error = InstrumentIdNotFoundError(source="tushare")
        assert error.details == {"source": "tushare"}

    def test_sid_not_found_error_with_identifier_and_source(self) -> None:
        """Test InstrumentIdNotFoundError stores both identifier and source."""
        error = InstrumentIdNotFoundError(
            message="Instrument ID not found in source",
            identifier="000001.SZ",
            source="tushare",
        )
        assert str(error) == "Instrument ID not found in source"
        assert error.details == {"identifier": "000001.SZ", "source": "tushare"}

    def test_sid_not_found_error_all_combinations(self) -> None:
        """Test InstrumentIdNotFoundError with all parameters."""
        # Custom message + identifier only
        e1 = InstrumentIdNotFoundError(message="Custom", identifier="000001.SZ")
        assert e1.details == {"identifier": "000001.SZ"}

        # Custom message + source only
        e2 = InstrumentIdNotFoundError(message="Custom", source="tushare")
        assert e2.details == {"source": "tushare"}

        # Default message + both params
        e3 = InstrumentIdNotFoundError(identifier="000001.SZ", source="tushare")
        assert e3.details == {"identifier": "000001.SZ", "source": "tushare"}


class TestTradingDateNotFoundError:
    """Tests for TradingDateNotFoundError."""

    def test_trading_date_not_found_error_is_calendar_error(self) -> None:
        """Test TradingDateNotFoundError inherits from CalendarError."""
        error = TradingDateNotFoundError()
        assert isinstance(error, CalendarError)
        assert isinstance(error, DataError)

    def test_trading_date_not_found_error_default_message(self) -> None:
        """Test TradingDateNotFoundError has default message."""
        error = TradingDateNotFoundError()
        assert str(error) == "Trading date not found"
        assert error.details == {}

    def test_trading_date_not_found_error_custom_message(self) -> None:
        """Test TradingDateNotFoundError with custom message."""
        error = TradingDateNotFoundError(message="Custom date not found")
        assert str(error) == "Custom date not found"
        assert error.details == {}

    def test_trading_date_not_found_error_with_date(self) -> None:
        """Test TradingDateNotFoundError stores date."""
        error = TradingDateNotFoundError(date="2024-01-01")
        assert error.details == {"date": "2024-01-01"}

    def test_trading_date_not_found_error_with_direction(self) -> None:
        """Test TradingDateNotFoundError stores direction."""
        error = TradingDateNotFoundError(direction="prev")
        assert error.details == {"direction": "prev"}

    def test_trading_date_not_found_error_with_date_and_direction(self) -> None:
        """Test TradingDateNotFoundError stores both date and direction."""
        error = TradingDateNotFoundError(
            message="Trading date not found in calendar",
            date="2024-01-01",
            direction="next",
        )
        assert str(error) == "Trading date not found in calendar"
        assert error.details == {"date": "2024-01-01", "direction": "next"}

    def test_trading_date_not_found_error_all_combinations(self) -> None:
        """Test TradingDateNotFoundError with all parameters."""
        # Custom message + date only
        e1 = TradingDateNotFoundError(message="Custom", date="2024-01-01")
        assert e1.details == {"date": "2024-01-01"}

        # Custom message + direction only
        e2 = TradingDateNotFoundError(message="Custom", direction="next")
        assert e2.details == {"direction": "next"}

        # Default message + both params
        e3 = TradingDateNotFoundError(date="2024-01-01", direction="prev")
        assert e3.details == {"date": "2024-01-01", "direction": "prev"}
