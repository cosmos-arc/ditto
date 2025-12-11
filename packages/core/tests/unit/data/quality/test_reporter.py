"""Tests for DataQualityReporter."""

from typing import Any
from unittest.mock import Mock

import polars as pl
from ditto_core.data.quality.reporter import DataQualityReporter
from ditto_core.data.validators.base import BaseValidator, ValidationResult
from ditto_core.data.validators.price import PriceValidator
from ditto_core.data.validators.volume import VolumeValidator


class MockValidator(BaseValidator):
    """Mock validator for testing."""

    def __init__(
        self, name: str, is_valid: bool = True, message: str = "Mock validation"
    ) -> None:
        self._name = name
        self._is_valid = is_valid
        self._message = message

    @property
    def name(self) -> str:
        """Get validator name."""
        return self._name

    def validate(self, data: Any) -> ValidationResult:
        """Validate data and return result."""
        return ValidationResult(
            is_valid=self._is_valid,
            message=self._message,
            details={"mock_detail": "test_value"},
        )


class TestSingleSymbolReport:
    """Test single symbol report generation."""

    def test_generate_report_with_valid_data(self) -> None:
        """Test generating report with valid data."""
        # Arrange

        data = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [3.5, 3.6],
                "high": [3.6, 3.7],
                "low": [3.4, 3.5],
                "close": [3.55, 3.65],
                "volume": [1000000, 1200000],
            }
        )

        mock_validator = MockValidator("test_validator", is_valid=True)
        reporter = DataQualityReporter([mock_validator])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["symbol"] == "510300.SH"
        assert report["total_records"] == 2
        assert report["quality_score"] == 1.0
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 0
        assert len(report["validators"]) == 1
        assert report["validators"][0]["status"] == "passed"
        assert report["date_range"]["start"] == "2024-01-01"
        assert report["date_range"]["end"] == "2024-01-02"

    def test_generate_report_with_invalid_data(self) -> None:
        """Test generating report with invalid data."""
        # Arrange

        data = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.4],  # Invalid: high < open
                "low": [3.6],  # Invalid: low > open
                "close": [3.55],
                "volume": [1000000],
            }
        )

        mock_validator = MockValidator(
            "test_validator", is_valid=False, message="Invalid OHLC"
        )
        reporter = DataQualityReporter([mock_validator])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["symbol"] == "510300.SH"
        assert report["quality_score"] == 0.0
        assert report["summary"]["passed"] == 0
        assert report["summary"]["failed"] == 1
        assert report["validators"][0]["status"] == "failed"
        assert report["validators"][0]["message"] == "Invalid OHLC"

    def test_generate_report_with_empty_data(self) -> None:
        """Test generating report with empty data."""
        # Arrange

        data = pl.DataFrame()
        mock_validator = MockValidator("test_validator")
        reporter = DataQualityReporter([mock_validator])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["symbol"] == "510300.SH"
        assert report["total_records"] == 0
        assert report["quality_score"] == 0.0
        assert report["summary"]["failed"] == 1
        assert report["validators"][0]["status"] == "failed"
        assert "数据为空" in report["validators"][0]["message"]

    def test_generate_report_with_multiple_validators(self) -> None:
        """Test generating report with multiple validators."""
        # Arrange

        data = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        validators = [
            MockValidator("price_validator", is_valid=True),
            MockValidator("volume_validator", is_valid=False, message="Volume issue"),
        ]
        reporter = DataQualityReporter(validators)

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["quality_score"] == 0.5
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 1
        assert len(report["validators"]) == 2
        assert report["validators"][0]["status"] == "passed"
        assert report["validators"][1]["status"] == "failed"

    def test_generate_report_handles_validator_exceptions(self) -> None:
        """Test that report generation handles validator exceptions gracefully."""
        # Arrange

        data = pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        # Create a validator that raises an exception
        failing_validator = Mock()
        failing_validator.name = "failing_validator"
        failing_validator.validate.side_effect = Exception("Validation error")

        reporter = DataQualityReporter([failing_validator])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["summary"]["failed"] == 1
        assert report["validators"][0]["status"] == "failed"
        assert "验证器执行错误" in report["validators"][0]["message"]


