"""Metadata 域数据模型."""

from __future__ import annotations

from dataclasses import dataclass

# ========================================================================
# Calendar
# ========================================================================


@dataclass(frozen=True)
class CalendarDay:
    """Single trading day data."""

    trade_date: str
    is_open: bool
    prev_trade_date: str | None
    next_trade_date: str | None
    week_of_year: int | None
    month: int | None
    quarter: int | None
    year: int | None
    is_week_end: bool
    is_month_end: bool
    is_quarter_end: bool


# ========================================================================
# Industry
# ========================================================================


@dataclass(frozen=True)
class IndustryBasic:
    """申万行业基本信息."""

    industry_id: str
    industry_name: str
    industry_level: str  # 一级/二级行业
    parent_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class IndustryMapping:
    """股票-行业映射."""

    instrument_id: int
    industry_id: str
    source: str = "sw"  # 申万
    effective_from: str | None = None
    effective_to: str | None = None
    entry_reason: str | None = None


# ========================================================================
# Instrument
# ========================================================================


@dataclass(frozen=True)
class InstrumentRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。

    Attributes:
        source_ticker: 源代码（如 "600000.SH"），数据库中存储为 source_ticker
        symbol: 显示符号（如 "600000"）
        name: 证券名称
        exchange: 交易所代码（如 "SSE", "SZSE"）
        asset_class: 资产类别（stock/etf/index）
        list_date: 上市日期（YYYY-MM-DD 格式）
        source: 数据源标识符（默认 "tushare"）
        board: 板块代码（可选）

    """

    source_ticker: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None


__all__ = [
    "CalendarDay",
    "IndustryBasic",
    "IndustryMapping",
    "InstrumentRegistration",
]
