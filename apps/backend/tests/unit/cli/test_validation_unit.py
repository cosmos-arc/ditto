"""参数验证工具单元测试."""

import pytest
import typer
from ditto_apps.cli.utils.validation import (
    validate_date_format,
    validate_instrument_params,
)


class TestValidateDateFormat:
    """日期格式验证测试."""

    @pytest.mark.unit
    def test_valid(self):
        """测试有效日期格式"""
        validate_date_format("2024-01-02")

    @pytest.mark.unit
    def test_invalid_separator(self):
        """测试无效日期分隔符"""
        with pytest.raises(typer.Exit):
            validate_date_format("2024/01/02")

    @pytest.mark.unit
    def test_invalid_format(self):
        """测试无效日期格式"""
        with pytest.raises(typer.Exit):
            validate_date_format("20240102")

    @pytest.mark.unit
    def test_invalid_date(self):
        """测试无效日期"""
        with pytest.raises(typer.Exit):
            validate_date_format("2024-13-01")  # 无效月份

        with pytest.raises(typer.Exit):
            validate_date_format("2024-01-32")  # 无效日期

    @pytest.mark.unit
    def test_leap_year(self):
        """测试闰年日期"""
        validate_date_format("2024-02-29")  # 2024 是闰年

        with pytest.raises(typer.Exit):
            validate_date_format("2023-02-29")  # 2023 不是闰年


class TestValidateInstrumentParams:
    """标识符参数验证测试."""

    @pytest.mark.unit
    def test_date_range_valid(self):
        """测试有效的日期范围（start <= end）"""
        # 不应抛出异常
        validate_instrument_params(
            date=None,
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            start="2024-01-01",
            end="2024-01-31",
        )

    @pytest.mark.unit
    def test_date_range_equal(self):
        """测试相等的日期范围（start == end）"""
        # 不应抛出异常
        validate_instrument_params(
            date=None,
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            start="2024-01-15",
            end="2024-01-15",
        )

    @pytest.mark.unit
    def test_date_range_invalid(self):
        """测试无效的日期范围（start > end）"""
        with pytest.raises(typer.BadParameter, match="不能晚于"):
            validate_instrument_params(
                date=None,
                ticker="000001",
                standard_ticker=None,
                instrument_id=None,
                start="2024-12-31",
                end="2024-01-01",
            )