class TestBatchReport:
    """Test batch report generation."""

    def test_generate_batch_report(self) -> None:
        """Test generating batch report for multiple symbols."""
        # Arrange

        data_dict = {
            "510300.SH": pl.DataFrame(
                {
                    "date": ["2024-01-01", "2024-01-02"],
                    "open": [3.5, 3.6],
                    "high": [3.6, 3.7],
                    "low": [3.4, 3.5],
                    "close": [3.55, 3.65],
                    "volume": [1000000, 1200000],
                }
            ),
            "516010.SH": pl.DataFrame(
                {
                    "date": ["2024-01-01"],
                    "open": [2.5],
                    "high": [2.6],
                    "low": [2.4],
                    "close": [2.55],
                    "volume": [800000],
                }
            ),
        }

        validators = [
            MockValidator("price_validator", is_valid=True),
            MockValidator("volume_validator", is_valid=True),
        ]
        reporter = DataQualityReporter(validators)

        # Act
        batch_report = reporter.generate_batch_report(data_dict)

        # Assert
        assert batch_report["total_symbols"] == 2
        assert batch_report["summary"]["total_records"] == 3
        assert batch_report["summary"]["avg_quality_score"] == 1.0
        assert len(batch_report["reports"]) == 2
        assert len(batch_report["summary"]["failed_symbols"]) == 0

        # Check score distribution
        dist = batch_report["summary"]["score_distribution"]
        assert dist["excellent"] == 2
        assert dist["good"] == 0
        assert dist["fair"] == 0
        assert dist["poor"] == 0

    def test_generate_batch_report_with_mixed_quality(self) -> None:
        """Test batch report with mixed quality scores."""
        # Arrange

        data_dict = {
            "510300.SH": pl.DataFrame(
                {
                    "date": ["2024-01-01"],
                    "open": [3.5],
                    "high": [3.6],
                    "low": [3.4],
                    "close": [3.55],
                    "volume": [1000000],
                }
            ),
            "516010.SH": pl.DataFrame(
                {
                    "date": ["2024-01-01"],
                    "open": [2.5],
                    "high": [2.4],  # Invalid
                    "low": [2.6],  # Invalid
                    "close": [2.55],
                    "volume": [800000],
                }
            ),
        }

        validators = [
            MockValidator("price_validator", is_valid=True),
            MockValidator("volume_validator", is_valid=False),
        ]
        reporter = DataQualityReporter(validators)

        # Act
        batch_report = reporter.generate_batch_report(data_dict)

        # Assert
        assert batch_report["total_symbols"] == 2
        assert batch_report["summary"]["avg_quality_score"] == 0.5
        assert "516010.SH" in batch_report["summary"]["failed_symbols"]

        # Check score distribution
        dist = batch_report["summary"]["score_distribution"]
        assert dist["excellent"] == 0
        assert dist["good"] == 0
        assert dist["fair"] == 2
        assert dist["poor"] == 0

    def test_generate_batch_report_empty_dict(self) -> None:
        """Test batch report with empty data dictionary."""
        # Arrange
        reporter = DataQualityReporter()

        # Act
        batch_report = reporter.generate_batch_report({})

        # Assert
        assert batch_report["total_symbols"] == 0
        assert batch_report["summary"]["total_records"] == 0
        assert batch_report["summary"]["avg_quality_score"] == 0.0
        assert len(batch_report["reports"]) == 0
        assert len(batch_report["summary"]["failed_symbols"]) == 0


