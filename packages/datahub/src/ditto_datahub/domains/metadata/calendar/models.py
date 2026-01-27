"""Calendar 相关数据模型."""

from __future__ import annotations

from dataclasses import dataclass


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
