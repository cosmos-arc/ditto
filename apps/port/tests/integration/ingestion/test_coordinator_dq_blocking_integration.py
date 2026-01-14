# 测试文件允许函数内导入

"""Tests for DQ L1 blocking behavior in coordinator.

This module tests that when DQ L1 checks fail:
1. The ingestion result status is "failed"
2. The error code is "DQ_BLOCKED"
3. The log is recorded as FAIL status
"""

import polars as pl
import pytest


@pytest.mark.integration
class TestDQBlockingBehavior:
    """Tests for DQ L1 blocking behavior."""

    def test_dq_blocked_returns_failed_status(self, mocker):
        """Test that DQ blocked ingestion returns failed status."""
        from ditto_datahub.dq import DQResult
        from ditto_datahub.repositories.bars import WriteResult
        from ditto_port.services.ingestion.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock metadata manager to not skip
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.bars = mocker.MagicMock()

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return valid data
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame({"src_code": ["000001.SZ"], "close": [None]}),
        )

        # Mock _write_data to return blocked result
        mock_dq_result = mocker.MagicMock(spec=DQResult)
        mock_dq_result.has_errors = True
        mock_dq_result.error_count = 1

        blocked_result = WriteResult(
            file_path="",
            checksum="",
            rows_written=0,
            rows_total=0,
            blocked=True,
            dq_result=mock_dq_result,
        )

        mocker.patch.object(coordinator, "_write_data", return_value=blocked_result)

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
        from ditto_datahub.dq import DQResult
        from ditto_datahub.repositories.bars import WriteResult
        from ditto_datahub.sources.metadata import IngestionStatus
        from ditto_port.services.ingestion.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock metadata manager to not skip
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.bars = mocker.MagicMock()

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return valid data
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame({"src_code": ["000001.SZ"], "close": [None]}),
        )

        # Mock _write_data to return blocked result
        mock_dq_result = mocker.MagicMock(spec=DQResult)
        mock_dq_result.has_errors = True
        mock_dq_result.error_count = 1

        blocked_result = WriteResult(
            file_path="",
            checksum="",
            rows_written=0,
            rows_total=0,
            blocked=True,
            dq_result=mock_dq_result,
        )

        mocker.patch.object(coordinator, "_write_data", return_value=blocked_result)

        # Execute ingestion
        coordinator.ingest_date("stock_daily", "2024-01-02")

        # Verify log was saved with FAIL status
        mock_hub.ingestion_log.save_log.assert_called_once()
        call_kwargs = mock_hub.ingestion_log.save_log.call_args.kwargs

        assert call_kwargs["status"] == IngestionStatus.FAIL
        assert call_kwargs["error_code"] == "DQ_BLOCKED"
        assert "DQ L1 check failed" in call_kwargs["error_message"]
