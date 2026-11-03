"""Tushare metal adapter tests."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.metal import MetalTushareAdapter


@pytest.mark.unit
class TestMetalTushareAdapter:
    """Tushare 贵金属适配器测试."""

    def test_fetch_metal_daily_trade_date_utc_contract_dtype(self) -> None:
        """金属腿 trade_date_utc 为 ms 无时区（COMMODITY_SOURCE_SCHEMA 合同）。

        μs-UTC 会让三腿合流 concat 崩溃（#629 回补实测）。
        """
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["XAUUSD.FXCM"],
                "trade_date": ["20240115"],
                "bid_open": [2040.0],
                "bid_high": [2050.0],
                "bid_low": [2035.0],
                "bid_close": [2045.0],
            }
        )

        adapter = MetalTushareAdapter(_client=mock_client)
        df = adapter.fetch_metal_daily(
            codes=["XAUUSD"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert df.height == 1
        assert df.schema["trade_date_utc"] == pl.Datetime("ms")
