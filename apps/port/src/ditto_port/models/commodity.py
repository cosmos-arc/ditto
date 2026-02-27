"""
Commodity (商品) 域 API 模型.

包含:
- CommodityBar: 商品 K 线响应模型
- CommodityQuery: 查询参数模型
- to_commodity_bar: 转换函数
- to_commodity_bar_list: 批量转换函数
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Self

import polars as pl
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


# 支持从 JSON 字符串解析日期的类型
DateField = Annotated[date | None, BeforeValidator(_parse_date)]


class CommodityQuery(BaseModel):
    """
    商品 K 线查询参数模型.

    Attributes:
        symbols: 商品代码列表 (可选, 如 ["AU", "AG", "CU"])
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        limit: 返回数量限制, 默认 1000, 范围 1-10000

    """

    symbols: list[str] | None = Field(default=None, description="商品代码列表")
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
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


class CommodityBar(BaseModel):
    """
    商品 K 线响应模型.

    Attributes:
        symbol: 商品代码 (如 AU 表示黄金)
        trade_date_utc: 交易日期 (UTC, YYYY-MM-DD)
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量 (可选)

    """

    symbol: str = Field(description="商品代码")
    trade_date_utc: str = Field(description="交易日期 (UTC)")
    open: float = Field(description="开盘价")
    high: float = Field(description="最高价")
    low: float = Field(description="最低价")
    close: float = Field(description="收盘价")
    volume: float | None = Field(default=None, description="成交量")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def _format_float(value: float | None, decimals: int = 4) -> float | None:
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


def to_commodity_bar(row: dict[str, Any]) -> CommodityBar:
    """
    将数据库行转换为 CommodityBar 模型.

    Args:
        row: 数据库行字典，包含 symbol, trade_date_utc, open, high, low, close,
             volume 等字段

    Returns:
        CommodityBar 模型实例

    """
    return CommodityBar(
        symbol=row["symbol"],
        trade_date_utc=_format_date(row["trade_date_utc"]) or "",
        open=_format_float(row["open"]) or 0.0,
        high=_format_float(row["high"]) or 0.0,
        low=_format_float(row["low"]) or 0.0,
        close=_format_float(row["close"]) or 0.0,
        volume=_format_float(row.get("volume")),
    )


def to_commodity_bar_list(df: pl.DataFrame) -> list[CommodityBar]:
    """
    将 DataFrame 转换为 CommodityBar 列表.

    Args:
        df: 包含商品 K 线数据的 DataFrame

    Returns:
        CommodityBar 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[CommodityBar] = []
    for row in df.to_dicts():
        result.append(to_commodity_bar(row))

    return result


__all__ = [
    "CommodityBar",
    "CommodityQuery",
    "to_commodity_bar",
    "to_commodity_bar_list",
]
