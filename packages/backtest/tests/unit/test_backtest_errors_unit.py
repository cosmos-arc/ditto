"""Backtest error hierarchy tests."""

from ditto_backtest.errors import (
    BacktestError,
    EngineConfigError,
    ReplayError,
    SimulationError,
)
from ditto_kernel.exceptions import DittoError


def test_backtest_error_hierarchy() -> None:
    assert issubclass(BacktestError, DittoError)
    assert issubclass(EngineConfigError, BacktestError)
    assert issubclass(ReplayError, BacktestError)
    assert issubclass(SimulationError, BacktestError)


def test_simulation_error_carries_details() -> None:
    err = SimulationError("invalid step context", step="pre_trade")
    assert err.details == {"step": "pre_trade"}
