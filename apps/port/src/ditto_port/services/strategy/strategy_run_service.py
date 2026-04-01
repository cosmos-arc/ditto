"""Shim — 真实实现已迁移至 ditto_app.process.strategy."""

from ditto_app.process.strategy import (
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunService,
    StrategyRunServiceConfig,
)

__all__ = [
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
]
