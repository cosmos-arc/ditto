"""Backtest simulation ownership tests."""

from __future__ import annotations

import importlib


def test_backtest_owns_simulated_brokerage_and_models() -> None:
    from ditto_backtest.brokerage import BacktestBrokerage
    from ditto_backtest.simulation import (
        AShareFillModel,
        AShareSettlementModel,
        BrokerageModel,
        FixedBpsSlippage,
    )

    assert BacktestBrokerage.__module__ == "ditto_backtest.brokerage"
    assert BrokerageModel.__module__ == "ditto_backtest.simulation.brokerage"
    assert AShareFillModel.__module__ == "ditto_backtest.simulation.fill"
    assert AShareSettlementModel.__module__ == "ditto_backtest.simulation.settlement"
    assert FixedBpsSlippage.__module__ == "ditto_backtest.simulation.slippage"


def test_execution_brokerage_exposes_only_ports() -> None:
    from ditto_execution import brokerage

    assert hasattr(brokerage, "Brokerage")
    assert hasattr(brokerage, "ProcessInput")
    assert not hasattr(brokerage, "BacktestBrokerage")


def test_execution_no_longer_owns_simulation_modules() -> None:
    for module_name in (
        "ditto_execution.reality.brokerage",
        "ditto_execution.reality.fill",
        "ditto_execution.reality.settlement",
        "ditto_execution.reality.slippage",
    ):
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module_name} should be owned by ditto_backtest")
