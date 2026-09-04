"""Tests for Macro domain models.

MacroCategory, MacroFrequency, IndicatorQuery, Indicator,
to_indicator, to_indicator_list.
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from pydantic import ValidationError


@pytest.mark.unit
class TestMacroCategory:
    """测试 MacroCategory 枚举."""

    def test_category_values(self) -> None:
        """验证 MacroCategory 包含四种类别."""
        from ditto_apps.models.macro import MacroCategory

        assert MacroCategory.ECONOMIC.value == "economic"
        assert MacroCategory.INTEREST_RATE.value == "interest_rate"
        assert MacroCategory.EXCHANGE_RATE.value == "exchange_rate"
        assert MacroCategory.MONEY_SUPPLY.value == "money_supply"

    def test_category_from_string(self) -> None:
        """验证可以从字符串创建 MacroCategory."""
        from ditto_apps.models.macro import MacroCategory

        assert MacroCategory("economic") == MacroCategory.ECONOMIC
        assert MacroCategory("interest_rate") == MacroCategory.INTEREST_RATE
        assert MacroCategory("exchange_rate") == MacroCategory.EXCHANGE_RATE
        assert MacroCategory("money_supply") == MacroCategory.MONEY_SUPPLY

    def test_category_invalid_value(self) -> None:
        """验证无效值会抛出异常."""
        from ditto_apps.models.macro import MacroCategory

        with pytest.raises(ValueError):
            MacroCategory("invalid")


@pytest.mark.unit
class TestMacroFrequency:
    """测试 MacroFrequency 枚举."""

    def test_frequency_values(self) -> None:
        """验证 MacroFrequency 包含 daily, monthly, quarterly."""
        from ditto_apps.models.macro import MacroFrequency

        assert MacroFrequency.DAILY.value == "daily"
        assert MacroFrequency.MONTHLY.value == "monthly"
        assert MacroFrequency.QUARTERLY.value == "quarterly"

    def test_frequency_from_string(self) -> None:
        """验证可以从字符串创建 MacroFrequency."""
        from ditto_apps.models.macro import MacroFrequency

        assert MacroFrequency("daily") == MacroFrequency.DAILY
        assert MacroFrequency("monthly") == MacroFrequency.MONTHLY
        assert MacroFrequency("quarterly") == MacroFrequency.QUARTERLY

    def test_frequency_invalid_value(self) -> None:
        """验证无效值会抛出异常."""
        from ditto_apps.models.macro import MacroFrequency

        with pytest.raises(ValueError):
            MacroFrequency("invalid")


@pytest.mark.unit
class TestIndicatorQuery:
    """测试 IndicatorQuery 查询参数模型."""

    def test_default_values(self) -> None:
        """验证默认值: indicators=None, start_date=None, end_date=None, category=None, frequency=None."""  # noqa: E501
        from ditto_apps.models.macro import IndicatorQuery

        query = IndicatorQuery()
        assert query.indicators is None
        assert query.start_date is None
        assert query.end_date is None
        assert query.category is None
        assert query.frequency is None

    def test_custom_values_with_indicator_ids(self) -> None:
        """验证自定义查询参数（使用 ID 列表）."""
        from ditto_apps.models.macro import (
            IndicatorQuery,
            MacroCategory,
            MacroFrequency,
        )

        query = IndicatorQuery(
            indicators=[1, 2, 3],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            category=MacroCategory.ECONOMIC,
            frequency=MacroFrequency.MONTHLY,
        )
        assert query.indicators == [1, 2, 3]
        assert query.start_date == date(2024, 1, 1)
        assert query.end_date == date(2024, 12, 31)
        assert query.category == MacroCategory.ECONOMIC
        assert query.frequency == MacroFrequency.MONTHLY

    def test_custom_values_with_indicator_codes(self) -> None:
        """验证自定义查询参数（使用代码列表）."""
        from ditto_apps.models.macro import IndicatorQuery

        query = IndicatorQuery(
            indicators=["GDP", "CPI", "PPI"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert query.indicators == ["GDP", "CPI", "PPI"]

    def test_date_range_validation_success(self) -> None:
        """验证日期范围校验成功: start_date <= end_date."""
        from ditto_apps.models.macro import IndicatorQuery

        # start_date == end_date 应该有效
        query = IndicatorQuery(
            start_date=date(2024, 6, 15),
            end_date=date(2024, 6, 15),
        )
        assert query.start_date == date(2024, 6, 15)
        assert query.end_date == date(2024, 6, 15)

        # start_date < end_date 应该有效
        query2 = IndicatorQuery(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert query2.start_date == date(2024, 1, 1)
        assert query2.end_date == date(2024, 12, 31)

    def test_date_range_validation_failure(self) -> None:
        """验证日期范围校验失败: start_date > end_date."""
        from ditto_apps.models.macro import IndicatorQuery

        with pytest.raises(ValidationError) as exc_info:
            IndicatorQuery(
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
            )
        assert "start_date" in str(exc_info.value).lower()
        assert "end_date" in str(exc_info.value).lower()

    def test_only_start_date_provided(self) -> None:
        """验证只提供 start_date 时校验通过."""
        from ditto_apps.models.macro import IndicatorQuery

        query = IndicatorQuery(start_date=date(2024, 1, 1))
        assert query.start_date == date(2024, 1, 1)
        assert query.end_date is None

    def test_only_end_date_provided(self) -> None:
        """验证只提供 end_date 时校验通过."""
        from ditto_apps.models.macro import IndicatorQuery

        query = IndicatorQuery(end_date=date(2024, 12, 31))
        assert query.start_date is None
        assert query.end_date == date(2024, 12, 31)


@pytest.mark.unit
class TestIndicator:
    """测试 Indicator 响应模型."""

    def test_basic_indicator(self) -> None:
        """验证基本 Indicator 创建."""
        from ditto_apps.models.macro import (
            Indicator,
            MacroCategory,
            MacroFrequency,
        )

        indicator = Indicator(
            indicator_id=1,
            code="GDP",
            name="国内生产总值",
            category=MacroCategory.ECONOMIC,
            frequency=MacroFrequency.QUARTERLY,
            date="2024-03-31",
            value=296299.0,
            unit="亿元",
        )

        assert indicator.indicator_id == 1
        assert indicator.code == "GDP"
        assert indicator.name == "国内生产总值"
        assert indicator.category == MacroCategory.ECONOMIC
        assert indicator.frequency == MacroFrequency.QUARTERLY
        assert indicator.date == "2024-03-31"
        assert indicator.value == 296299.0
        assert indicator.unit == "亿元"

    def test_indicator_with_optional_fields_none(self) -> None:
        """验证可选字段为 None."""
        from ditto_apps.models.macro import (
            Indicator,
            MacroCategory,
            MacroFrequency,
        )

        indicator = Indicator(
            indicator_id=1,
            code="GDP",
            name="国内生产总值",
            category=MacroCategory.ECONOMIC,
            frequency=MacroFrequency.QUARTERLY,
            date="2024-03-31",
            value=296299.0,
            unit=None,
        )

        assert indicator.unit is None

    def test_model_dump(self) -> None:
        """验证 model_dump 序列化."""
        from ditto_apps.models.macro import (
            Indicator,
            MacroCategory,
            MacroFrequency,
        )

        indicator = Indicator(
            indicator_id=1,
            code="GDP",
            name="国内生产总值",
            category=MacroCategory.ECONOMIC,
            frequency=MacroFrequency.QUARTERLY,
            date="2024-03-31",
            value=296299.0,
            unit="亿元",
        )

        data = indicator.model_dump()
        assert data["indicator_id"] == 1
        assert data["code"] == "GDP"
        assert data["name"] == "国内生产总值"
        assert data["category"] == MacroCategory.ECONOMIC
        assert data["frequency"] == MacroFrequency.QUARTERLY
        assert data["date"] == "2024-03-31"
        assert data["value"] == 296299.0
        assert data["unit"] == "亿元"


@pytest.mark.unit
class TestToIndicator:
    """测试 to_indicator 转换函数."""

    def test_convert_complete_row(self) -> None:
        """验证完整行转换."""
        from ditto_apps.models.macro import (
            MacroCategory,
            MacroFrequency,
            to_indicator,
        )

        row: dict[str, Any] = {
            "indicator_id": 1,
            "code": "GDP",
            "name": "国内生产总值",
            "category": "economic",
            "frequency": "quarterly",
            "date": "2024-03-31",
            "value": 296299.0,
            "unit": "亿元",
        }

        indicator = to_indicator(row)

        assert indicator.indicator_id == 1
        assert indicator.code == "GDP"
        assert indicator.name == "国内生产总值"
        assert indicator.category == MacroCategory.ECONOMIC
        assert indicator.frequency == MacroFrequency.QUARTERLY
        assert indicator.date == "2024-03-31"
        assert indicator.value == 296299.0
        assert indicator.unit == "亿元"

    def test_convert_with_missing_optional_fields(self) -> None:
        """验证可选字段缺失时的转换."""
        from ditto_apps.models.macro import to_indicator

        row: dict[str, Any] = {
            "indicator_id": 1,
            "code": "GDP",
            "name": "国内生产总值",
            "category": "economic",
            "frequency": "quarterly",
            "date": "2024-03-31",
            "value": 296299.0,
        }

        indicator = to_indicator(row)

        assert indicator.unit is None

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的转换."""
        from ditto_apps.models.macro import to_indicator

        row: dict[str, Any] = {
            "indicator_id": 1,
            "code": "GDP",
            "name": "国内生产总值",
            "category": "economic",
            "frequency": "quarterly",
            "date": "2024-03-31",
            "value": 296299.0,
            "unit": None,
        }

        indicator = to_indicator(row)
        assert indicator.unit is None


