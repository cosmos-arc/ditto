"""TradingOrchestrator Protocol 单元测试."""

from __future__ import annotations

from unittest.mock import Mock

from ditto_engine.backtest.engine import EngineResult
from ditto_engine.orchestrator.protocol import TradingOrchestrator

# ---------------------------------------------------------------------------
# Protocol 结构兼容性
# ---------------------------------------------------------------------------


class TestTradingOrchestratorProtocol:
    """TradingOrchestrator Protocol 测试."""

    def test_mock_satisfies_protocol(self) -> None:
        """Mock 对象满足 TradingOrchestrator Protocol — run() 返回 EngineResult."""

        def _use_orchestrator(orch: TradingOrchestrator) -> EngineResult:
            return orch.run()

        mock = Mock(spec=TradingOrchestrator)
        mock.run.return_value = EngineResult(
            run_id="test",
            period=("2026-01-01", "2026-01-31"),
        )
        result = _use_orchestrator(mock)
        assert isinstance(result, EngineResult)
        assert result.run_id == "test"

    def test_custom_implementation_satisfies(self) -> None:
        """自定义实现满足 Protocol."""

        class StubOrchestrator:
            def run(self) -> EngineResult:
                return EngineResult(
                    run_id="stub",
                    period=("2026-01-01", "2026-01-01"),
                )

        def _accept(orch: TradingOrchestrator) -> EngineResult:
            return orch.run()

        stub = StubOrchestrator()
        result = _accept(stub)
        assert result.run_id == "stub"
