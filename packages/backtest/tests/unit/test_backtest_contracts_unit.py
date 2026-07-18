"""Backtest capability contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

from ditto_backtest.contracts import TradingLoop
from ditto_backtest.engine import EngineConfig, EngineLoop, EngineOptions
from ditto_backtest.result import EngineResult
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_kernel.clock import SimulatedClock

DAYS = ["2026-03-01", "2026-03-02", "2026-03-03"]


def _make_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-03-01",
        end_date="2026-03-03",
        initial_cash=1_000_000.0,
        spec_hash="e" * 64,
        strategy_id="default",
        strategy_run_id="run-001",
    )


def _make_engine_loop() -> EngineLoop:
    config = _make_config()
    data_feed = Mock()
    data_feed.trading_days.return_value = DAYS
    clock = SimulatedClock(initial=datetime(2026, 3, 1, tzinfo=UTC))
    synchronizer = BacktestSynchronizer(
        data_feed=data_feed,
        clock=clock,
        start_date=config.start_date,
    )
    return EngineLoop(
        config=config,
        pipeline=Mock(),
        planner=Mock(),
        brokerage=Mock(),
        pre_trade_check=Mock(),
        data_feed=data_feed,
        synchronizer=synchronizer,
        options=EngineOptions(),
    )


def _accept_trading_loop(loop: TradingLoop) -> TradingLoop:
    return loop


def test_engine_loop_satisfies_trading_loop_protocol() -> None:
    loop = _make_engine_loop()
    typed = _accept_trading_loop(loop)
    assert isinstance(typed, EngineLoop)


def test_stub_satisfies_trading_loop_protocol() -> None:
    class StubLoop:
        def run(self) -> EngineResult:
            return EngineResult(
                run_id="stub",
                period=("2026-01-01", "2026-01-01"),
            )

    typed = _accept_trading_loop(StubLoop())
    result = typed.run()
    assert result.run_id == "stub"


def test_contracts_do_not_import_engine_implementation() -> None:
    text = Path("packages/backtest/src/ditto_backtest/contracts.py").read_text(
        encoding="utf-8",
    )
    assert "ditto_backtest.engine" not in text


def test_engine_result_has_canonical_result_module() -> None:
    assert EngineResult.__module__ == "ditto_backtest.result"
