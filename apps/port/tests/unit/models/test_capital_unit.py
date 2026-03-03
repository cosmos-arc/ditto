"""Tests for Capital domain models.

MarginQuery, Margin, ValuationQuery, Valuation.
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestMarginQuery:
    """测试 MarginQuery 查询参数模型."""

    def test_default_values(self) -> None:
        """验证默认值: instrument_id 必填, as_of_date 必填."""
        from ditto_port.models.capital import MarginQuery

        query = MarginQuery(instrument_id="000001.SZ", as_of_date=date(2024, 1, 15))
        assert query.instrument_id == "000001.SZ"
        assert query.as_of_date == date(2024, 1, 15)

    def test_instrument_id_required(self) -> None:
        """验证 instrument_id 是必填字段."""
        from ditto_port.models.capital import MarginQuery

        with pytest.raises(ValidationError):
            MarginQuery(as_of_date=date(2024, 1, 15))  # type: ignore[call-arg]

    def test_as_of_date_required(self) -> None:
        """验证 as_of_date 是必填字段."""
        from ditto_port.models.capital import MarginQuery

        with pytest.raises(ValidationError):
            MarginQuery(instrument_id="000001.SZ")  # type: ignore[call-arg]


@pytest.mark.unit
class TestMargin:
    """测试 Margin 响应模型."""

    def test_basic_margin(self) -> None:
        """验证基本 Margin 创建."""
        from ditto_port.models.capital import Margin

        margin = Margin(
            instrument_id="000001.SZ",
            trade_date="2024-01-15",
            margin_buy_balance=1000000.0,
            short_sell_balance=500000.0,
            margin_buy_volume=100000,
            short_sell_volume=50000,
        )

        assert margin.instrument_id == "000001.SZ"
        assert margin.trade_date == "2024-01-15"
        assert margin.margin_buy_balance == 1000000.0
        assert margin.short_sell_balance == 500000.0
        assert margin.margin_buy_volume == 100000
        assert margin.short_sell_volume == 50000

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_port.models.capital import Margin

        margin = Margin(
            instrument_id="000001.SZ",
            trade_date="2024-01-15",
            margin_buy_balance=1000000.0,
            short_sell_balance=500000.0,
            margin_buy_volume=100000,
            short_sell_volume=50000,
        )

        data = margin.model_dump()
        assert data["instrument_id"] == "000001.SZ"
        assert data["trade_date"] == "2024-01-15"
        assert data["margin_buy_balance"] == 1000000.0


@pytest.mark.unit
class TestToMargin:
    """测试 to_margin 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_port.models.capital import to_margin

        row: dict[str, Any] = {
            "instrument_id": "000001.SZ",
            "trade_date": "2024-01-15",
            "margin_buy_balance": 1000000.0,
            "short_sell_balance": 500000.0,
            "margin_buy_volume": 100000,
            "short_sell_volume": 50000,
        }

        margin = to_margin(row)

        assert margin.instrument_id == "000001.SZ"
        assert margin.trade_date == "2024-01-15"
        assert margin.margin_buy_balance == 1000000.0
        assert margin.short_sell_balance == 500000.0
        assert margin.margin_buy_volume == 100000
        assert margin.short_sell_volume == 50000


