"""策略上下文工厂。"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_port.registry.container import make_app_container
from ditto_port.registry.contexts.bundle import StrategyBundle
from ditto_port.services.strategy.facade import StrategyFacade


@contextmanager
def create_strategy_bundle() -> Iterator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield StrategyBundle(strategy_facade=container.get(StrategyFacade))
    finally:
        container.close()
