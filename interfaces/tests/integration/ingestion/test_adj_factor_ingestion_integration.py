# 测试文件允许函数内导入

"""Adj factor 摄取流程集成测试。"""

import polars as pl
import pytest


@pytest.mark.integration
class TestAdjFactorIngestion:
    """Tests for adj_factor ingestion with instrument_id mapping."""

    def test_ingest_adj_factor_uses_source_ticker_column(self, mocker):
        """Test that adj_factor ingestion uses source_ticker column for ID mapping."""
        from ditto_app.process.ingestion.config import IngestionCoordinatorConfig
        from ditto_app.process.ingestion.coordinator import (
            IngestionCoordinator,
            MarketServices,
        )
        from ditto_data.ingestion.ingestion_log_service import IngestionLogService
        from ditto_data.services.capital_service import CapitalService
        from ditto_data.services.fundamental_service import FundamentalService
        from ditto_data.services.macro_service import MacroService
        from ditto_data.services.market_service import MarketService
        from ditto_data.services.market_write_service import MarketWriteService
        from ditto_data.services.metadata_service import MetadataService

        # Mock services
        mock_metadata_service = mocker.MagicMock(spec=MetadataService)
        mock_market_service = mocker.MagicMock(spec=MarketService)
        mock_market_write_service = mocker.MagicMock(spec=MarketWriteService)
        mock_fundamental_service = mocker.MagicMock(spec=FundamentalService)
        mock_capital_service = mocker.MagicMock(spec=CapitalService)
        mock_macro_service = mocker.MagicMock(spec=MacroService)
        mock_ingestion_log_service = mocker.MagicMock(spec=IngestionLogService)
        mock_source = mocker.MagicMock()

        # Mock return values
        mock_market_write_service.save_adj_factor.return_value = 2
        mock_metadata_service.resolve_or_create_instruments_batch.return_value = {
            "000001.SZ": 1_000_001,
            "000002.SZ": 1_000_002,
        }

        # Create coordinator
        coordinator = IngestionCoordinator(
            metadata_service=mock_metadata_service,
            market_services=MarketServices(
                query=mock_market_service,
                write=mock_market_write_service,
            ),
            fundamental_service=mock_fundamental_service,
            capital_service=mock_capital_service,
            macro_service=mock_macro_service,
            source=mock_source,
            config=IngestionCoordinatorConfig(
                ingestion_log_service=mock_ingestion_log_service,
            ),
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

        # Verify save_adj_factor was called
        mock_market_write_service.save_adj_factor.assert_called_once()
        call_args = mock_market_write_service.save_adj_factor.call_args
        df_written = call_args.kwargs["df"]

        # Verify instrument_id/source_ticker columns exist in the written dataframe
        assert "instrument_id" in df_written.columns, (
            "instrument_id column missing in written dataframe"
        )
        assert "source_ticker" in df_written.columns, (
            "source_ticker column missing in written dataframe"
        )
        mock_metadata_service.resolve_or_create_instruments_batch.assert_called_once_with(
            df=mocker.ANY,
            source="tushare",
            asset_class="stock",
            source_ticker_col="source_ticker",
        )

    def test_ingest_fund_adj_uses_source_ticker_column(self, mocker):
        """Test that fund_adj ingestion uses source_ticker column for ID mapping."""
        from ditto_app.process.ingestion.config import IngestionCoordinatorConfig
        from ditto_app.process.ingestion.coordinator import (
            IngestionCoordinator,
            MarketServices,
        )
        from ditto_data.ingestion.ingestion_log_service import IngestionLogService
        from ditto_data.services.capital_service import CapitalService
        from ditto_data.services.fundamental_service import FundamentalService
        from ditto_data.services.macro_service import MacroService
        from ditto_data.services.market_service import MarketService
        from ditto_data.services.market_write_service import MarketWriteService
        from ditto_data.services.metadata_service import MetadataService

        # Mock services
        mock_metadata_service = mocker.MagicMock(spec=MetadataService)
        mock_market_service = mocker.MagicMock(spec=MarketService)
        mock_market_write_service = mocker.MagicMock(spec=MarketWriteService)
        mock_fundamental_service = mocker.MagicMock(spec=FundamentalService)
        mock_capital_service = mocker.MagicMock(spec=CapitalService)
        mock_macro_service = mocker.MagicMock(spec=MacroService)
        mock_ingestion_log_service = mocker.MagicMock(spec=IngestionLogService)
        mock_source = mocker.MagicMock()

        # Mock return values
        mock_market_write_service.save_adj_factor.return_value = 2
        mock_metadata_service.resolve_or_create_instruments_batch.return_value = {
            "510300.SH": 2_000_001,
            "510500.SH": 2_000_002,
        }

        # Create coordinator
        coordinator = IngestionCoordinator(
            metadata_service=mock_metadata_service,
            market_services=MarketServices(
                query=mock_market_service,
                write=mock_market_write_service,
            ),
            fundamental_service=mock_fundamental_service,
            capital_service=mock_capital_service,
            macro_service=mock_macro_service,
            source=mock_source,
            config=IngestionCoordinatorConfig(
                ingestion_log_service=mock_ingestion_log_service,
            ),
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

        # Verify save_adj_factor was called
        mock_market_write_service.save_adj_factor.assert_called_once()
        call_args = mock_market_write_service.save_adj_factor.call_args
        df_written = call_args.kwargs["df"]

        # Verify instrument_id/source_ticker columns exist in the written dataframe
        assert "instrument_id" in df_written.columns, (
            "instrument_id column missing in written dataframe"
        )
        assert "source_ticker" in df_written.columns, (
            "source_ticker column missing in written dataframe"
        )
        mock_metadata_service.resolve_or_create_instruments_batch.assert_called_once_with(
            df=mocker.ANY,
            source="tushare",
            asset_class="etf",
            source_ticker_col="source_ticker",
        )
