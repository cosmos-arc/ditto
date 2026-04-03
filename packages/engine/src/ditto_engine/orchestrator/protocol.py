"""
TradingOrchestrator Protocol — 交易编排形式化接口.

定义交易日循环的标准接口，EngineLoop 作为回测实现隐式满足此 Protocol。
未来 LiveTradingOrchestrator 等实现也将满足此接口。
"""

from __future__ import annotations

from typing import Protocol

from ditto_engine.backtest.engine import EngineResult

__all__ = ["TradingOrchestrator"]


class TradingOrchestrator(Protocol):
    """
    交易编排器 Protocol — 日循环的形式化抽象.

    实现者负责编排每日交易流程:
      1. 获取数据切片
      2. 获取账户快照
      3. PostTrade 风控扫描
      4. [调仓日] Alpha → Portfolio 决策
      5. [调仓日] 执行计划 + PreTrade 验证
      6. [调仓日] 下单
      7. 处理待成交
      8. 审计记录
    """

    def run(self) -> EngineResult:
        """执行完整交易周期，返回运行结果."""
        ...
