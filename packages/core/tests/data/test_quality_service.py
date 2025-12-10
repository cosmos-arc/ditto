"""Unit tests for DataQualityService."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from ditto_core.data.quality_service import DataQualityService


class TestDataQualityService:
    """Test DataQualityService functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_data_service = MagicMock()
        self.quality_service = DataQualityService(self.mock_data_service)

    def test_initialization(self) -> None:
        """Test DataQualityService initialization."""
        assert self.quality_service.data_service == self.mock_data_service

    @pytest.mark.asyncio
    async def test_validate_symbol(self) -> None:
        """Test validating data for a single symbol."""
        test_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        validators = ["completeness", "accuracy", "consistency"]

        result = await self.quality_service.validate_symbol(
            symbol="000001.SZ",
            start_date=test_date,
            end_date=end_date,
            validators=validators,
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_validate_symbol_no_validators(self) -> None:
        """Test validating symbol without validators."""
        test_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)

        result = await self.quality_service.validate_symbol(
            symbol="000001.SZ", start_date=test_date, end_date=end_date, validators=None
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_run_health_check(self) -> None:
        """Test running overall data health check."""
        result = await self.quality_service.run_health_check(
            sample_size=100, days_back=30
        )

        assert isinstance(result, dict)
        assert result["healthy"] is True
        assert result["score"] == 100.0
        assert isinstance(result["symbols_checked"], list)
        assert "date_range" in result
        assert isinstance(result["date_range"]["start"], date)
        assert isinstance(result["date_range"]["end"], date)
        assert result["total_validations"] == 0
        assert result["passed_validations"] == 0
        assert result["critical_issues"] == 0

    @pytest.mark.asyncio
    async def test_run_health_check_with_different_params(self) -> None:
        """Test health check with different parameters."""
        result = await self.quality_service.run_health_check(
            sample_size=500, days_back=90
        )

        assert isinstance(result, dict)
        assert result["healthy"] is True
        assert isinstance(result["score"], float)

    @pytest.mark.asyncio
    async def test_generate_quality_report(self) -> None:
        """Test generating comprehensive quality report."""
        test_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        ts_codes = ["000001.SZ", "000002.SZ"]

        result = await self.quality_service.generate_quality_report(
            ts_codes=ts_codes,
            start_date=test_date,
            end_date=end_date,
            save_report=False,
        )

        assert isinstance(result, dict)
        assert "summary" in result
        assert "quality_scores" in result
        assert "issue_analysis" in result
        assert "recommendations" in result

        # Check summary structure
        summary = result["summary"]
        assert summary["validators_run"] == 0
        assert summary["validators_passed"] == 0
        assert summary["success_rate"] == 1.0
        assert summary["quality_score"] == 100.0
        assert summary["total_issues"] == 0
        assert summary["total_records_validated"] == 0

        # Check issue breakdown
        issue_breakdown = summary["issue_breakdown"]
        assert issue_breakdown["critical"] == 0
        assert issue_breakdown["error"] == 0
        assert issue_breakdown["warning"] == 0
        assert issue_breakdown["info"] == 0

    @pytest.mark.asyncio
    async def test_generate_quality_report_no_params(self) -> None:
        """Test generating quality report with minimal parameters."""
        result = await self.quality_service.generate_quality_report(
            ts_codes=None, start_date=None, end_date=None
        )

        assert isinstance(result, dict)
        assert "summary" in result
        assert "quality_scores" in result
        assert "issue_analysis" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_generate_quality_report_save_enabled(self) -> None:
        """Test generating quality report with save enabled."""
        result = await self.quality_service.generate_quality_report(
            ts_codes=["000001.SZ"], start_date=None, end_date=None, save_report=True
        )

        assert isinstance(result, dict)
        assert isinstance(result["summary"], dict)

    @pytest.mark.asyncio
    async def test_date_range_in_health_check(self) -> None:
        """Test that health check returns correct date range."""
        days_back = 7
        expected_end = date.today()
        expected_end - timedelta(days=days_back)

        result = await self.quality_service.run_health_check(
            sample_size=10, days_back=days_back
        )

        assert result["date_range"]["end"] == expected_end
        assert isinstance(result["date_range"]["start"], date)
