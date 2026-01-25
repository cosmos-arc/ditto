"""参数验证工具单元测试."""

import pytest
import typer
from ditto_port.cli.utils.validation import validate_date_format


@pytest.mark.unit
def test_validate_date_format_valid():
    """测试有效日期格式"""
    # 不应抛出异常
    validate_date_format("2024-01-02")


@pytest.mark.unit
def test_validate_date_format_invalid_separator():
    """测试无效日期分隔符"""
    with pytest.raises(typer.Exit):
        validate_date_format("2024/01/02")


@pytest.mark.unit
def test_validate_date_format_invalid_format():
    """测试无效日期格式"""
    with pytest.raises(typer.Exit):
        validate_date_format("20240102")


@pytest.mark.unit
def test_validate_date_format_invalid_date():
    """测试无效日期"""
    with pytest.raises(typer.Exit):
        validate_date_format("2024-13-01")  # 无效月份

    with pytest.raises(typer.Exit):
        validate_date_format("2024-01-32")  # 无效日期


@pytest.mark.unit
def test_validate_date_format_leap_year():
    """测试闰年日期"""
    # 有效闰年日期
    validate_date_format("2024-02-29")  # 2024 是闰年

    # 无效闰年日期
    with pytest.raises(typer.Exit):
        validate_date_format("2023-02-29")  # 2023 不是闰年