@pytest.mark.unit
class TestToMarginList:
    """测试 to_margin_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.capital import to_margin_list

        df = pl.DataFrame()
        result = to_margin_list(df)
        assert result == []

    def test_convert_single_row_dataframe(self) -> None:
        """验证单行 DataFrame 转换."""
        from ditto_port.models.capital import to_margin_list

        df = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": ["2024-01-15"],
                "margin_buy_balance": [1000000.0],
                "short_sell_balance": [500000.0],
                "margin_buy_volume": [100000],
                "short_sell_volume": [50000],
            }
        )

        result = to_margin_list(df)

        assert len(result) == 1
        assert result[0].instrument_id == "000001.SZ"
        assert result[0].trade_date == "2024-01-15"

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_port.models.capital import to_margin_list

        df = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ", "000001.SZ"],
                "trade_date": ["2024-01-15", "2024-01-16"],
                "margin_buy_balance": [1000000.0, 1100000.0],
                "short_sell_balance": [500000.0, 550000.0],
                "margin_buy_volume": [100000, 110000],
                "short_sell_volume": [50000, 55000],
            }
        )

        result = to_margin_list(df)

        assert len(result) == 2
        assert result[0].instrument_id == "000001.SZ"
        assert result[1].instrument_id == "000001.SZ"


@pytest.mark.unit
class TestValuationQuery:
    """测试 ValuationQuery 查询参数模型."""

    def test_required_fields(self) -> None:
        """验证必填字段."""
        from ditto_port.models.capital import ValuationQuery

        query = ValuationQuery(instrument_id="000001.SZ", as_of_date=date(2024, 1, 15))
        assert query.instrument_id == "000001.SZ"
        assert query.as_of_date == date(2024, 1, 15)


@pytest.mark.unit
class TestValuation:
    """测试 Valuation 响应模型."""

    def test_basic_valuation(self) -> None:
        """验证基本 Valuation 创建."""
        from ditto_port.models.capital import Valuation

        valuation = Valuation(
            instrument_id="000001.SZ",
            trade_date="2024-01-15",
            pe_ratio=15.5,
            pb_ratio=2.3,
            ps_ratio=3.2,
            dividend_yield=0.025,
            market_cap=50000000000.0,
        )

        assert valuation.instrument_id == "000001.SZ"
        assert valuation.trade_date == "2024-01-15"
        assert valuation.pe_ratio == 15.5
        assert valuation.pb_ratio == 2.3
        assert valuation.ps_ratio == 3.2
        assert valuation.dividend_yield == 0.025
        assert valuation.market_cap == 50000000000.0

    def test_valuation_with_optional_fields_none(self) -> None:
        """验证可选字段为 None."""
        from ditto_port.models.capital import Valuation

        valuation = Valuation(
            instrument_id="000001.SZ",
            trade_date="2024-01-15",
            pe_ratio=None,
            pb_ratio=2.3,
            ps_ratio=None,
            dividend_yield=None,
            market_cap=50000000000.0,
        )

        assert valuation.pe_ratio is None
        assert valuation.ps_ratio is None
        assert valuation.dividend_yield is None


@pytest.mark.unit
class TestToValuation:
    """测试 to_valuation 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_port.models.capital import to_valuation

        row: dict[str, Any] = {
            "instrument_id": "000001.SZ",
            "trade_date": "2024-01-15",
            "pe_ratio": 15.5,
            "pb_ratio": 2.3,
            "ps_ratio": 3.2,
            "dividend_yield": 0.025,
            "market_cap": 50000000000.0,
        }

        valuation = to_valuation(row)

        assert valuation.instrument_id == "000001.SZ"
        assert valuation.trade_date == "2024-01-15"
        assert valuation.pe_ratio == 15.5
        assert valuation.pb_ratio == 2.3

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的转换."""
        from ditto_port.models.capital import to_valuation

        row: dict[str, Any] = {
            "instrument_id": "000001.SZ",
            "trade_date": "2024-01-15",
            "pe_ratio": None,
            "pb_ratio": 2.3,
            "ps_ratio": None,
            "dividend_yield": None,
            "market_cap": 50000000000.0,
        }

        valuation = to_valuation(row)
        assert valuation.pe_ratio is None
        assert valuation.ps_ratio is None


@pytest.mark.unit
class TestToValuationList:
    """测试 to_valuation_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.capital import to_valuation_list

        df = pl.DataFrame()
        result = to_valuation_list(df)
        assert result == []

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_port.models.capital import to_valuation_list

        df = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ", "000001.SZ"],
                "trade_date": ["2024-01-15", "2024-01-16"],
                "pe_ratio": [15.5, 16.0],
                "pb_ratio": [2.3, 2.4],
                "ps_ratio": [3.2, 3.3],
                "dividend_yield": [0.025, 0.026],
                "market_cap": [50000000000.0, 51000000000.0],
            }
        )

        result = to_valuation_list(df)

        assert len(result) == 2
        assert result[0].pe_ratio == 15.5
        assert result[1].pe_ratio == 16.0
