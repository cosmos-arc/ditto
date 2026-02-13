"""
Capital 域 API 模型.

包含:
- MarginQuery: 融资融券查询参数模型
- Margin: 融资融券响应模型
- ValuationQuery: 估值指标查询参数模型
- Valuation: 估值指标响应模型
- FuturesQuery: 期货查询参数模型
- Futures: 期货响应模型
- 转换函数
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


class MarginQuery(BaseModel):
    """
    融资融券查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    """

    instrument_id: str = Field(description="标的 ID")
    as_of_date: date = Field(description="时间点查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Margin(BaseModel):
    """
    融资融券响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期
        margin_buy_balance: 融资余额
        short_sell_balance: 融券余额
        margin_buy_volume: 融资买入量
        short_sell_volume: 融券卖出量

    """

    instrument_id: str = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    margin_buy_balance: float = Field(description="融资余额")
    short_sell_balance: float = Field(description="融券余额")
    margin_buy_volume: int = Field(description="融资买入量")
    short_sell_volume: int = Field(description="融券卖出量")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_margin(row: dict[str, Any]) -> Margin:
    """
    将数据库行转换为 Margin 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, margin_buy_balance,
             short_sell_balance, margin_buy_volume, short_sell_volume 等字段

    Returns:
        Margin 模型实例

    """
    return Margin(
        instrument_id=row["instrument_id"],
        trade_date=row["trade_date"],
        margin_buy_balance=row["margin_buy_balance"],
        short_sell_balance=row["short_sell_balance"],
        margin_buy_volume=row["margin_buy_volume"],
        short_sell_volume=row["short_sell_volume"],
    )


def to_margin_list(df: pl.DataFrame) -> list[Margin]:
    """
    将 DataFrame 转换为 Margin 列表.

    Args:
        df: 包含融资融券数据的 DataFrame

    Returns:
        Margin 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Margin] = []
    for row in df.to_dicts():
        result.append(to_margin(row))

    return result


class ValuationQuery(BaseModel):
    """
    估值指标查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    """

    instrument_id: str = Field(description="标的 ID")
    as_of_date: date = Field(description="时间点查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Valuation(BaseModel):
    """
    估值指标响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期
        pe_ratio: 市盈率 (可选)
        pb_ratio: 市净率
        ps_ratio: 市销率 (可选)
        dividend_yield: 股息率 (可选)
        market_cap: 市值

    """

    instrument_id: str = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    pe_ratio: float | None = Field(default=None, description="市盈率")
    pb_ratio: float = Field(description="市净率")
    ps_ratio: float | None = Field(default=None, description="市销率")
    dividend_yield: float | None = Field(default=None, description="股息率")
    market_cap: float = Field(description="市值")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_valuation(row: dict[str, Any]) -> Valuation:
    """
    将数据库行转换为 Valuation 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, pe_ratio, pb_ratio,
             ps_ratio, dividend_yield, market_cap 等字段

    Returns:
        Valuation 模型实例

    """
    return Valuation(
        instrument_id=row["instrument_id"],
        trade_date=row["trade_date"],
        pe_ratio=row.get("pe_ratio"),
        pb_ratio=row["pb_ratio"],
        ps_ratio=row.get("ps_ratio"),
        dividend_yield=row.get("dividend_yield"),
        market_cap=row["market_cap"],
    )


def to_valuation_list(df: pl.DataFrame) -> list[Valuation]:
    """
    将 DataFrame 转换为 Valuation 列表.

    Args:
        df: 包含估值指标数据的 DataFrame

    Returns:
        Valuation 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Valuation] = []
    for row in df.to_dicts():
        result.append(to_valuation(row))

    return result


class FuturesQuery(BaseModel):
    """
    期货查询参数模型.

    Attributes:
        instrument_id: 标的 ID
        as_of_date: 时间点查询日期

    """

    instrument_id: str = Field(description="标的 ID")
    as_of_date: date = Field(description="时间点查询日期")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class Futures(BaseModel):
    """
    期货响应模型.

    Attributes:
        instrument_id: 标的 ID
        trade_date: 交易日期
        open_interest: 持仓量
        settlement_price: 结算价 (可选)
        volume: 成交量
        turnover: 成交额 (可选)

    """

    instrument_id: str = Field(description="标的 ID")
    trade_date: str = Field(description="交易日期")
    open_interest: int = Field(description="持仓量")
    settlement_price: float | None = Field(default=None, description="结算价")
    volume: int = Field(description="成交量")
    turnover: float | None = Field(default=None, description="成交额")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


def to_futures(row: dict[str, Any]) -> Futures:
    """
    将数据库行转换为 Futures 模型.

    Args:
        row: 数据库行字典，包含 instrument_id, trade_date, open_interest,
             settlement_price, volume, turnover 等字段

    Returns:
        Futures 模型实例

    """
    return Futures(
        instrument_id=row["instrument_id"],
        trade_date=row["trade_date"],
        open_interest=row["open_interest"],
        settlement_price=row.get("settlement_price"),
        volume=row["volume"],
        turnover=row.get("turnover"),
    )


def to_futures_list(df: pl.DataFrame) -> list[Futures]:
    """
    将 DataFrame 转换为 Futures 列表.

    Args:
        df: 包含期货数据的 DataFrame

    Returns:
        Futures 模型实例列表

    """
    if df.is_empty():
        return []

    result: list[Futures] = []
    for row in df.to_dicts():
        result.append(to_futures(row))

    return result


__all__ = [
    "Futures",
    "FuturesQuery",
    "Margin",
    "MarginQuery",
    "Valuation",
    "ValuationQuery",
    "to_futures",
    "to_futures_list",
    "to_margin",
    "to_margin_list",
    "to_valuation",
    "to_valuation_list",
]
