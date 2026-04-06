"""
策略运行编排服务 — re-export shim.

原始实现已拆分为三个独立模块：
  - strategy_types.py: 共享类型、DTO、协议、工具类
  - backtest_service.py: BacktestService 及其配置
  - strategy_run_service.py: StrategyRunService、StrategyFacade 及相关类型

本文件仅做 re-export，保持所有公共 API 的导入路径不变。
"""

from __future__ import annotations

from ditto_app.process.backtest_service import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_app.process.strategy_run_service import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunService,
    StrategyRunServiceConfig,
)
from ditto_app.process.strategy_types import (
    MarketServiceDataFeed,
    MarketServiceDataFeedConfig,
    RunLifecycleService,
    StrategyInputAssembler,
    enrich_record_with_symbol,
    write_backtest_artifacts,
)

__all__ = [
    "BacktestService",
    "BacktestServiceConfig",
    "BacktestServiceOptions",
    "MarketServiceDataFeed",
    "MarketServiceDataFeedConfig",
    "RunLifecycleService",
    "StrategyFacade",
    "StrategyInputAssembler",
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
    "enrich_record_with_symbol",
    "write_backtest_artifacts",
]
