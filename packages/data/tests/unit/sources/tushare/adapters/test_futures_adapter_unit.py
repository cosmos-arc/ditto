"""Tests for FuturesTushareAdapter（#434 期货合约日线与合约信息）."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.futures import (
    FUTURES_BASIC_SCHEMA,
    FUTURES_DAILY_SCHEMA,
    FuturesTushareAdapter,
)


def _daily_response() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_code": ["CU2506.SHF", "SCTASL.INE"],
            "trade_date": ["20260930", "20260930"],
            "open": [77300.0, None],
            "high": [77580.0, None],
            "low": [77080.0, None],
            "close": [77220.0, None],
            "settle": [77140.0, 696.1],
            "pre_settle": [77300.0, 716.9],
            "vol": [3872.0, 0.0],
            "amount": [7070.03, None],
            "oi": [4119.0, None],
        }
    )


@pytest.mark.unit
class TestFuturesDaily:
    def test_normalizes_columns_and_keeps_null_close(self) -> None:
        """close=null 且 settle 有效的行原样保留，不互填。"""
        mock_client = MagicMock()
        mock_client.query.return_value = _daily_response()
        adapter = FuturesTushareAdapter(_client=mock_client)

        result = adapter.fetch_daily(trade_date="2026-09-30")

        assert result.columns == list(FUTURES_DAILY_SCHEMA)
        assert result.height == 2
        row = result.filter(pl.col("source_ticker") == "SCTASL.INE").to_dicts()[0]
        assert row["close"] is None
        assert row["settle"] == 696.1
        assert row["knowledge_date"] == date.today()

    def test_trade_date_mode_sends_compact_date(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = _daily_response()
        adapter = FuturesTushareAdapter(_client=mock_client)

        adapter.fetch_daily(trade_date="2026-09-30")

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["api_name"] == "fut_daily"
        assert kwargs["trade_date"] == "20260930"
        assert "ts_code" not in kwargs

    def test_ticker_mode_sends_window(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = _daily_response()
        adapter = FuturesTushareAdapter(_client=mock_client)

        adapter.fetch_daily(
            source_ticker="CU2506.SHF",
            start_date="2025-01-01",
            end_date="2025-04-30",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["ts_code"] == "CU2506.SHF"
        assert kwargs["start_date"] == "20250101"
        assert kwargs["end_date"] == "20250430"

    def test_mutually_exclusive_params_raise(self) -> None:
        adapter = FuturesTushareAdapter(_client=MagicMock())
        with pytest.raises(ValueError, match="互斥"):
            adapter.fetch_daily(trade_date="2026-09-30", source_ticker="CU2506.SHF")
        with pytest.raises(ValueError, match="之一"):
            adapter.fetch_daily()

    def test_empty_response_returns_schema_frame(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()
        adapter = FuturesTushareAdapter(_client=mock_client)

        result = adapter.fetch_daily(trade_date="2026-10-01")

        assert result.height == 0
        assert result.columns == list(FUTURES_DAILY_SCHEMA)


@pytest.mark.unit
class TestFuturesBasic:
    def test_fetches_each_official_exchange(self) -> None:
        """按官方交易所代码分片（SHFE/CZCE 而非 SHF/ZCE）。"""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["CU2506.SHF"],
                "symbol": ["CU2506"],
                "exchange": ["SHFE"],
                "fut_code": ["CU"],
                "multiplier": ["5"],
                "list_date": ["20250422"],
                "delist_date": ["20250616"],
            }
        )
        adapter = FuturesTushareAdapter(_client=mock_client)

        result = adapter.fetch_basic()

        requested = [
            call.kwargs["exchange"] for call in mock_client.query.call_args_list
        ]
        assert requested == ["SHFE", "CZCE", "DCE", "INE", "CFFEX", "GFEX"]
        assert result.height == 6  # 每个交易所返回同一行 mock
        assert result.columns == list(FUTURES_BASIC_SCHEMA)
        row = result.to_dicts()[0]
        assert row["list_date"] == date(2025, 4, 22)
        assert row["delist_date"] == date(2025, 6, 16)
        assert row["multiplier"] == 5.0
        assert row["source"] == "tushare"

    def test_all_exchanges_empty_returns_schema_frame(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()
        adapter = FuturesTushareAdapter(_client=mock_client)

        result = adapter.fetch_basic()

        assert result.height == 0
        assert result.columns == list(FUTURES_BASIC_SCHEMA)
