"""Tushare FX adapter tests."""

from datetime import UTC
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.sources.tushare.adapters.fx import (
    FX_CODE_TO_INSTRUMENT_ID,
    FxTushareAdapter,
)


@pytest.mark.unit
class TestFxTushareAdapter:
    """Tushare 汇率适配器测试."""

    def test_fx_code_mapping_exists(self) -> None:
        """测试汇率代码映射存在."""
        # 外汇货币对
        assert "USDCNH.FXCM" in FX_CODE_TO_INSTRUMENT_ID
        assert "EURUSD.FXCM" in FX_CODE_TO_INSTRUMENT_ID
        assert FX_CODE_TO_INSTRUMENT_ID["USDCNH.FXCM"] == 4_000_001
        # 贵金属现货通过 FRED 获取，不在 Tushare 列表中
        assert "XAUUSD.FXCM" not in FX_CODE_TO_INSTRUMENT_ID
        assert "XAGUSD.FXCM" not in FX_CODE_TO_INSTRUMENT_ID

    def test_fetch_fx_daily_basic(self) -> None:
        """测试基本汇率数据获取."""
        # 设置模拟返回 - 使用 Tushare 实际返回的 bid_ 前缀字段
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["USDCNH.FXCM"],
                "trade_date": ["20240115"],
                "bid_open": [7.1800],
                "bid_high": [7.1900],
                "bid_low": [7.1750],
                "bid_close": [7.1850],
            }
        )

        # 创建适配器并获取数据
        adapter = FxTushareAdapter(_client=mock_client)
        df = adapter.fetch_fx_daily(
            ts_codes=["USDCNH.FXCM"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 验证返回结构
        assert df.height == 1
        assert "instrument_id" in df.columns
        assert "trade_date" in df.columns
        assert "trade_date_utc" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns

        # 验证 instrument_id 正确
        assert df["instrument_id"][0] == 4_000_001

    def test_fetch_fx_daily_trade_date_utc_conversion(self) -> None:
        """测试 trade_date_utc 字段的时区转换."""
        mock_client = MagicMock()
        # 使用 2024-01-15 作为测试日期 - 使用 bid_ 前缀字段
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["USDCNH.FXCM"],
                "trade_date": ["20240115"],
                "bid_open": [7.1800],
                "bid_high": [7.1900],
                "bid_low": [7.1750],
                "bid_close": [7.1850],
            }
        )

        adapter = FxTushareAdapter(_client=mock_client)
        df = adapter.fetch_fx_daily(
            ts_codes=["USDCNH.FXCM"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 验证 trade_date_utc 字段存在
        assert "trade_date_utc" in df.columns
        assert df.height == 1

        # 验证 UTC 时间戳类型
        trade_date_utc = df["trade_date_utc"][0]
        assert trade_date_utc is not None

        # Tushare fx_daily 日期为 GMT（格林尼治时间），直接转换为 UTC
        # 所以 2024-01-15 GMT = 2024-01-15 00:00:00 UTC
        from datetime import datetime

        expected_utc = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        # Polars 返回的是带时区的 datetime
        assert trade_date_utc == expected_utc

    def test_fetch_fx_daily_empty_response(self) -> None:
        """测试空响应返回空 DataFrame."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()

        adapter = FxTushareAdapter(_client=mock_client)
        df = adapter.fetch_fx_daily(
            ts_codes=["USDCNH.FXCM"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 验证返回空 DataFrame 但有正确 schema
        assert df.height == 0
        assert "instrument_id" in df.columns

    def test_fetch_fx_daily_unknown_code(self) -> None:
        """测试未知代码返回空 DataFrame."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["UNKNOWN.FXCM"],
                "trade_date": ["20240115"],
                "bid_open": [1.0],
                "bid_high": [1.0],
                "bid_low": [1.0],
                "bid_close": [1.0],
            }
        )

        adapter = FxTushareAdapter(_client=mock_client)
        df = adapter.fetch_fx_daily(
            ts_codes=["UNKNOWN.FXCM"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 未知代码应该被跳过
        assert df.height == 0
