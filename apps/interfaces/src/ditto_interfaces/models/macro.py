"""
Macro 域 API 模型.

包含:
- IndicatorQuery: 查询参数模型
- Indicator: 响应模型
- to_indicator: 转换函数
- to_indicator_list: 批量转换函数
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Self

import polars as pl
from ditto_datahub.models import MacroCategory, MacroFrequency
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def _parse_date(v: Any) -> date | None:
    """解析日期值，支持字符串和 date 对象."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v)
    raise ValueError(f"Invalid date format: {v}")


def _parse_category(v: Any) -> MacroCategory | None:
    """解析 MacroCategory，支持字符串和 MacroCategory 对象."""
    if v is None:
        return None
    if isinstance(v, MacroCategory):
        return v
    if isinstance(v, str):
        return MacroCategory(v)
    raise ValueError(f"Invalid category: {v}")


def _parse_frequency(v: Any) -> MacroFrequency | None:
    """解析 MacroFrequency，支持字符串和 MacroFrequency 对象."""
    if v is None:
        return None
    if isinstance(v, MacroFrequency):
        return v
    if isinstance(v, str):
        return MacroFrequency(v)
    raise ValueError(f"Invalid frequency: {v}")


# 支持从 JSON 字符串解析日期的类型
DateField = Annotated[date | None, BeforeValidator(_parse_date)]
# 支持从 JSON 字符串解析 MacroCategory
CategoryField = Annotated[MacroCategory | None, BeforeValidator(_parse_category)]
# 支持从 JSON 字符串解析 MacroFrequency
FrequencyField = Annotated[MacroFrequency | None, BeforeValidator(_parse_frequency)]


class IndicatorQuery(BaseModel):
    """
    宏观指标查询参数模型.

    Attributes:
        indicators: 指标 ID 或代码列表 (可选)
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        category: 类别过滤 (可选)
        frequency: 频率过滤 (可选)

    """

    indicators: list[int] | list[str] | None = Field(
        default=None, description="指标 ID 或代码列表"
    )
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
    category: CategoryField = Field(default=None, description="类别过滤")
    frequency: FrequencyField = Field(default=None, description="频率过滤")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """
        验证日期范围: start_date <= end_date.

        如果只提供了一个日期，则跳过校验。

        Raises:
            ValueError: 如果 start_date > end_date

        """
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            msg = (
                f"start_date ({self.start_date}) cannot be greater than "
                f"end_date ({self.end_date})"
            )
            raise ValueError(msg)
        return self


class Indicator(BaseModel):
    """
    宏观指标响应模型.

    Attributes:
        indicator_id: 指标 ID
        code: 指标代码
        name: 指标名称
        category: 类别
        frequency: 频率
        date: 数据日期
        value: 指标值
        unit: 单位 (可选)

    """

    indicator_id: int = Field(description="指标 ID")
    code: str = Field(description="指标代码")
    name: str = Field(description="指标名称")
    category: MacroCategory = Field(description="类别")
    frequency: MacroFrequency = Field(description="频率")
    date: str = Field(description="数据日期")
    value: float = Field(description="指标值")
    unit: str | None = Field(default=None, description="单位")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_indicator(row: dict[str, Any]) -> Indicator:
    """
    将数据库行转换为 Indicator 模型.

    Args:
        row: 数据库行字典，包含 indicator_id, code, name, category, frequency,
             date, value, unit 等字段

    Returns:
        Indicator 模型实例

    """
    # 处理 date 字段：可能是 date 对象或字符串
    date_raw = row.get("date")
    if isinstance(date_raw, date):
        date_str = date_raw.isoformat()
    elif date_raw is not None:
        date_str = str(date_raw)
    else:
        date_str = ""

    return Indicator(
        indicator_id=row["indicator_id"],
        code=row["code"],
        name=row["name"],
        category=MacroCategory(row["category"]),
        frequency=MacroFrequency(row["frequency"]),
        date=date_str,
        value=row["value"],
        unit=row.get("unit"),
    )


def to_indicator_list(df: pl.DataFrame) -> list[Indicator]:
    """
    将 DataFrame 转换为 Indicator 列表.

    Args:
        df: 包含宏观指标数据的 DataFrame

    Returns:
        Indicator 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Indicator] = []
    for row in df.to_dicts():
        result.append(to_indicator(row))

    return result


__all__ = [
    "Indicator",
    "IndicatorQuery",
    "to_indicator",
    "to_indicator_list",
]
