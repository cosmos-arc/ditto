"""Tushare source 内部共享工具函数."""

from __future__ import annotations


def to_compact_date(trade_date: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for Tushare APIs."""
    return trade_date.replace("-", "")
