"""策略上下文工厂。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_app.process.execution.strategy_run_process import StrategyFacade
from ditto_data.services.strategy.strategy_run_service import (
    StrategyRunService as StrategyRunLifecycleService,
)
from ditto_data.services.strategy.strategy_run_service import (
    StrategyRunWriterProtocol,
)

from ditto_interfaces.registry.container import make_app_container
from ditto_interfaces.registry.contexts.bundle import StrategyBundle


@contextmanager
def create_strategy_bundle() -> Iterator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield StrategyBundle(
            strategy_facade=container.get(StrategyFacade),
            run_service=container.get(StrategyRunLifecycleService),
            run_writer=container.get(StrategyRunWriterProtocol),
        )
    finally:
        container.close()
