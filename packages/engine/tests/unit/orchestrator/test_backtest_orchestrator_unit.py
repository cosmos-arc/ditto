"""BacktestTradingOrchestrator 别名单元测试."""

from __future__ import annotations

from ditto_engine.backtest.engine import EngineLoop
from ditto_engine.orchestrator import BacktestTradingOrchestrator


class TestBacktestTradingOrchestrator:
    """BacktestTradingOrchestrator = EngineLoop 别名测试."""

    def test_alias_is_engine_loop(self) -> None:
        """BacktestTradingOrchestrator 是 EngineLoop 的别名."""
        assert BacktestTradingOrchestrator is EngineLoop

    def test_creatable(self) -> None:
        """可以通过 BacktestTradingOrchestrator 创建实例."""
        assert issubclass(BacktestTradingOrchestrator, EngineLoop)
