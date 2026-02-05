"""Tests for ingestion monitoring task."""

import pytest
from ditto_core.quality.spec import DQIssue, DQLevel, DQResult, DQSeverity
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability import init, reset_for_testing
from ditto_foundation.observability.config import ObservabilityConfig
from ditto_port.jobs.tasks.monitoring import monitor_ingestion_quality


@pytest.fixture(autouse=True)
def setup_observability():
    """Initialize observability for metrics testing."""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.mark.unit
class TestMonitorIngestionQuality:
    """Tests for monitor_ingestion_quality task."""

    def test_monitor_records_successful_ingestion_metrics(self) -> None:
        """Test monitoring records metrics for successful ingestion."""
        ingestion_results = {
            "etf_daily": {
                "trade_date": "2024-12-27",
                "rows_fetched": 5000,
                "rows_written": 4980,
                "new_securities_registered": 2,
                "api_calls": 1,
                "duration_sec": 5.5,
                "status": "success",
                "dq_result": DQResult(
                    dataset="etf_daily",
                    passed=True,
                    issues=[],
                ),
            }
        }

        # Should not raise
        result = monitor_ingestion_quality(
            trade_date="2024-12-27",
            ingestion_results=ingestion_results,
        )

        assert result["total_datasets"] == 1
        assert result["successful_datasets"] == 1

    def test_monitor_records_dq_failure_metrics(self) -> None:
        """Test monitoring records metrics for DQ failures."""
        # Create DQ result with errors
        dq_result = DQResult(
            dataset="stock_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="null_check",
                    message="Null values found",
                    affected_rows=10,
                ),
                DQIssue(
                    level=DQLevel.BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="price_range",
                    message="Price out of range",
                    affected_rows=5,
                ),
            ],
        )

        ingestion_results = {
            "stock_daily": {
                "trade_date": "2024-12-27",
                "rows_fetched": 10000,
                "rows_written": 9990,
                "new_securities_registered": 0,
                "api_calls": 2,
                "duration_sec": 15.0,
                "status": "warning",
                "dq_result": dq_result,
            }
        }

        result = monitor_ingestion_quality(
            trade_date="2024-12-27",
            ingestion_results=ingestion_results,
        )

        assert result["total_datasets"] == 1
        assert result["datasets_with_errors"] == 1
        assert result["datasets_with_warnings"] == 1
        assert result["total_dq_errors"] == 1
        assert result["total_dq_warnings"] == 1

    def test_monitor_aggregates_multiple_datasets(self) -> None:
        """Test monitoring aggregates metrics across multiple datasets."""
        ingestion_results = {
            "etf_daily": {
                "trade_date": "2024-12-27",
                "rows_fetched": 5000,
                "rows_written": 4980,
                "new_securities_registered": 2,
                "api_calls": 1,
                "duration_sec": 5.5,
                "status": "success",
                "dq_result": DQResult(dataset="etf_daily", passed=True, issues=[]),
            },
            "stock_daily": {
                "trade_date": "2024-12-27",
                "rows_fetched": 10000,
                "rows_written": 9990,
                "new_securities_registered": 0,
                "api_calls": 2,
                "duration_sec": 15.0,
                "status": "success",
                "dq_result": DQResult(dataset="stock_daily", passed=True, issues=[]),
            },
        }

        result = monitor_ingestion_quality(
            trade_date="2024-12-27",
            ingestion_results=ingestion_results,
        )

        assert result["total_datasets"] == 2
        assert result["successful_datasets"] == 2
        assert result["total_rows_fetched"] == 15000
        assert result["total_rows_written"] == 14970
        assert result["total_new_securities"] == 2
        assert result["total_api_calls"] == 3
        assert result["total_duration_sec"] == 20.5

    def test_monitor_handles_empty_results(self) -> None:
        """Test monitoring handles empty ingestion results."""
        result = monitor_ingestion_quality(
            trade_date="2024-12-27",
            ingestion_results={},
        )

        assert result["total_datasets"] == 0
        assert result["successful_datasets"] == 0
        assert result["total_rows_fetched"] == 0

    def test_monitor_handles_missing_dq_result(self) -> None:
        """Test monitoring handles results without DQ result."""
        ingestion_results = {
            "etf_daily": {
                "trade_date": "2024-12-27",
                "rows_fetched": 5000,
                "rows_written": 4980,
                "new_securities_registered": 2,
                "api_calls": 1,
                "duration_sec": 5.5,
                "status": "success",
                # Missing dq_result
            }
        }

        # Should not raise
        result = monitor_ingestion_quality(
            trade_date="2024-12-27",
            ingestion_results=ingestion_results,
        )

        assert result["total_datasets"] == 1
