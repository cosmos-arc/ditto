"""Tests for FredSource."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
from ditto_data.sources.fred.fred_source import FredSource


class TestFredSourceInit:
    """Tests for FredSource initialization."""

    def test_init_creates_adapters(self) -> None:
        """Test initialization creates macro and commodity adapters."""
        with (
            patch("ditto_data.sources.fred.fred_source.MacroFredAdapter") as mock_macro,
            patch(
                "ditto_data.sources.fred.fred_source.CommodityFredAdapter"
            ) as mock_commodity,
        ):
            FredSource(api_key="test_key")
            mock_macro.assert_called_once_with(api_key="test_key")
            mock_commodity.assert_called_once_with(api_key="test_key")


class TestFredSourceMacroMethods:
    """Tests for FredSource macro methods."""

    def test_fetch_macro_indicators_with_codes(self) -> None:
        """日更按频率分组做有界回看，捕获"今天发布、观察期在过去"的值."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            result = source.fetch_macro_indicators(
                trade_date="2024-01-15",
                codes=["US_CPI_INDEX", "US_GDP_QOQ"],  # monthly + quarterly
            )

        calls = mock_adapter.fetch_indicators.call_args_list
        assert len(calls) == 2
        by_frequency = {call.kwargs["codes"][0]: call for call in calls}
        # 月度回看 400 天、季度回看 900 天（_DAILY_UPDATE_LOOKBACK_DAYS）
        assert by_frequency["US_CPI_INDEX"].kwargs == {
            "codes": ["US_CPI_INDEX"],
            "start_date": "2022-12-11",
            "end_date": "2024-01-15",
        }
        assert by_frequency["US_GDP_QOQ"].kwargs == {
            "codes": ["US_GDP_QOQ"],
            "start_date": "2021-07-29",
            "end_date": "2024-01-15",
        }
        assert result.height == 0

    def test_fetch_macro_indicators_monthly_publication_day_captured(
        self,
    ) -> None:
        """#432 回归：发布日在今天、观察期在上月的月度值必须落在请求窗口内."""
        mock_adapter = MagicMock()
        # 适配器原样返回（模拟 2024-01-15 发布 2023-12-01 观察）
        mock_adapter.fetch_indicators.side_effect = lambda **kwargs: pl.DataFrame(
            {
                "indicator_code": ["US_CPI_INDEX"],
                "date": [pl.date(2023, 12, 1)],
                "value": [3.4],
                "start": [kwargs["start_date"]],
            }
        )

        with patch(
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            source.fetch_macro_indicators(
                trade_date="2024-01-15",
                codes=["US_CPI_INDEX"],
            )

        request_start = mock_adapter.fetch_indicators.call_args.kwargs["start_date"]
        # 旧实现 start=end=当天 会漏掉 2023-12-01 的观察
        assert request_start <= "2023-12-01"

    def test_fetch_macro_indicators_without_codes_uses_all(self) -> None:
        """Test fetch_macro_indicators uses ALL_FRED_CODES when codes is None."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
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
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            result = source.fetch_macro_indicators_range(
                codes=["US_CPI_INDEX"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

        mock_adapter.fetch_indicators.assert_called_once_with(
            codes=["US_CPI_INDEX"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert result.height == 0

    def test_fetch_macro_indicators_passes_realtime_end(self) -> None:
        """fetch_macro_indicators 透传 realtime_end 给 adapter（启用 PIT）."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            source.fetch_macro_indicators(
                trade_date="2024-01-15",
                codes=["US_CPI_INDEX"],
                realtime_end="2024-01-15",
            )

        mock_adapter.fetch_indicators.assert_called_once_with(
            codes=["US_CPI_INDEX"],
            start_date="2022-12-11",  # 月度回看窗口 + realtime_end 透传
            end_date="2024-01-15",
            realtime_end="2024-01-15",
        )

    def test_fetch_macro_indicators_range_passes_realtime(self) -> None:
        """fetch_macro_indicators_range 透传 realtime_start/realtime_end."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_indicators.return_value = pl.DataFrame(
            {"indicator_code": [], "date": []}
        )

        with patch(
            "ditto_data.sources.fred.fred_source.MacroFredAdapter",
            return_value=mock_adapter,
        ):
            source = FredSource(api_key="test_key")
            source.fetch_macro_indicators_range(
                codes=["US_CPI_INDEX"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                realtime_start="2024-01-01",
                realtime_end="2024-01-31",
            )

        mock_adapter.fetch_indicators.assert_called_once_with(
            codes=["US_CPI_INDEX"],
            start_date="2024-01-01",
            end_date="2024-01-31",
            realtime_start="2024-01-01",
            realtime_end="2024-01-31",
        )


class TestFredSourceCommodityMethods:
    """Tests for FredSource commodity methods."""

    def test_fetch_commodities(self) -> None:
        """Test fetch_commodities delegates to commodity adapter."""
        mock_adapter = MagicMock()
        mock_adapter.fetch_commodities.return_value = pl.DataFrame(
            {"code": [], "date": []}
        )

        with patch(
            "ditto_data.sources.fred.fred_source.CommodityFredAdapter",
            return_value=mock_adapter,
        ):
            with patch("ditto_data.sources.fred.fred_source.MacroFredAdapter"):
                source = FredSource(api_key="test_key")
                result = source.fetch_commodities(
                    codes=["COMMOD_WTI", "COMMOD_BRENT"],
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                )

        mock_adapter.fetch_commodities.assert_called_once_with(
            codes=["COMMOD_WTI", "COMMOD_BRENT"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        assert result.height == 0
