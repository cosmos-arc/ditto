"""Metadata 域数据模型."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

# ========================================================================
# Calendar
# ========================================================================


@dataclass(frozen=True)
class CalendarDay:
    """Single trading day data."""

    trade_date: str
    is_open: bool
    exchange: str = "SSE"
    prev_trade_date: str | None = None
    next_trade_date: str | None = None
    week_of_year: int | None = None
    month: int | None = None
    quarter: int | None = None
    year: int | None = None
    is_week_end: bool = False
    is_month_end: bool = False
    is_quarter_end: bool = False
    is_half_day: bool = False
    is_special: bool = False


# ========================================================================
# Industry
# ========================================================================


@dataclass(frozen=True)
class IndustryBasic:
    """行业基本信息（申万/证监会）."""

    industry_id: str
    industry_name: str
    industry_level: str  # L1/L2/L3
    parent_id: str | None = None
    is_active: bool = True
    source: str = "sw"  # sw=申万, csrc=证监会


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
# Instrument Extension (Protocol)
# ========================================================================


class InstrumentExtension(Protocol):
    """
    资产扩展信息协议。

    所有资产类型扩展的统一接口，使用 Protocol 而非继承，
    符合"组合优于继承"原则。
    """

    instrument_id: int


@dataclass(frozen=True)
class StockExtension(InstrumentExtension):
    """股票扩展信息"""

    instrument_id: int
    list_status: Literal["L", "D", "P"] | None  # L=正常, D=退市, P=暂停
    industry_id: int | None


@dataclass(frozen=True)
class ETFExtension(InstrumentExtension):
    """ETF 扩展信息"""

    instrument_id: int
    fund_type: str | None  # 股票型/债券型/货币型/混合型等
    fund_manager: str | None
    establish_date: str | None
    tracking_index: str | None


@dataclass(frozen=True)
class IndexExtension(InstrumentExtension):
    """指数扩展信息"""

    instrument_id: int
    base_date: str | None  # 基日
    base_point: float | None  # 基点
    num_constituents: int | None  # 成分股数量


# ========================================================================
# Instrument Registration
# ========================================================================


@dataclass(frozen=True)
class InstrumentRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。

    Attributes:
        source_ticker: 源代码（如 "600000.SH"），数据库中存储为 source_ticker
        ticker: 裸代码（如 "600000"）
        name: 证券名称
        exchange: 交易所代码（如 "SSE", "SZSE"）
        asset_class: 资产类别（stock/etf/index）
        list_date: 上市日期（YYYY-MM-DD 格式）
        delist_date: 退市日期（YYYY-MM-DD 格式，可选）
        source: 数据源标识符（默认 "tushare"）
        board: 板块代码（可选）
        extension: 可选的资产类型扩展信息

    """

    source_ticker: str
    ticker: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    delist_date: str | None = None
    source: str = "tushare"
    board: str | None = None
    extension: InstrumentExtension | None = None


__all__ = [
    "CalendarDay",
    "ETFExtension",
    "IndexExtension",
    "IndustryBasic",
    "IndustryMapping",
    "InstrumentExtension",
    "InstrumentRegistration",
    "StockExtension",
]
