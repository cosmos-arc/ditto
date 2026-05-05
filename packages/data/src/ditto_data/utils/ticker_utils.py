"""Ticker 相关工具函数."""

from __future__ import annotations

__all__ = ["get_standard_ticker"]


def get_standard_ticker(ticker: str, exchange: str) -> str:
    """
    生成标准可读编码（仅展示层使用）.

    Args:
        ticker: 裸代码（如 "600000"）
        exchange: 交易所代码（如 "SSE"）

    Returns:
        标准可读编码（如 "600000.SSE"）

    Examples:
        >>> get_standard_ticker("600000", "SSE")
        '600000.SSE'
        >>> get_standard_ticker("000001", "SZSE")
        '000001.SZSE'

    """
    return f"{ticker}.{exchange}"
