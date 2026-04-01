"""Shim — 真实实现已迁移至 ditto_app.process.strategy."""

from ditto_app.process.strategy import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)

__all__ = ["BacktestService", "BacktestServiceConfig", "BacktestServiceOptions"]
