"""策略上下文工厂。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_app.process.strategy_run_service import StrategyFacade

from ditto_interfaces.registry.container import make_app_container
from ditto_interfaces.registry.contexts.bundle import StrategyBundle


@contextmanager
def create_strategy_bundle() -> Iterator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield StrategyBundle(strategy_facade=container.get(StrategyFacade))
    finally:
        container.close()
