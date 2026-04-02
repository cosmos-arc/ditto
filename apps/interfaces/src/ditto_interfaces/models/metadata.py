"""
Metadata 域 API 模型.

包含:
- InstrumentQuery: 查询参数模型
- Instrument: 响应模型
- to_instrument: 转换函数
- to_instrument_list: 批量转换函数
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_kernel.enums import AssetClass
from ditto_kernel.identity import InstrumentId
from pydantic import BaseModel, ConfigDict, Field


class InstrumentQuery(BaseModel):
    """
    标的查询参数模型.

    Attributes:
        asset_class: 资产类别过滤 (可选)
        exchange: 交易所过滤 (可选)
        is_active: 活跃状态过滤 (可选)
        limit: 返回数量限制, 默认 100, 范围 1-1000

    """

    asset_class: AssetClass | None = Field(default=None, description="资产类别过滤")
    exchange: str | None = Field(default=None, description="交易所过滤")
    is_active: bool | None = Field(default=None, description="活跃状态过滤")
    limit: int = Field(default=100, ge=1, le=1000, description="返回数量限制")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Instrument(BaseModel):
    """
    标的响应模型.

    Attributes:
        instrument_id: 标的 ID
        ticker: 裸代码 (如 600000)
        name: 证券名称
        asset_class: 资产类别
        exchange: 交易所代码
        list_date: 上市日期 (可选)
        is_active: 是否活跃

    """

    instrument_id: InstrumentId = Field(description="标的 ID")
    ticker: str = Field(description="裸代码")
    name: str = Field(description="证券名称")
    asset_class: AssetClass = Field(description="资产类别")
    exchange: str = Field(description="交易所代码")
    list_date: str | None = Field(default=None, description="上市日期")
    is_active: bool = Field(description="是否活跃")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_instrument(row: dict[str, Any]) -> Instrument:
    """
    将数据库行转换为 Instrument 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, ticker, name, asset_class,
             exchange, list_date, is_active 等字段

    Returns:
        Instrument 模型实例

    """
    # 处理 is_active 字段：数据库中可能存储为 0/1 或 True/False
    is_active_raw = row.get("is_active")
    is_active = bool(is_active_raw) if is_active_raw is not None else True

    return Instrument(
        instrument_id=InstrumentId(row["instrument_id"]),
        ticker=row["ticker"],
        name=row["name"],
        asset_class=AssetClass(row["asset_class"]),
        exchange=row["exchange"],
        list_date=row.get("list_date"),
        is_active=is_active,
    )


def to_instrument_list(df: pl.DataFrame) -> list[Instrument]:
    """
    将 DataFrame 转换为 Instrument 列表.

    Args:
        df: 包含标的数据的 DataFrame

    Returns:
        Instrument 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Instrument] = []
    for row in df.to_dicts():
        result.append(to_instrument(row))

    return result


__all__ = [
    "Instrument",
    "InstrumentQuery",
    "to_instrument",
    "to_instrument_list",
]
