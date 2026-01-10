"""Tests for DataHub error types."""

from ditto_datahub.errors import (
    DataHubError,
    DatasetNotFoundError,
    PartitionNotFoundError,
    ValidationError,
)


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_is_datahub_error(self) -> None:
        """Test ValidationError inherits from DataHubError."""
        error = ValidationError("Test error")
        assert isinstance(error, DataHubError)
        assert str(error) == "Test error"

    def test_validation_error_with_details(self) -> None:
        """Test ValidationError can store details."""
        error = ValidationError(
            "Schema validation failed",
            details={"column": "sid", "expected": "Int64"},
        )
        assert error.details == {"column": "sid", "expected": "Int64"}


class TestDatasetNotFoundError:
    """Tests for DatasetNotFoundError."""

    def test_dataset_not_found_error_is_datahub_error(self) -> None:
        """Test DatasetNotFoundError inherits from DataHubError."""
        error = DatasetNotFoundError("Dataset not found")
        assert isinstance(error, DataHubError)

    def test_dataset_not_found_error_with_dataset(self) -> None:
        """Test DatasetNotFoundError stores dataset name."""
        error = DatasetNotFoundError(dataset="stock_daily")
        assert error.details == {"dataset": "stock_daily"}


class TestPartitionNotFoundError:
    """Tests for PartitionNotFoundError."""

    def test_partition_not_found_error_is_datahub_error(self) -> None:
        """Test PartitionNotFoundError inherits from DataHubError."""
        error = PartitionNotFoundError("Partition not found")
        assert isinstance(error, DataHubError)

    def test_partition_not_found_error_with_details(self) -> None:
        """Test PartitionNotFoundError stores details."""
        error = PartitionNotFoundError(dataset="stock_daily", year=2024)
        assert error.details == {"dataset": "stock_daily", "year": 2024}

    def test_partition_not_found_error_partial_details(self) -> None:
        """Test PartitionNotFoundError with partial details."""
        error = PartitionNotFoundError(dataset="stock_daily")
        assert error.details == {"dataset": "stock_daily"}
