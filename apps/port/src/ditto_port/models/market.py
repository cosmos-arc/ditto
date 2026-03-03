"""
Market 域 API 模型.

包含:
- Adjustment: 复权类型枚举
- BarsQuery: K 线查询参数模型
- Bar: K 线响应模型
- to_bar: 转换函数
- to_bar_list: 批量转换函数
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Self

import polars as pl
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


class Adjustment(StrEnum):
    """
    复权类型枚举.

    Attributes:
        NONE: 不复权
        QFQ: 前复权
        HFQ: 后复权

    """

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


def _parse_date(v: Any) -> date | None:
    """解析日期值，支持字符串和 date 对象."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v)
    raise ValueError(f"Invalid date format: {v}")


def _parse_adjustment(v: Any) -> Adjustment:
    """解析复权类型，支持字符串和 Adjustment 对象."""
    if isinstance(v, Adjustment):
        return v
    if isinstance(v, str):
        return Adjustment(v)
    raise ValueError(f"Invalid adjustment type: {v}")


# 支持从 JSON 字符串解析日期的类型
DateField = Annotated[date | None, BeforeValidator(_parse_date)]
# 支持从 JSON 字符串解析复权类型
AdjustmentField = Annotated[Adjustment, BeforeValidator(_parse_adjustment)]


class BarsQuery(BaseModel):
    """
    K 线查询参数模型.

    Attributes:
        instrument_ids: 标的 ID 列表 (可选)
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        adjustment: 复权类型, 默认 none
        limit: 返回数量限制, 默认 1000, 范围 1-10000

    """

    instrument_ids: list[int] | None = Field(default=None, description="标的 ID 列表")
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
    adjustment: AdjustmentField = Field(default=Adjustment.NONE, description="复权类型")
    limit: int = Field(default=1000, ge=1, le=10000, description="返回数量限制")

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


class Bar(BaseModel):
    """
    K 线响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期 (YYYY-MM-DD)
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量 (保留2位小数)
        amount: 成交额
        turnover_rate: 换手率 (可选)

    """

    instrument_id: int = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    open: float = Field(description="开盘价")
    high: float = Field(description="最高价")
    low: float = Field(description="最低价")
    close: float = Field(description="收盘价")
    volume: float = Field(description="成交量")
    amount: float = Field(description="成交额")
    turnover_rate: float | None = Field(default=None, description="换手率")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def _format_float(value: float | None, decimals: int = 2) -> float | None:
    """格式化浮点数到指定小数位."""
    if value is None:
        return None
    return round(value, decimals)


def _format_date(value: date | str | None) -> str | None:
    """将日期转换为字符串格式 (YYYY-MM-DD)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def to_bar(row: dict[str, Any]) -> Bar:
    """
    将数据库行转换为 Bar 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, open, high, low,
             close, volume, amount, turnover_rate 等字段

    Returns:
        Bar 模型实例

    """
    return Bar(
        instrument_id=row["instrument_id"],
        trade_date=_format_date(row["trade_date"]) or "",
        open=_format_float(row["open"]) or 0.0,
        high=_format_float(row["high"]) or 0.0,
        low=_format_float(row["low"]) or 0.0,
        close=_format_float(row["close"]) or 0.0,
        volume=_format_float(row["volume"]) or 0.0,
        amount=_format_float(row["amount"]) or 0.0,
        turnover_rate=_format_float(row.get("turnover_rate")),
    )


def to_bar_list(df: pl.DataFrame) -> list[Bar]:
    """
    将 DataFrame 转换为 Bar 列表.

    Args:
        df: 包含 K 线数据的 DataFrame

    Returns:
        Bar 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Bar] = []
    for row in df.to_dicts():
        result.append(to_bar(row))

    return result


__all__ = [
    "Adjustment",
    "Bar",
    "BarsQuery",
    "to_bar",
    "to_bar_list",
]
