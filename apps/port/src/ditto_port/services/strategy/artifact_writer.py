"""Shim — 真实实现已迁移至 ditto_app.process.strategy."""

from ditto_app.process.strategy import (
    enrich_record_with_symbol,
    write_backtest_artifacts,
)

__all__ = ["enrich_record_with_symbol", "write_backtest_artifacts"]