class TestReporterConfiguration:
    """Test reporter configuration methods."""

    def test_default_validators(self) -> None:
        """Test that reporter is initialized with default validators."""
        # Act
        reporter = DataQualityReporter()

        # Assert
        assert len(reporter.validators) == 2
        assert reporter.validators[0].name == "price_validator"
        assert reporter.validators[1].name == "volume_validator"

    def test_custom_validators(self) -> None:
        """Test initializing reporter with custom validators."""
        # Arrange
        custom_validators = [MockValidator("custom1"), MockValidator("custom2")]

        # Act
        reporter = DataQualityReporter(custom_validators)

        # Assert
        assert len(reporter.validators) == 2
        assert reporter.validators[0].name == "custom1"
        assert reporter.validators[1].name == "custom2"

    def test_add_validator(self) -> None:
        """Test adding a validator to the reporter."""
        # Arrange
        reporter = DataQualityReporter()
        initial_count = len(reporter.validators)

        # Act
        reporter.add_validator(MockValidator("new_validator"))

        # Assert
        assert len(reporter.validators) == initial_count + 1
        assert reporter.validators[-1].name == "new_validator"

    def test_remove_validator(self) -> None:
        """Test removing a validator from the reporter."""
        # Arrange
        reporter = DataQualityReporter()
        initial_count = len(reporter.validators)

        # Act
        result = reporter.remove_validator("price_validator")

        # Assert
        assert result is True
        assert len(reporter.validators) == initial_count - 1
        assert not any(v.name == "price_validator" for v in reporter.validators)

    def test_remove_nonexistent_validator(self) -> None:
        """Test removing a validator that doesn't exist."""
        # Arrange
        reporter = DataQualityReporter()
        initial_count = len(reporter.validators)

        # Act
        result = reporter.remove_validator("nonexistent")

        # Assert
        assert result is False
        assert len(reporter.validators) == initial_count

    def test_list_validators(self) -> None:
        """Test listing all validator names."""
        # Arrange
        custom_validators = [MockValidator("test1"), MockValidator("test2")]
        reporter = DataQualityReporter(custom_validators)

        # Act
        validator_names = reporter.list_validators()

        # Assert
        assert validator_names == ["test1", "test2"]


class TestReportIntegration:
    """Integration tests with real validators."""

    def test_real_price_validator(self) -> None:
        """Test with actual price validator."""
        # Arrange

        # Create data with price issues
        data = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [3.5, -3.6],  # Negative price on second day
                "high": [3.6, 3.7],
                "low": [3.4, 3.8],  # low > high on second day
                "close": [3.55, 3.65],
                "volume": [1000000, 1200000],
            }
        )

        # Use real validators
        reporter = DataQualityReporter([PriceValidator()])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["summary"]["failed"] == 1
        assert report["quality_score"] == 0.0
        validator_report = report["validators"][0]
        assert validator_report["name"] == "price_validator"
        assert validator_report["status"] == "failed"
        assert "非正价格" in validator_report["message"]
        assert validator_report["details"]["negative_prices"] > 0

    def test_real_volume_validator(self) -> None:
        """Test with actual volume validator."""
        # Arrange

        # Create data with volume issues
        data = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "open": [3.5, 3.6, 3.7],
                "high": [3.6, 3.7, 3.8],
                "low": [3.4, 3.5, 3.6],
                "close": [3.55, 3.65, 3.75],
                "volume": [1000000, -500000, 100000000],  # Negative and extreme volume
            }
        )

        # Use real validators
        reporter = DataQualityReporter([VolumeValidator()])

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["summary"]["failed"] == 1
        assert report["quality_score"] == 0.0
        validator_report = report["validators"][0]
        assert validator_report["name"] == "volume_validator"
        assert validator_report["status"] == "failed"
        assert "负成交量" in validator_report["message"]

    def test_valid_data_with_real_validators(self) -> None:
        """Test with valid data using real validators."""
        # Arrange

        # Create valid data
        data = pl.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "open": [3.5, 3.6, 3.7],
                "high": [3.6, 3.7, 3.8],
                "low": [3.4, 3.5, 3.6],
                "close": [3.55, 3.65, 3.75],
                "volume": [1000000, 1200000, 1500000],
            }
        )

        # Use default validators (PriceValidator and VolumeValidator)
        reporter = DataQualityReporter()

        # Act
        report = reporter.generate_report(data, "510300.SH")

        # Assert
        assert report["summary"]["passed"] == 2
        assert report["summary"]["failed"] == 0
        assert report["quality_score"] == 1.0
        assert all(v["status"] == "passed" for v in report["validators"])
