"""Tushare FX adapter tests."""

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
        assert "USDCNH.FXCM" in FX_CODE_TO_INSTRUMENT_ID
        assert "EURUSD.FXCM" in FX_CODE_TO_INSTRUMENT_ID
        assert FX_CODE_TO_INSTRUMENT_ID["USDCNH.FXCM"] == 4_000_001

    def test_fetch_fx_daily_basic(self) -> None:
        """测试基本汇率数据获取."""
        # 设置模拟返回
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["USDCNH.FXCM"],
                "trade_date": ["20240115"],
                "open": [7.1800],
                "high": [7.1900],
                "low": [7.1750],
                "close": [7.1850],
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
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns

        # 验证 instrument_id 正确
        assert df["instrument_id"][0] == 4_000_001

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
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
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
