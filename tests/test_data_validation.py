"""
Tests for data quality validation.

This module tests the data validation framework, including
individual validators, cross-source validation, and the
overall validation service.
"""

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, Mock

import polars as pl
import pytest
from data.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from data.validation.cross_validator import CrossSourceValidator
from data.validation.quality_reporter import QualityReporter
from data.validation.service import DataQualityService
from data.validation.validators import (
    LimitUpDownValidator,
    OHLCValidator,
    PriceContinuityValidator,
    VolumeValidator,
)


@pytest.fixture
def sample_daily_data() -> pl.DataFrame:
    """Create sample daily market data for testing."""
    return pl.DataFrame(
        {
            "ts_code": ["510300.SH"] * 5,
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
                date(2024, 1, 8),
            ],
            "open": [3.50, 3.52, 3.51, 3.53, 3.54],
            "high": [3.55, 3.53, 3.54, 3.56, 3.57],
            "low": [3.48, 3.50, 3.49, 3.51, 3.52],
            "close": [3.52, 3.51, 3.53, 3.54, 3.55],
            "pre_close": [3.50, 3.52, 3.51, 3.53, 3.54],
            "pct_chg": [0.57, -0.28, 0.57, 0.28, 0.28],
            "vol": [1000000, 1200000, 1100000, 1300000, 1250000],
            "amount": [3520000, 3612000, 3883000, 4602000, 4437500],
        }
    )


@pytest.fixture
def invalid_daily_data() -> pl.DataFrame:
    """Create invalid daily data for testing."""
    return pl.DataFrame(
        {
            "ts_code": ["510300.SH"] * 3,
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
            ],
            "open": [3.50, 3.52, 3.51],
            "high": [3.45, 3.53, 3.54],  # High < Low on first record
            "low": [3.48, 3.50, 3.49],
            "close": [3.60, 3.51, 3.53],  # Close > High on first record
            "pre_close": [3.50, 3.52, 3.51],
            "pct_chg": [2.86, -0.28, 0.57],
            "vol": [1000000, -500000, 1100000],  # Negative volume on second record
            "amount": [3520000, 3612000, 3883000],
        }
    )


@pytest.fixture
def mock_data_service() -> Any:
    """Create mock data service."""
    service = Mock()
    service.get_daily_data = AsyncMock(return_value=pl.DataFrame())
    service.get_adj_factors = AsyncMock(return_value=pl.DataFrame())
    service.get_etf_list = AsyncMock(
        return_value=pl.DataFrame(
            {
                "ts_code": ["510300.SH", "159919.SZ", "516010.SH"],
            }
        )
    )
    return service


class TestValidationIssue:
    """Test ValidationIssue class."""

    def test_validation_issue_creation(self) -> None:
        """Test creating a validation issue."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="TEST_ERROR",
            message="Test error message",
            ts_code="510300.SH",
            trade_date=date(2024, 1, 2),
            details={"test": "value"},
            suggestion="Fix the test",
        )

        assert issue.severity == ValidationSeverity.ERROR
        assert issue.code == "TEST_ERROR"
        assert issue.message == "Test error message"
        assert issue.ts_code == "510300.SH"
        assert issue.trade_date == date(2024, 1, 2)
        assert issue.details == {"test": "value"}
        assert issue.suggestion == "Fix the test"

    def test_to_dict(self) -> None:
        """Test converting validation issue to dictionary."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            code="TEST_WARNING",
            message="Test warning",
            ts_code="510300.SH",
            trade_date=date(2024, 1, 2),
        )

        result = issue.to_dict()

        assert result["severity"] == "warning"
        assert result["code"] == "TEST_WARNING"
        assert result["message"] == "Test warning"
        assert result["ts_code"] == "510300.SH"
        assert result["trade_date"] == "2024-01-02"


class TestValidationResult:
    """Test ValidationResult class."""

    def test_validation_result_properties(self) -> None:
        """Test validation result properties."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "ERR1", "Error 1"),
            ValidationIssue(ValidationSeverity.ERROR, "ERR2", "Error 2"),
            ValidationIssue(ValidationSeverity.WARNING, "WARN1", "Warning 1"),
            ValidationIssue(ValidationSeverity.INFO, "INFO1", "Info 1"),
        ]

        result = ValidationResult(
            is_valid=False,
            issues=issues,
            stats={"test": "value"},
        )

        assert result.error_count == 2
        assert result.warning_count == 1
        assert result.info_count == 1

    def test_get_issues_by_severity(self) -> None:
        """Test filtering issues by severity."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "ERR1", "Error 1"),
            ValidationIssue(ValidationSeverity.WARNING, "WARN1", "Warning 1"),
            ValidationIssue(ValidationSeverity.ERROR, "ERR2", "Error 2"),
        ]

        result = ValidationResult(is_valid=False, issues=issues, stats={})

        errors = result.get_issues_by_severity(ValidationSeverity.ERROR)
        warnings = result.get_issues_by_severity(ValidationSeverity.WARNING)

        assert len(errors) == 2
        assert len(warnings) == 1


