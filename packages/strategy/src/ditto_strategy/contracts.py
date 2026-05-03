"""Strategy domain contracts — Protocol definitions for strategy consumers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle

__all__ = ["SignalProvider"]


@runtime_checkable
class SignalProvider(Protocol):
    """策略信号生成接口 — 输入上下文与数据包，输出目标组合."""

    def run(
        self,
        context: StrategyContext,
        input_bundle: StrategyInputBundle,
    ) -> TargetPortfolio:
        """执行策略评估，返回目标组合权重."""
        ...
