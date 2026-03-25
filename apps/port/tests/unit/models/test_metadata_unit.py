"""Tests for Metadata domain models.

AssetClass, InstrumentQuery, Instrument, to_instrument, to_instrument_list.
"""

from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestAssetClass:
    """测试 AssetClass 枚举."""

    def test_asset_class_values(self) -> None:
        """验证 AssetClass 包含 stock, etf, index."""
        from ditto_kernel.enums import AssetClass

        assert AssetClass.STOCK.value == "stock"
        assert AssetClass.ETF.value == "etf"
        assert AssetClass.INDEX.value == "index"
        assert AssetClass.FUTURE.value == "future"
        assert AssetClass.BOND.value == "bond"
        assert AssetClass.FUND.value == "fund"

    def test_asset_class_from_string(self) -> None:
        """验证可以从字符串创建 AssetClass."""
        from ditto_kernel.enums import AssetClass

        assert AssetClass("stock") == AssetClass.STOCK
        assert AssetClass("etf") == AssetClass.ETF
        assert AssetClass("index") == AssetClass.INDEX

    def test_asset_class_invalid_value(self) -> None:
        """验证无效值会抛出异常."""
        from ditto_kernel.enums import AssetClass

        with pytest.raises(ValueError):
            AssetClass("invalid")


@pytest.mark.unit
class TestInstrumentQuery:
    """测试 InstrumentQuery 查询参数模型."""

    def test_default_values(self) -> None:
        """验证默认值: asset_class=None, exchange=None, is_active=None, limit=100."""
        from ditto_port.models.metadata import InstrumentQuery

        query = InstrumentQuery()
        assert query.asset_class is None
        assert query.exchange is None
        assert query.is_active is None
        assert query.limit == 100

    def test_custom_values(self) -> None:
        """验证自定义查询参数."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import InstrumentQuery

        query = InstrumentQuery(
            asset_class=AssetClass.STOCK,
            exchange="SSE",
            is_active=True,
            limit=50,
        )
        assert query.asset_class == AssetClass.STOCK
        assert query.exchange == "SSE"
        assert query.is_active is True
        assert query.limit == 50

    def test_limit_minimum_value(self) -> None:
        """验证 limit 最小值为 1."""
        from ditto_port.models.metadata import InstrumentQuery

        # 边界值: 1 应该有效
        query = InstrumentQuery(limit=1)
        assert query.limit == 1

        # 0 应该无效
        with pytest.raises(ValidationError) as exc_info:
            InstrumentQuery(limit=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_limit_maximum_value(self) -> None:
        """验证 limit 最大值为 1000."""
        from ditto_port.models.metadata import InstrumentQuery

        # 边界值: 1000 应该有效
        query = InstrumentQuery(limit=1000)
        assert query.limit == 1000

        # 1001 应该无效
        with pytest.raises(ValidationError) as exc_info:
            InstrumentQuery(limit=1001)
        assert "less than or equal to 1000" in str(exc_info.value)


@pytest.mark.unit
class TestInstrument:
    """测试 Instrument 响应模型."""

    def test_basic_instrument(self) -> None:
        """验证基本 Instrument 创建."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import Instrument

        instrument = Instrument(
            instrument_id=1,
            ticker="600000",
            name="浦发银行",
            asset_class=AssetClass.STOCK,
            exchange="SSE",
            list_date="1999-11-10",
            is_active=True,
        )

        assert instrument.instrument_id == 1
        assert instrument.ticker == "600000"
        assert instrument.name == "浦发银行"
        assert instrument.asset_class == AssetClass.STOCK
        assert instrument.exchange == "SSE"
        assert instrument.list_date == "1999-11-10"
        assert instrument.is_active is True

    def test_instrument_with_optional_fields(self) -> None:
        """验证可选字段."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import Instrument

        # list_date 可以为 None
        instrument = Instrument(
            instrument_id=2,
            ticker="000001",
            name="平安银行",
            asset_class=AssetClass.STOCK,
            exchange="SZSE",
            list_date=None,
            is_active=True,
        )

        assert instrument.list_date is None

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import Instrument

        instrument = Instrument(
            instrument_id=1,
            ticker="600000",
            name="浦发银行",
            asset_class=AssetClass.STOCK,
            exchange="SSE",
            list_date="1999-11-10",
            is_active=True,
        )

        data = instrument.model_dump()
        assert data["instrument_id"] == 1
        assert data["ticker"] == "600000"
        assert data["name"] == "浦发银行"
        assert data["asset_class"] == AssetClass.STOCK
        assert data["exchange"] == "SSE"
        assert data["list_date"] == "1999-11-10"
        assert data["is_active"] is True


@pytest.mark.unit
class TestToInstrument:
    """测试 to_instrument 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import to_instrument

        row: dict[str, Any] = {
            "instrument_id": 1,
            "ticker": "600000",
            "name": "浦发银行",
            "asset_class": "stock",
            "exchange": "SSE",
            "list_date": "1999-11-10",
            "is_active": 1,
        }

        instrument = to_instrument(row)

        assert instrument.instrument_id == 1
        assert instrument.ticker == "600000"
        assert instrument.name == "浦发银行"
        assert instrument.asset_class == AssetClass.STOCK
        assert instrument.exchange == "SSE"
        assert instrument.list_date == "1999-11-10"
        assert instrument.is_active is True

    def test_convert_with_missing_optional_fields(self) -> None:
        """验证可选字段缺失时的转换."""
        from ditto_port.models.metadata import to_instrument

        row: dict[str, Any] = {
            "instrument_id": 2,
            "ticker": "000001",
            "name": "平安银行",
            "asset_class": "stock",
            "exchange": "SZSE",
            "list_date": None,
            "is_active": 1,
        }

        instrument = to_instrument(row)

        assert instrument.list_date is None
        assert instrument.is_active is True

    def test_convert_with_boolean_is_active(self) -> None:
        """验证 is_active 为布尔值时的转换."""
        from ditto_port.models.metadata import to_instrument

        row: dict[str, Any] = {
            "instrument_id": 1,
            "ticker": "600000",
            "name": "浦发银行",
            "asset_class": "stock",
            "exchange": "SSE",
            "list_date": "1999-11-10",
            "is_active": True,
        }

        instrument = to_instrument(row)
        assert instrument.is_active is True

    def test_convert_inactive_instrument(self) -> None:
        """验证非活跃证券转换."""
        from ditto_port.models.metadata import to_instrument

        row: dict[str, Any] = {
            "instrument_id": 1,
            "ticker": "600000",
            "name": "浦发银行",
            "asset_class": "stock",
            "exchange": "SSE",
            "list_date": "1999-11-10",
            "is_active": 0,
        }

        instrument = to_instrument(row)
        assert instrument.is_active is False


