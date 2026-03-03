"""Tests for FredSource."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from ditto_datahub.sources.fred.fred_source import FredSource


class TestFredSourceInit:
    """Tests for FredSource initialization."""

    def test_init_creates_adapters(self) -> None:
        """Test initialization creates macro and commodity adapters."""
        with (
            patch(
                "ditto_datahub.sources.fred.fred_source.MacroFredAdapter"
            ) as mock_macro,
            patch(
                "ditto_datahub.sources.fred.fred_source.CommodityFredAdapter"
            ) as mock_commodity,
        ):
            FredSource(api_key="test_key")
            mock_macro.assert_called_once_with(api_key="test_key")
            mock_commodity.assert_called_once_with(api_key="test_key")


class TestFredSourceMacroMethods:
    """Tests for FredSource macro methods."""

    def test_fetch_macro_indicators_with_codes(self) -> None:
        """Test fetch_macro_indicators delegates to macro adapter with codes."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_datahub.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            result = source.fetch_macro_indicators(
                trade_date="2024-01-15",
                codes=["US_CPI_YOY", "US_GDP_QOQ"],
            )

        mock_adapter.fetch_indicators.assert_called_once_with(
            codes=["US_CPI_YOY", "US_GDP_QOQ"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )
        assert result.height == 0

    def test_fetch_macro_indicators_without_codes_uses_all(self) -> None:
        """Test fetch_macro_indicators uses ALL_FRED_CODES when codes is None."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_datahub.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            source.fetch_macro_indicators(trade_date="2024-01-15", codes=None)

        # Verify that fetch_indicators was called with a non-empty list
        call_args = mock_adapter.fetch_indicators.call_args
        assert call_args is not None
        codes_arg = call_args.kwargs["codes"]
        assert len(codes_arg) > 0  # ALL_FRED_CODES should have items
        assert "start_date" in call_args.kwargs
        assert "end_date" in call_args.kwargs

    def test_fetch_macro_indicators_range(self) -> None:
        """Test fetch_macro_indicators_range delegates to macro adapter."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_datahub.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            result = source.fetch_macro_indicators_range(
                codes=["US_CPI_YOY"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

        mock_adapter.fetch_indicators.assert_called_once_with(
            codes=["US_CPI_YOY"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert result.height == 0


class TestFredSourceCommodityMethods:
    """Tests for FredSource commodity methods."""

    def test_fetch_commodities(self) -> None:
        """Test fetch_commodities delegates to commodity adapter."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_commodities.return_value = pl.DataFrame(
            {"code": [], "date": []}
        )

        with patch(
            "ditto_datahub.sources.fred.fred_source.CommodityFredAdapter",
            return_value=mock_adapter,
        ):
            with patch("ditto_datahub.sources.fred.fred_source.MacroFredAdapter"):
                source = FredSource(api_key="test_key")
                result = source.fetch_commodities(
                    codes=["COMMOD_WTI", "COMMOD_GOLD"],
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                )

        mock_adapter.fetch_commodities.assert_called_once_with(
            codes=["COMMOD_WTI", "COMMOD_GOLD"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert result.height == 0


class TestFredSourceUnsupportedMethods:
    """Tests for FredSource unsupported methods that raise NotImplementedError."""

    @pytest.fixture
    def source(self) -> FredSource:
        """Create FredSource with mocked adapters."""
        with (
            patch("ditto_datahub.sources.fred.fred_source.MacroFredAdapter"),
            patch("ditto_datahub.sources.fred.fred_source.CommodityFredAdapter"),
        ):
            return FredSource(api_key="test_key")

    def test_fetch_calendar_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_calendar raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="trading calendar"):
            source.fetch_calendar("2024-01-01", "2024-12-31")

    def test_fetch_stock_basic_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_stock_basic raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="stock data"):
            source.fetch_stock_basic()

    def test_fetch_stock_daily_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_stock_daily raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="stock data"):
            source.fetch_stock_daily(trade_date="2024-01-15")

    def test_fetch_adj_factor_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_adj_factor raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="adjustment factors"):
            source.fetch_adj_factor("2024-01-15")

    def test_fetch_etf_basic_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_etf_basic raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="ETF data"):
            source.fetch_etf_basic()

    def test_fetch_etf_daily_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_etf_daily raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="ETF data"):
            source.fetch_etf_daily(trade_date="2024-01-15")

    def test_fetch_index_basic_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_index_basic raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="index data"):
            source.fetch_index_basic()

    def test_fetch_fx_daily_raises_not_implemented(self, source: FredSource) -> None:
        """Test fetch_fx_daily raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="FX data"):
            source.fetch_fx_daily(
                ts_codes=["USDCNH"], start_date="2024-01-01", end_date="2024-01-31"
            )
