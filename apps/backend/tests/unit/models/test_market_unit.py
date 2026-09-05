"""Tests for Market domain models.

Adjustment, BarsQuery, Bar, to_bar, to_bar_list.
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestAdjustment:
    """测试 Adjustment 枚举."""

    def test_adjustment_values(self) -> None:
        """验证 Adjustment 包含 none, qfq, hfq."""
        from ditto_apps.models.market import Adjustment

        assert Adjustment.NONE.value == "none"
        assert Adjustment.QFQ.value == "qfq"
        assert Adjustment.HFQ.value == "hfq"

    def test_adjustment_from_string(self) -> None:
        """验证可以从字符串创建 Adjustment."""
        from ditto_apps.models.market import Adjustment

        assert Adjustment("none") == Adjustment.NONE
        assert Adjustment("qfq") == Adjustment.QFQ
        assert Adjustment("hfq") == Adjustment.HFQ

    def test_adjustment_invalid_value(self) -> None:
        """验证无效值会抛出异常."""
        from ditto_apps.models.market import Adjustment

        with pytest.raises(ValueError):
            Adjustment("invalid")


@pytest.mark.unit
class TestBarsQuery:
    """测试 BarsQuery 查询参数模型."""

    def test_default_values(self) -> None:
        """验证默认值: instrument_ids=None, start_date=None, end_date=None, adjustment=none, limit=1000."""  # noqa: E501
        from ditto_apps.models.market import Adjustment, BarsQuery

        query = BarsQuery()
        assert query.instrument_ids is None
        assert query.start_date is None
        assert query.end_date is None
        assert query.adjustment == Adjustment.NONE
        assert query.limit == 1000
        assert query.asset_class is None
        assert query.allow_experimental_data is False

    def test_custom_values(self) -> None:
        """验证自定义查询参数."""
        from ditto_apps.models.market import Adjustment, BarsQuery

        query = BarsQuery(
            instrument_ids=[1, 2, 3],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            adjustment=Adjustment.QFQ,
            limit=500,
            asset_class="stock",
            allow_experimental_data=True,
        )
        assert query.instrument_ids == [1, 2, 3]
        assert query.start_date == date(2024, 1, 1)
        assert query.end_date == date(2024, 1, 31)
        assert query.adjustment == Adjustment.QFQ
        assert query.limit == 500
        assert query.asset_class == "stock"
        assert query.allow_experimental_data is True

    def test_date_range_validation_success(self) -> None:
        """验证日期范围校验成功: start_date <= end_date."""
        from ditto_apps.models.market import BarsQuery

        # start_date == end_date 应该有效
        query = BarsQuery(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )
        assert query.start_date == date(2024, 1, 15)
        assert query.end_date == date(2024, 1, 15)

        # start_date < end_date 应该有效
        query2 = BarsQuery(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert query2.start_date == date(2024, 1, 1)
        assert query2.end_date == date(2024, 1, 31)

    def test_date_range_validation_failure(self) -> None:
        """验证日期范围校验失败: start_date > end_date."""
        from ditto_apps.models.market import BarsQuery

        with pytest.raises(ValidationError) as exc_info:
            BarsQuery(
                start_date=date(2024, 1, 31),
                end_date=date(2024, 1, 1),
            )
        assert "start_date" in str(exc_info.value).lower()
        assert "end_date" in str(exc_info.value).lower()

    def test_only_start_date_provided(self) -> None:
        """验证只提供 start_date 时校验通过."""
        from ditto_apps.models.market import BarsQuery

        query = BarsQuery(start_date=date(2024, 1, 1))
        assert query.start_date == date(2024, 1, 1)
        assert query.end_date is None

    def test_only_end_date_provided(self) -> None:
        """验证只提供 end_date 时校验通过."""
        from ditto_apps.models.market import BarsQuery

        query = BarsQuery(end_date=date(2024, 1, 31))
        assert query.start_date is None
        assert query.end_date == date(2024, 1, 31)

    def test_limit_minimum_value(self) -> None:
        """验证 limit 最小值为 1."""
        from ditto_apps.models.market import BarsQuery

        # 边界值: 1 应该有效
        query = BarsQuery(limit=1)
        assert query.limit == 1

        # 0 应该无效
        with pytest.raises(ValidationError) as exc_info:
            BarsQuery(limit=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_limit_maximum_value(self) -> None:
        """验证 limit 最大值为 10000."""
        from ditto_apps.models.market import BarsQuery

        # 边界值: 10000 应该有效
        query = BarsQuery(limit=10000)
        assert query.limit == 10000

        # 10001 应该无效
        with pytest.raises(ValidationError) as exc_info:
            BarsQuery(limit=10001)
        assert "less than or equal to 10000" in str(exc_info.value)


@pytest.mark.unit
class TestBar:
    """测试 Bar 响应模型."""

    def test_basic_bar(self) -> None:
        """验证基本 Bar 创建."""
        from ditto_apps.models.market import Bar

        bar = Bar(
            instrument_id=1,
            trade_date="2024-01-15",
            open=10.0,
            high=11.0,
            low=9.5,
            close=10.5,
            volume=1000000,
            amount=10500000.0,
        )

        assert bar.instrument_id == 1
        assert bar.trade_date == "2024-01-15"
        assert bar.open == 10.0
        assert bar.high == 11.0
        assert bar.low == 9.5
        assert bar.close == 10.5
        assert bar.volume == 1000000
        assert bar.amount == 10500000.0

    def test_bar_with_turnover_rate(self) -> None:
        """验证带换手率的 Bar."""
        from ditto_apps.models.market import Bar

        bar = Bar(
            instrument_id=1,
            trade_date="2024-01-15",
            open=10.0,
            high=11.0,
            low=9.5,
            close=10.5,
            volume=1000000,
            amount=10500000.0,
            turnover_rate=0.025,
        )

        assert bar.turnover_rate == 0.025

    def test_bar_with_optional_fields_none(self) -> None:
        """验证可选字段为 None."""
        from ditto_apps.models.market import Bar

        bar = Bar(
            instrument_id=1,
            trade_date="2024-01-15",
            open=10.0,
            high=11.0,
            low=9.5,
            close=10.5,
            volume=1000000,
            amount=10500000.0,
            turnover_rate=None,
        )

        assert bar.turnover_rate is None

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_apps.models.market import Bar

        bar = Bar(
            instrument_id=1,
            trade_date="2024-01-15",
            open=10.0,
            high=11.0,
            low=9.5,
            close=10.5,
            volume=1000000,
            amount=10500000.0,
        )

        data = bar.model_dump()
        assert data["instrument_id"] == 1
        assert data["trade_date"] == "2024-01-15"
        assert data["open"] == 10.0
        assert data["high"] == 11.0
        assert data["low"] == 9.5
        assert data["close"] == 10.5
        assert data["volume"] == 1000000
        assert data["amount"] == 10500000.0


@pytest.mark.unit
class TestToBar:
    """测试 to_bar 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_apps.models.market import to_bar

        row: dict[str, Any] = {
            "instrument_id": 1,
            "trade_date": "2024-01-15",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000000,
            "amount": 10500000.0,
            "turnover_rate": 0.0256,
        }

        bar = to_bar(row)

        assert bar.instrument_id == 1
        assert bar.trade_date == "2024-01-15"
        assert bar.open == 10.0
        assert bar.high == 11.0
        assert bar.low == 9.5
        assert bar.close == 10.5
        assert bar.volume == 1000000
        assert bar.amount == 10500000.0
        assert bar.turnover_rate == 0.03  # 四舍五入到 2 位小数

    def test_convert_with_missing_optional_fields(self) -> None:
        """验证可选字段缺失时的转换."""
        from ditto_apps.models.market import to_bar

        row: dict[str, Any] = {
            "instrument_id": 1,
            "trade_date": "2024-01-15",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000000,
            "amount": 10500000.0,
        }

        bar = to_bar(row)

        assert bar.turnover_rate is None

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的转换."""
        from ditto_apps.models.market import to_bar

        row: dict[str, Any] = {
            "instrument_id": 1,
            "trade_date": "2024-01-15",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000000,
            "amount": 10500000.0,
            "turnover_rate": None,
        }

        bar = to_bar(row)
        assert bar.turnover_rate is None


@pytest.mark.unit
class TestToBarList:
    """测试 to_bar_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_apps.models.market import to_bar_list

        df = pl.DataFrame()
        result = to_bar_list(df)
        assert result == []

    def test_convert_single_row_dataframe(self) -> None:
        """验证单行 DataFrame 转换."""
        from ditto_apps.models.market import to_bar_list

        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-15"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000000],
                "amount": [10500000.0],
            }
        )

        result = to_bar_list(df)

        assert len(result) == 1
        assert result[0].instrument_id == 1
        assert result[0].trade_date == "2024-01-15"

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_apps.models.market import to_bar_list

        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2],
                "trade_date": ["2024-01-15", "2024-01-16", "2024-01-15"],
                "open": [10.0, 10.5, 20.0],
                "high": [11.0, 11.5, 21.0],
                "low": [9.5, 10.0, 19.5],
                "close": [10.5, 11.0, 20.5],
                "volume": [1000000, 1100000, 2000000],
                "amount": [10500000.0, 11550000.0, 41000000.0],
            }
        )

        result = to_bar_list(df)

        assert len(result) == 3
        assert result[0].instrument_id == 1
        assert result[1].instrument_id == 1
        assert result[2].instrument_id == 2

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的 DataFrame 转换."""
        from ditto_apps.models.market import to_bar_list

        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-15"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000000],
                "amount": [10500000.0],
                "turnover_rate": [None],
            }
        )

        result = to_bar_list(df)

        assert len(result) == 1
        assert result[0].turnover_rate is None
