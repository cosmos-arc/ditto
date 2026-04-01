"""Shim — 真实实现已迁移至 ditto_app.builders.strategy."""

from ditto_app.builders.strategy import (
    BacktestRuntimeBuilder,
    PublishedBacktestRuntime,
)

__all__ = ["BacktestRuntimeBuilder", "PublishedBacktestRuntime"]
