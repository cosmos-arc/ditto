"""TradingLoop Protocol 单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

from ditto_backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineOptions,
    EngineResult,
)
from ditto_backtest.protocol import TradingLoop
from ditto_kernel.clock import Clock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"]


def _make_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-03-01",
        end_date="2026-03-03",
        initial_cash=1_000_000.0,
        strategy_id="default",
        strategy_run_id="run-001",
    )


def _make_clock() -> MagicMock:
    clock = MagicMock(spec=Clock)
    clock.now.return_value = None
    return clock


def _make_engine_loop() -> EngineLoop:
    config = _make_config()
    data_feed = Mock()
    data_feed.trading_days.return_value = DAYS
    return EngineLoop(
        config=config,
        pipeline=Mock(),
        planner=Mock(),
        brokerage=Mock(),
        pre_trade_check=Mock(),
        data_feed=data_feed,
        options=EngineOptions(clock=_make_clock()),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTradingLoopProtocol:
    """TradingLoop Protocol 结构化子类型验证."""

    def test_engine_loop_satisfies_protocol(self) -> None:
        """EngineLoop 满足 TradingLoop Protocol（类型注解赋值验证）."""
        loop = _make_engine_loop()
        typed: TradingLoop = loop  # type: ignore[assignment]
        assert isinstance(typed, EngineLoop)

    def test_stub_satisfies_protocol(self) -> None:
        """任意实现 run() -> EngineResult 的类都满足 Protocol."""

        class StubLoop:
            def run(self) -> EngineResult:
                return EngineResult(
                    run_id="stub",
                    period=("2026-01-01", "2026-01-01"),
                )

        typed: TradingLoop = StubLoop()  # type: ignore[assignment]
        result = typed.run()
        assert result.run_id == "stub"

    def test_protocol_has_run_method(self) -> None:
        """TradingLoop Protocol 定义了 run 方法."""
        assert hasattr(TradingLoop, "run")