class TestOHLCValidator:
    """Test OHLC validator."""

    def test_valid_data(self, sample_daily_data: pl.DataFrame) -> None:
        """Test validation of valid data."""
        validator = OHLCValidator()
        result = validator.validate(sample_daily_data)

        assert result.is_valid
        assert len(result.issues) == 0

    def test_invalid_high_low(self, invalid_daily_data: pl.DataFrame) -> None:
        """Test detection of high < low error."""
        validator = OHLCValidator()
        result = validator.validate(invalid_daily_data)

        assert not result.is_valid

        # Should have HIGH_LT_LOW error
        high_low_errors = [
            issue for issue in result.issues if issue.code == "HIGH_LT_LOW"
        ]
        assert len(high_low_errors) == 1
        assert high_low_errors[0].severity == ValidationSeverity.ERROR

    def test_invalid_close_range(self, invalid_daily_data: pl.DataFrame) -> None:
        """Test detection of close outside high-low range."""
        validator = OHLCValidator()
        result = validator.validate(invalid_daily_data)

        # Should have CLOSE_OUTSIDE_RANGE error
        close_errors = [
            issue for issue in result.issues if issue.code == "CLOSE_OUTSIDE_RANGE"
        ]
        assert len(close_errors) == 1
        assert close_errors[0].severity == ValidationSeverity.ERROR


class TestPriceContinuityValidator:
    """Test price continuity validator."""

    def test_continuous_prices(self, sample_daily_data: pl.DataFrame) -> None:
        """Test validation of continuous price data."""
        validator = PriceContinuityValidator()
        result = validator.validate(sample_daily_data)

        # Should have no major issues
        info_issues = result.get_issues_by_severity(ValidationSeverity.INFO)
        assert len(info_issues) == 0

    def test_stale_prices(self) -> None:
        """Test detection of stale prices."""
        # Create data with unchanged prices
        stale_data = pl.DataFrame(
            {
                "ts_code": ["510300.SH"] * 15,
                "trade_date": [date(2024, 1, i) for i in range(2, 17)],
                "close": [3.50] * 15,
                "pre_close": [3.50] * 15,
                "pct_chg": [0.0] * 15,
            }
        )

        validator = PriceContinuityValidator(config={"stale_price_days": 10})
        result = validator.validate(stale_data)

        # Should detect stale prices
        stale_issues = [
            issue for issue in result.issues if issue.code == "STALE_PRICES"
        ]
        assert len(stale_issues) > 0


class TestVolumeValidator:
    """Test volume validator."""

    def test_valid_volume(self, sample_daily_data: pl.DataFrame) -> None:
        """Test validation of valid volume data."""
        validator = VolumeValidator()
        result = validator.validate(sample_daily_data)

        assert len(result.issues) == 0

    def test_negative_volume(self, invalid_daily_data: pl.DataFrame) -> None:
        """Test detection of negative volume."""
        validator = VolumeValidator()
        result = validator.validate(invalid_daily_data)

        # Should detect negative volume
        negative_issues = [
            issue for issue in result.issues if issue.code == "NEGATIVE_VOLUME"
        ]
        assert len(negative_issues) == 1
        assert negative_issues[0].severity == ValidationSeverity.ERROR

    def test_volume_spike(self) -> None:
        """Test detection of volume spikes."""
        # Create data with volume spike
        spike_data = pl.DataFrame(
            {
                "vol": [1000000] * 19 + [15000000],  # 15x spike on day 20
            }
        )

        validator = VolumeValidator(config={"volume_spike_threshold": 10})
        result = validator.validate(spike_data)

        # Should detect volume spike
        spike_issues = [
            issue for issue in result.issues if issue.code == "VOLUME_SPIKE"
        ]
        assert len(spike_issues) > 0


class TestLimitUpDownValidator:
    """Test limit-up/down validator."""

    def test_normal_movements(self, sample_daily_data: pl.DataFrame) -> None:
        """Test validation of normal price movements."""
        validator = LimitUpDownValidator()
        result = validator.validate(sample_daily_data)

        # No limit movements should be detected
        limit_issues = [
            issue for issue in result.issues if issue.code in ["LIMIT_UP", "LIMIT_DOWN"]
        ]
        assert len(limit_issues) == 0

    def test_limit_movements(self) -> None:
        """Test detection of limit-up/down movements."""
        # Create data with limit movements
        limit_data = pl.DataFrame(
            {
                "pct_chg": [10.0, -10.0, 9.99],  # ETF limit is 10%
                "close": [3.85, 3.47, 3.81],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
            }
        )

        validator = LimitUpDownValidator()
        result = validator.validate(limit_data)

        # Should detect limit movements
        limit_up = [i for i in result.issues if i.code == "LIMIT_UP"]
        limit_down = [i for i in result.issues if i.code == "LIMIT_DOWN"]

        assert len(limit_up) == 1
        assert len(limit_down) == 1