@pytest.mark.unit
class TestToInstrumentList:
    """测试 to_instrument_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_port.models.metadata import to_instrument_list

        df = pl.DataFrame()
        result = to_instrument_list(df)
        assert result == []

    def test_convert_single_row_dataframe(self) -> None:
        """验证单行 DataFrame 转换."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import to_instrument_list

        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": ["1999-11-10"],
                "is_active": [1],
            }
        )

        result = to_instrument_list(df)

        assert len(result) == 1
        assert result[0].instrument_id == 1
        assert result[0].ticker == "600000"
        assert result[0].asset_class == AssetClass.STOCK

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_kernel.enums import AssetClass
        from ditto_port.models.metadata import to_instrument_list

        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "ticker": ["600000", "000001", "000300"],
                "name": ["浦发银行", "平安银行", "沪深300"],
                "asset_class": ["stock", "stock", "index"],
                "exchange": ["SSE", "SZSE", "SSE"],
                "list_date": ["1999-11-10", "1991-04-03", "2005-04-08"],
                "is_active": [1, 1, 1],
            }
        )

        result = to_instrument_list(df)

        assert len(result) == 3
        assert result[0].asset_class == AssetClass.STOCK
        assert result[1].asset_class == AssetClass.STOCK
        assert result[2].asset_class == AssetClass.INDEX

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的 DataFrame 转换."""
        from ditto_port.models.metadata import to_instrument_list

        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": [None],
                "is_active": [1],
            }
        )

        result = to_instrument_list(df)

        assert len(result) == 1
        assert result[0].list_date is None
