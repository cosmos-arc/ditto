"""策略上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
    StrategyRunWriterProtocol,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import StrategyBundle


@contextmanager
def create_strategy_bundle() -> Generator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield StrategyBundle(
            strategy_facade=container.get(StrategyFacade),
            catalog_service=container.get(StrategyCatalogService),
            run_service=container.get(StrategyRunLifecycleStore),
            run_writer=container.get(StrategyRunWriterProtocol),
        )
    finally:
        container.close()