class TestCrossSourceValidator:
    """Test cross-source validator."""

    def test_perfect_match(self, sample_daily_data: pl.DataFrame) -> None:
        """Test validation with perfectly matching data."""
        validator = CrossSourceValidator()
        issues = validator.validate(sample_daily_data, sample_daily_data)

        assert len(issues) == 0

    def test_price_discrepancy(self) -> None:
        """Test detection of price discrepancies."""
        primary = pl.DataFrame(
            {
                "close": [3.52, 3.54],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "ts_code": ["510300.SH", "510300.SH"],
            }
        )

        backup = pl.DataFrame(
            {
                "close": [3.53, 3.54],  # 0.01 difference on first record
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "ts_code": ["510300.SH", "510300.SH"],
            }
        )

        validator = CrossSourceValidator(config={"price_tolerance_pct": 0.01})
        issues = validator.validate(primary, backup)

        # Should detect price discrepancy
        price_issues = [issue for issue in issues if issue.code == "PRICE_DISCREPANCY"]
        assert len(price_issues) == 1

    def test_insufficient_overlap(self) -> None:
        """Test detection of insufficient data overlap."""
        primary = pl.DataFrame(
            {
                "close": [3.52, 3.54],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
                "ts_code": ["510300.SH", "510300.SH"],
            }
        )

        backup = pl.DataFrame(
            {
                "close": [3.51],
                "trade_date": [date(2024, 1, 5)],  # Different date
                "ts_code": ["510300.SH"],
            }
        )

        validator = CrossSourceValidator(config={"min_overlap_ratio": 0.5})
        issues = validator.validate(primary, backup)

        # Should detect insufficient overlap
        overlap_issues = [
            issue for issue in issues if issue.code == "INSUFFICIENT_OVERLAP"
        ]
        assert len(overlap_issues) == 1


class TestQualityReporter:
    """Test quality report generator."""

    def test_generate_report(self) -> None:
        """Test quality report generation."""
        validation_results = {
            "ohlc": ValidationResult(
                is_valid=True,
                issues=[],
                stats={"records_validated": 100},
            ),
            "volume": ValidationResult(
                is_valid=False,
                issues=[
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "VOLUME_SPIKE",
                        "Volume spike detected",
                        ts_code="510300.SH",
                    )
                ],
                stats={"records_validated": 100},
            ),
        }

        reporter = QualityReporter()
        report = reporter.generate_report(validation_results)

        assert report["summary"]["total_issues"] == 1
        assert report["summary"]["validators_passed"] == 1
        assert report["quality_scores"]["ohlc"]["score"] == 100
        assert report["quality_scores"]["volume"]["score"] == 95
        assert len(report["recommendations"]) > 0


@pytest.mark.asyncio
class TestDataQualityService:
    """Test data quality service."""

    async def test_validate_symbol(
        self,
        sample_daily_data: pl.DataFrame,
        mock_data_service: Any,
    ) -> None:
        """Test symbol validation."""
        mock_data_service.get_daily_data.return_value = sample_daily_data
        mock_data_service.get_adj_factors.return_value = pl.DataFrame()

        service = DataQualityService(mock_data_service)
        results = await service.validate_symbol(
            "510300.SH", date(2024, 1, 2), date(2024, 1, 8)
        )

        assert len(results) > 0
        assert "ohlc" in results
        assert "volume" in results

    async def test_validate_multiple_symbols(
        self, sample_daily_data: pl.DataFrame, mock_data_service: Any
    ) -> None:
        """Test multiple symbol validation."""
        mock_data_service.get_daily_data.return_value = sample_daily_data
        mock_data_service.get_adj_factors.return_value = pl.DataFrame()

        service = DataQualityService(mock_data_service)
        results = await service.validate_multiple_symbols(
            ["510300.SH", "159919.SZ"],
            date(2024, 1, 2),
            date(2024, 1, 8),
        )

        assert len(results) == 2
        assert "510300.SH" in results
        assert "159919.SZ" in results

    async def test_generate_quality_report(
        self, sample_daily_data: pl.DataFrame, mock_data_service: Any
    ) -> None:
        """Test quality report generation."""
        mock_data_service.get_daily_data.return_value = sample_daily_data
        mock_data_service.get_adj_factors.return_value = pl.DataFrame()

        service = DataQualityService(mock_data_service)
        report = await service.generate_quality_report(
            ts_codes=["510300.SH"],
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 8),
            save_report=False,
        )

        assert "summary" in report
        assert "quality_scores" in report
        assert "recommendations" in report

    async def test_health_check(
        self,
        sample_daily_data: pl.DataFrame,
        mock_data_service: Any,
    ) -> None:
        """Test health check functionality."""
        mock_data_service.get_daily_data.return_value = sample_daily_data
        mock_data_service.get_adj_factors.return_value = pl.DataFrame()

        service = DataQualityService(mock_data_service)
        health = await service.run_health_check(sample_size=1, days_back=5)

        assert "healthy" in health
        assert "score" in health
        assert "total_validations" in health

    def test_cache_management(self) -> None:
        """Test validation cache management."""
        service = DataQualityService(Mock())

        # Initially empty
        stats = service.get_cache_stats()
        assert stats["cached_entries"] == 0

        # Clear cache (should not error)
        service.clear_cache()
        stats = service.get_cache_stats()
        assert stats["cached_entries"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
