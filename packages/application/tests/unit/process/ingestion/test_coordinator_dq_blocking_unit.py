# 测试文件允许函数内导入

"""
Tests for DQ L1 blocking behavior in coordinator.

This module tests that when DQ L1 checks fail:
1. The ingestion result status is "failed"
2. The error code is "DQ_BLOCKED"
3. The log is recorded as FAIL status
"""

import polars as pl
import pytest


@pytest.mark.unit
class TestDQBlockingBehavior:
    """Tests for DQ L1 blocking behavior."""

    def test_dq_blocked_returns_failed_status(self, mocker):
        """Test that DQ blocked ingestion returns failed status."""
        from ditto_application.processes.ingestion.config import (
            IngestionCoordinatorConfig,
        )
        from ditto_application.processes.ingestion.coordinator import (
            IngestionCoordinator,
            IngestionServices,
            MarketServices,
            SourceFetchers,
        )
        from ditto_data.quality.quality_types import DQResult
        from ditto_platform.foundation import WriteResult

        # Mock services
        mock_metadata_service = mocker.MagicMock()
        mock_market_service = mocker.MagicMock()
        mock_fundamental_service = mocker.MagicMock()
        mock_capital_service = mocker.MagicMock()
        mock_macro_service = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_ingestion_log_service = mocker.MagicMock()

        # Mock metadata manager to not skip
        mock_ingestion_log_service.get_log.return_value = None

        # Create coordinator
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_service,
                    write=mock_market_service,
                ),
                fundamental=mock_fundamental_service,
                capital=mock_capital_service,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_service=mock_ingestion_log_service,
            ),
        )

        # Mock _fetch_data to return valid data
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {"source_ticker": ["000001.SZ"], "close": [None]}
            ),
        )

        # Mock _data_writer.write_data to return blocked result
        mock_dq_result = mocker.MagicMock(spec=DQResult)
        mock_dq_result.has_errors = True
        mock_dq_result.error_count = 1

        blocked_result = WriteResult(
            file_path="",
            checksum="",
            rows_written=0,
            rows_total=0,
            blocked=True,
        )

        mocker.patch.object(
            coordinator._data_writer, "write_data", return_value=blocked_result
        )

        # Execute ingestion
        result = coordinator.ingest_date("stock_daily", "2024-01-02")

        # Verify result status is failed
        assert result.status == "failed", f"Expected 'failed', got '{result.status}'"
        assert result.error == "DQ_BLOCKED", (
            f"Expected 'DQ_BLOCKED', got '{result.error}'"
        )
        assert "DQ L1 check failed" in result.message

    def test_dq_blocked_logs_fail_status(self, mocker):
        """Test that DQ blocked ingestion logs FAIL status for retry."""
        from ditto_application.processes.ingestion.config import (
            IngestionCoordinatorConfig,
        )
        from ditto_application.processes.ingestion.coordinator import (
            IngestionCoordinator,
            IngestionServices,
            MarketServices,
            SourceFetchers,
        )
        from ditto_data.models.ingestion import IngestionLog, IngestionStatus
        from ditto_data.quality.quality_types import DQResult
        from ditto_platform.foundation import WriteResult

        # Mock services
        mock_metadata_service = mocker.MagicMock()
        mock_market_service = mocker.MagicMock()
        mock_fundamental_service = mocker.MagicMock()
        mock_capital_service = mocker.MagicMock()
        mock_macro_service = mocker.MagicMock()
        mock_source = mocker.MagicMock()
        mock_ingestion_log_service = mocker.MagicMock()

        # Mock metadata manager to not skip
        mock_ingestion_log_service.get_log.return_value = None

        # Create coordinator
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_service,
                    write=mock_market_service,
                ),
                fundamental=mock_fundamental_service,
                capital=mock_capital_service,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_service=mock_ingestion_log_service,
            ),
        )

        # Mock _fetch_data to return valid data
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {"source_ticker": ["000001.SZ"], "close": [None]}
            ),
        )

        # Mock _data_writer.write_data to return blocked result
        mock_dq_result = mocker.MagicMock(spec=DQResult)
        mock_dq_result.has_errors = True
        mock_dq_result.error_count = 1

        blocked_result = WriteResult(
            file_path="",
            checksum="",
            rows_written=0,
            rows_total=0,
            blocked=True,
        )

        mocker.patch.object(
            coordinator._data_writer, "write_data", return_value=blocked_result
        )

        # Execute ingestion
        coordinator.ingest_date("stock_daily", "2024-01-02")

        # Verify log was saved with FAIL status
        mock_ingestion_log_service.save_log.assert_called_once()
        # 获取位置参数中的 IngestionLog 对象
        call_args = mock_ingestion_log_service.save_log.call_args.args
        log_entry = call_args[0]

        assert isinstance(log_entry, IngestionLog)
        assert log_entry.status == IngestionStatus.FAIL
        assert log_entry.error_code == "DQ_BLOCKED"
        assert "DQ L1 check failed" in log_entry.error_message
