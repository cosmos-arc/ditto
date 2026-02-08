# 测试文件允许函数内导入

"""Adj factor 摄取流程集成测试。"""

import polars as pl
import pytest


@pytest.mark.integration
class TestAdjFactorIngestion:
    """Tests for adj_factor ingestion with instrument_id mapping."""

    def test_ingest_adj_factor_uses_source_ticker_column(self, mocker):
        """Test that adj_factor ingestion uses source_ticker column for ID mapping."""
        from ditto_port.services.ingestion.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock dependencies
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.market = mocker.MagicMock()
        mock_hub.metadata = mocker.MagicMock()
        # Mock write_adj_factor to return dict[str, int]
        mock_hub.market.write_adj_factor.return_value = {
            "rows": 2,
            "files": 1,
        }
        mock_hub.metadata.resolve_or_create_batch.return_value = {
            "000001.SZ": 1_000_001,
            "000002.SZ": 1_000_002,
        }

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return data with source_ticker column
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {
                    "source_ticker": ["000001.SZ", "000002.SZ"],
                    "trade_date": ["2024-01-02", "2024-01-02"],
                    "adj_factor": [1.234, 1.567],
                }
            ),
        )

        # Execute ingestion
        result = coordinator.ingest_date("adj_factor", "2024-01-02")

        # Verify result status is success
        assert result.status == "success", f"Expected 'success', got '{result.status}'"

        # Verify market.write_adj_factor was called with dataframe containing
        # instrument_id
        call_args = mock_hub.market.write_adj_factor.call_args
        df_written = call_args.kwargs["df"]

        # Verify instrument_id/source_ticker columns exist in the written dataframe
        assert "instrument_id" in df_written.columns, (
            "instrument_id column missing in written dataframe"
        )
        assert "source_ticker" in df_written.columns, (
            "source_ticker column missing in written dataframe"
        )
        mock_hub.metadata.resolve_or_create_batch.assert_called_once_with(
            df=mocker.ANY,
            source="tushare",
            asset_class="stock",
            source_ticker_col="source_ticker",
        )

    def test_ingest_fund_adj_uses_source_ticker_column(self, mocker):
        """Test that fund_adj ingestion uses source_ticker column for ID mapping."""
        from ditto_port.services.ingestion.coordinator import IngestionCoordinator

        # Mock DataHub
        mock_hub = mocker.MagicMock()
        mock_source = mocker.MagicMock()

        # Mock dependencies
        mock_hub.ingestion_log = mocker.MagicMock()
        mock_hub.market = mocker.MagicMock()
        mock_hub.metadata = mocker.MagicMock()
        mock_hub.market.write_adj_factor.return_value = {
            "rows": 2,
            "files": 1,
        }
        mock_hub.metadata.resolve_or_create_batch.return_value = {
            "510300.SH": 2_000_001,
            "510500.SH": 2_000_002,
        }

        # Create coordinator
        coordinator = IngestionCoordinator(
            hub=mock_hub,
            source=mock_source,
            source_name="tushare",
        )

        # Mock _fetch_data to return data with source_ticker column
        mocker.patch.object(
            coordinator,
            "_fetch_data",
            return_value=pl.DataFrame(
                {
                    "source_ticker": ["510300.SH", "510500.SH"],
                    "trade_date": ["2024-01-02", "2024-01-02"],
                    "adj_factor": [1.123, 1.234],
                }
            ),
        )

        # Execute ingestion
        result = coordinator.ingest_date("fund_adj", "2024-01-02")

        # Verify result status is success
        assert result.status == "success", f"Expected 'success', got '{result.status}'"

        # Verify market.write_adj_factor was called with dataframe containing
        # instrument_id
        call_args = mock_hub.market.write_adj_factor.call_args
        df_written = call_args.kwargs["df"]

        # Verify instrument_id/source_ticker columns exist in the written dataframe
        assert "instrument_id" in df_written.columns, (
            "instrument_id column missing in written dataframe"
        )
        assert "source_ticker" in df_written.columns, (
            "source_ticker column missing in written dataframe"
        )
        mock_hub.metadata.resolve_or_create_batch.assert_called_once_with(
            df=mocker.ANY,
            source="tushare",
            asset_class="etf",
            source_ticker_col="source_ticker",
        )
