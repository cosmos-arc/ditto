"""Backtest capability contracts."""

from __future__ import annotations

from typing import Protocol

from ditto_backtest.result import EngineResult

__all__ = ["TradingLoop"]


class TradingLoop(Protocol):
    """
    交易循环统一接口 -- 回测/实盘/模拟共享。

    EngineLoop 是回测实现；未来 LiveLoop 将实现同一接口。
    """

    def run(self) -> EngineResult:
        """执行完整交易循环，返回运行结果。"""
        ...
