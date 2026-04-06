"""
策略服务工厂与运行时装配 — re-export shim.

所有公共符号已拆分至子模块，此文件仅负责保持
``from ditto_app.builders.strategy import Xxx`` 的向后兼容。

拆分结构：
  - runtime_builder.py  → PublishedStrategyRuntime, StrategyRuntimeBuilder
  - slice_builder.py    → StrategySliceBuilder
  - service_factory.py  → PublishedBacktestRuntime,
    BacktestRuntimeBuilder, StrategyServiceFactory
"""

from __future__ import annotations

from ditto_app.builders.runtime_builder import (
    PublishedStrategyRuntime,
    StrategyRuntimeBuilder,
)
from ditto_app.builders.service_factory import (
    BacktestRuntimeBuilder,
    PublishedBacktestRuntime,
    StrategyServiceFactory,
)
from ditto_app.builders.slice_builder import StrategySliceBuilder

__all__ = [
    "BacktestRuntimeBuilder",
    "PublishedBacktestRuntime",
    "PublishedStrategyRuntime",
    "StrategyRuntimeBuilder",
    "StrategyServiceFactory",
    "StrategySliceBuilder",
]
