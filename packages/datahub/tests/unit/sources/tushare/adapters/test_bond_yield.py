"""Tests for BondYieldTushareAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA
from ditto_datahub.sources.tushare.adapters.bond_yield import (
    CN_BOND_YIELD_INDICATORS,
    BondYieldTushareAdapter,
    get_cn_bond_yield_indicator,
)


@pytest.mark.unit
class TestBondYieldTushareAdapter:
    """Tushare 国债收益率适配器测试."""

    def test_cn_bond_yield_indicators_exist(self) -> None:
        """测试指标定义存在."""
        assert "CN_BOND_YIELD_1Y" in CN_BOND_YIELD_INDICATORS
        assert "CN_BOND_YIELD_2Y" in CN_BOND_YIELD_INDICATORS
        assert "CN_BOND_YIELD_5Y" in CN_BOND_YIELD_INDICATORS
        assert "CN_BOND_YIELD_10Y" in CN_BOND_YIELD_INDICATORS

    def test_get_cn_bond_yield_indicator(self) -> None:
        """测试获取指标."""
        indicator = get_cn_bond_yield_indicator("CN_BOND_YIELD_10Y")
        assert indicator is not None
        assert indicator.curve_term == 10.0
        assert indicator.maturity == "10年"

    def test_get_cn_bond_yield_indicator_unknown(self) -> None:
        """测试未知指标返回 None."""
        indicator = get_cn_bond_yield_indicator("UNKNOWN")
        assert indicator is None

    def test_fetch_bond_yield_basic(self) -> None:
        """测试基本数据获取（使用长格式 API 响应）."""
        mock_client = MagicMock()
        # 模拟新的长格式 API 响应
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB", "1001.CB"],
                "trade_date": ["20240115", "20240115"],
                "curve_name": ["中债国债收益率曲线", "中债国债收益率曲线"],
                "curve_type": ["0", "0"],
                "curve_term": [1.0, 10.0],
                "yield": [2.15, 2.65],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        df = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert df.height == 2
        assert set(df["indicator_code"].unique()) == {
            "CN_BOND_YIELD_1Y",
            "CN_BOND_YIELD_10Y",
        }
        assert "date" in df.columns
        assert "value" in df.columns

    def test_fetch_bond_yield_empty_response(self) -> None:
        """测试空响应."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()

        adapter = BondYieldTushareAdapter(_client=mock_client)
        df = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert df.height == 0
        # 验证返回正确的 schema
        assert set(df.columns) == set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())

    def test_fetch_bond_yield_unknown_code_skipped(self) -> None:
        """测试未知代码被跳过."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [2.15],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        df = adapter.fetch_bond_yield(
            codes=["UNKNOWN_CODE"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 未知代码应该返回空 DataFrame
        assert df.height == 0
        # 没有有效指标时不应该调用 API
        mock_client.query.assert_not_called()

    def test_fetch_bond_yield_returns_correct_schema(self) -> None:
        """测试返回正确的 schema."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [2.15],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        expected_columns = set(MACRO_INDICATOR_SOURCE_SCHEMA.schema.keys())
        assert set(result.columns) == expected_columns

    def test_fetch_bond_yield_includes_metadata_columns(self) -> None:
        """测试结果包含所有元数据列."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [10.0],
                "yield": [2.65],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_10Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert result.height == 1
        assert result["indicator_code"][0] == "CN_BOND_YIELD_10Y"
        assert result["indicator_name"][0] == "中国10年期国债收益率"
        assert result["category"][0] == "interest_rate"
        assert result["frequency"][0] == "daily"
        assert result["source"][0] == "tushare"
        assert result["need_pit"][0] is False
        assert result["unit"][0] == "%"

    def test_fetch_bond_yield_parses_daily_date(self) -> None:
        """测试日期字符串 (YYYYMMDD) 正确解析."""
        from datetime import date

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [2.15],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert result["date"][0] == date(2024, 1, 15)

    def test_fetch_bond_yield_knowledge_date_equals_date(self) -> None:
        """测试 knowledge_date 等于 date（T+0 发布）."""
        from datetime import date

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [2.15],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert result["knowledge_date"][0] == date(2024, 1, 15)
        assert result["knowledge_date"][0] == result["date"][0]

    def test_fetch_bond_yield_multiple_indicators(self) -> None:
        """测试获取多个指标."""
        mock_client = MagicMock()
        # 2 days x 2 indicators = 4 rows in long format
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB", "1001.CB", "1001.CB", "1001.CB"],
                "trade_date": ["20240115", "20240115", "20240116", "20240116"],
                "curve_type": ["0", "0", "0", "0"],
                "curve_term": [1.0, 5.0, 1.0, 5.0],
                "yield": [2.15, 2.45, 2.20, 2.50],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_5Y"],
            start_date="2024-01-15",
            end_date="2024-01-16",
        )

        # 2 days x 2 indicators = 4 rows
        assert result.height == 4
        assert set(result["indicator_code"].unique()) == {
            "CN_BOND_YIELD_1Y",
            "CN_BOND_YIELD_5Y",
        }

    def test_fetch_bond_yield_null_values_filtered(self) -> None:
        """测试 NULL 值被过滤."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [None],  # type: ignore[list-item]
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        assert result.height == 0

    def test_fetch_bond_yield_uses_correct_api_params(self) -> None:
        """测试使用正确的 API 参数."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB"],
                "trade_date": ["20240115"],
                "curve_type": ["0"],
                "curve_term": [1.0],
                "yield": [2.15],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        mock_client.query.assert_called_once()
        call_kwargs = mock_client.query.call_args.kwargs
        assert call_kwargs["api_name"] == "yc_cb"
        assert call_kwargs["ts_code"] == "1001.CB"
        assert call_kwargs["curve_type"] == "0"
        assert call_kwargs["start_date"] == "20240115"
        assert call_kwargs["end_date"] == "20240115"

    def test_fetch_bond_yield_unwanted_terms_filtered(self) -> None:
        """测试不需要的期限被过滤."""
        mock_client = MagicMock()
        # 返回包含不需要的期限（3.0年）
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["1001.CB", "1001.CB", "1001.CB"],
                "trade_date": ["20240115", "20240115", "20240115"],
                "curve_type": ["0", "0", "0"],
                "curve_term": [1.0, 3.0, 10.0],  # 3.0 不是我们需要的
                "yield": [2.15, 2.30, 2.65],
            }
        )

        adapter = BondYieldTushareAdapter(_client=mock_client)
        result = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"],
            start_date="2024-01-15",
            end_date="2024-01-15",
        )

        # 只返回 1Y 和 10Y
        assert result.height == 2
        assert set(result["indicator_code"].unique()) == {
            "CN_BOND_YIELD_1Y",
            "CN_BOND_YIELD_10Y",
        }
