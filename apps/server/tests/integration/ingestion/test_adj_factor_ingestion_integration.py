# ruff: noqa: PLC0415  # 测试文件允许函数内导入

"""Tests for adj_factor and fund_adj ingestion with correct SID mapping.

This module tests that adj_factor and fund_adj datasets correctly map
source codes to internal SIDs using the correct column name (src_code).
"""

import polars as pl
import pytest


@pytest.mark.integration
class TestAdjFactorIngestion:
    """Tests for adj_factor ingestion with SID mapping."""

    def test_ingest_adj_factor_uses_src_code_column(self, mocker):
        """Test that adj_factor ingestion uses src_code column for SID mapping."""
        from ditto_server.ingestion.services.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock dependencies
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.ingestion_cursor = mocker.MagicMock()
        mock_hub.adj_factor = mocker.MagicMock()
        mock_hub.adj_factor.write.return_value = ("/path/to/file", "checksum123")

        # Mock security_store to return valid securities
        mock_hub.security_store = mocker.MagicMock()
        mock_hub.security_store.resolve_sid.side_effect = (
            lambda src_code, source, asset_class: {
                "000001.SZ": 1_000_001,
                "000002.SZ": 1_000_002,
            }.get(src_code)
        )

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return data with src_code column (not ts_code)
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {
                    "src_code": ["000001.SZ", "000002.SZ"],
                    "trade_date": ["2024-01-02", "2024-01-02"],
                    "adj_factor": [1.234, 1.567],
                }
            ),
        )

        # Execute ingestion
        result = coordinator.ingest_date("adj_factor", "2024-01-02")

        # Verify result status is success
        assert result.status == "success", f"Expected 'success', got '{result.status}'"

        # Verify adj_factor.write was called with dataframe containing sid
        call_args = mock_hub.adj_factor.write.call_args
        df_written = call_args.kwargs["df"]

        # Verify sid column exists in the written dataframe
        assert "sid" in df_written.columns, "sid column missing in written dataframe"
        assert "src_code" in df_written.columns, (
            "src_code column missing in written dataframe"
        )

    def test_ingest_fund_adj_uses_src_code_column(self, mocker):
        """Test that fund_adj ingestion uses src_code column for SID mapping."""
        from ditto_server.ingestion.services.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock dependencies
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.ingestion_cursor = mocker.MagicMock()
        mock_hub.adj_factor = mocker.MagicMock()
        mock_hub.adj_factor.write.return_value = ("/path/to/file", "checksum456")

        # Mock security_store to return valid securities
        mock_hub.security_store = mocker.MagicMock()
        mock_hub.security_store.resolve_sid.side_effect = (
            lambda src_code, source, asset_class: {
                "510300.SH": 2_000_001,
                "510500.SH": 2_000_002,
            }.get(src_code)
        )

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return data with src_code column (not ts_code)
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {
                    "src_code": ["510300.SH", "510500.SH"],
                    "trade_date": ["2024-01-02", "2024-01-02"],
                    "adj_factor": [1.123, 1.234],
                }
            ),
        )

        # Execute ingestion
        result = coordinator.ingest_date("fund_adj", "2024-01-02")

        # Verify result status is success
        assert result.status == "success", f"Expected 'success', got '{result.status}'"

        # Verify adj_factor.write was called with dataframe containing sid
        call_args = mock_hub.adj_factor.write.call_args
        df_written = call_args.kwargs["df"]

        # Verify sid column exists in the written dataframe
        assert "sid" in df_written.columns, "sid column missing in written dataframe"
        assert "src_code" in df_written.columns, (
            "src_code column missing in written dataframe"
        )
