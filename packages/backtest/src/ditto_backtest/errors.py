"""Backtest domain errors."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "BacktestError",
    "EngineConfigError",
    "ReplayError",
    "SimulationError",
]


class BacktestError(DittoError):
    """Backtest domain error root."""


class EngineConfigError(BacktestError):
    """Backtest engine configuration error."""


class ReplayError(BacktestError):
    """Replay validation error."""


class SimulationError(BacktestError):
    """Simulation runtime error."""