@pytest.mark.unit
class TestToIndicatorList:
    """测试 to_indicator_list 转换函数."""

    def test_convert_empty_dataframe(self) -> None:
        """验证空 DataFrame 转换."""
        from ditto_apps.models.macro import to_indicator_list

        df = pl.DataFrame()
        result = to_indicator_list(df)
        assert result == []

    def test_convert_single_row_dataframe(self) -> None:
        """验证单行 DataFrame 转换."""
        from ditto_apps.models.macro import (
            MacroCategory,
            MacroFrequency,
            to_indicator_list,
        )

        df = pl.DataFrame(
            {
                "indicator_id": [1],
                "code": ["GDP"],
                "name": ["国内生产总值"],
                "category": ["economic"],
                "frequency": ["quarterly"],
                "date": ["2024-03-31"],
                "value": [296299.0],
            }
        )

        result = to_indicator_list(df)

        assert len(result) == 1
        assert result[0].indicator_id == 1
        assert result[0].code == "GDP"
        assert result[0].category == MacroCategory.ECONOMIC
        assert result[0].frequency == MacroFrequency.QUARTERLY

    def test_convert_multiple_rows_dataframe(self) -> None:
        """验证多行 DataFrame 转换."""
        from ditto_apps.models.macro import MacroCategory, to_indicator_list

        df = pl.DataFrame(
            {
                "indicator_id": [1, 1, 2],
                "code": ["GDP", "GDP", "CPI"],
                "name": ["国内生产总值", "国内生产总值", "消费者物价指数"],
                "category": ["economic", "economic", "economic"],
                "frequency": ["quarterly", "quarterly", "monthly"],
                "date": ["2024-03-31", "2024-06-30", "2024-06-30"],
                "value": [296299.0, 320000.0, 102.5],
            }
        )

        result = to_indicator_list(df)

        assert len(result) == 3
        assert result[0].indicator_id == 1
        assert result[1].indicator_id == 1
        assert result[2].indicator_id == 2
        assert result[0].category == MacroCategory.ECONOMIC
        assert result[1].category == MacroCategory.ECONOMIC
        assert result[2].category == MacroCategory.ECONOMIC

    def test_convert_with_null_values(self) -> None:
        """验证包含 NULL 值的 DataFrame 转换."""
        from ditto_apps.models.macro import to_indicator_list

        df = pl.DataFrame(
            {
                "indicator_id": [1],
                "code": ["GDP"],
                "name": ["国内生产总值"],
                "category": ["economic"],
                "frequency": ["quarterly"],
                "date": ["2024-03-31"],
                "value": [296299.0],
                "unit": [None],
            }
        )

        result = to_indicator_list(df)

        assert len(result) == 1
        assert result[0].unit is None
