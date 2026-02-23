"""Tests for Stock adapter."""

from unittest.mock import MagicMock

import polars as pl
import pytest


@pytest.mark.unit
class TestStockAdapterFetchByTicker:
    """测试 StockAdapter 按股票查询功能."""

    def test_fetch_stock_daily_by_ticker_uses_ts_code(self) -> None:
        """按股票查询应使用 ts_code 参数."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20240115"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "pre_close": [10.0],
                "vol": [1000000],
                "amount": [10500000],
                "pct_chg": [5.0],
            }
        )

        adapter = StockTushareAdapter(_client=mock_client)

        # 按股票+时间段查询
        result = adapter.fetch_stock_daily(
            source_ticker="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # 验证调用了正确的 API
        mock_client.query.assert_called_once()
        call_kwargs = mock_client.query.call_args.kwargs
        assert call_kwargs["api_name"] == "daily"
        assert call_kwargs["ts_code"] == "000001.SZ"
        assert call_kwargs["start_date"] == "20240101"
        assert call_kwargs["end_date"] == "20240131"
        assert isinstance(result, pl.DataFrame)

    def test_fetch_stock_daily_by_ticker_returns_dataframe(self) -> None:
        """按股票查询应返回 DataFrame."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": ["20240115", "20240116"],
                "open": [10.0, 10.5],
                "high": [11.0, 11.5],
                "low": [9.5, 10.0],
                "close": [10.5, 11.0],
                "pre_close": [10.0, 10.5],
                "vol": [1000000, 1200000],
                "amount": [10500000, 13200000],
                "pct_chg": [5.0, 4.76],
            }
        )

        adapter = StockTushareAdapter(_client=mock_client)
        result = adapter.fetch_stock_daily(
            source_ticker="000001.SZ",
            start_date="2024-01-15",
            end_date="2024-01-16",
        )

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2

    def test_fetch_stock_daily_by_ticker_empty_result(self) -> None:
        """按股票查询无数据时应返回空 DataFrame."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()

        adapter = StockTushareAdapter(_client=mock_client)
        result = adapter.fetch_stock_daily(
            source_ticker="999999.SZ",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()


@pytest.mark.unit
class TestStockAdapterFetchMutualExclusiveParams:
    """测试 StockAdapter 参数互斥校验."""

    def test_fetch_stock_daily_mutual_exclusive_params(self) -> None:
        """trade_date 和 source_ticker 互斥."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="互斥"):
            adapter.fetch_stock_daily(
                trade_date="2024-01-15",
                source_ticker="000001.SZ",
            )

    def test_fetch_stock_daily_requires_at_least_one_param(self) -> None:
        """必须指定 trade_date 或 source_ticker 之一."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="必须指定"):
            adapter.fetch_stock_daily()

    def test_fetch_stock_daily_by_ticker_requires_date_range(self) -> None:
        """按股票查询必须指定 start_date 和 end_date."""
        from ditto_datahub.sources.tushare.adapters.stock import StockTushareAdapter

        mock_client = MagicMock()
        adapter = StockTushareAdapter(_client=mock_client)

        with pytest.raises(ValueError, match="必须指定"):
            adapter.fetch_stock_daily(
                source_ticker="000001.SZ",
                start_date="",
                end_date="",
            )
