"""策略上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
    PublishStrategyCommand,
    PublishStrategyHandler,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.strategy.seed_bootstrap import SeedStrategyBootstrap
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
    StrategyRunWriterProtocol,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import StrategyBundle


@dataclass(frozen=True)
class _SeedCreateAdapter:
    handler: CreateStrategyHandler

    def create(
        self,
        *,
        strategy_id: str,
        name: str,
        spec_json: dict[str, object],
        tags: tuple[str, ...],
    ) -> int:
        return self.handler.handle(
            CreateStrategyCommand(
                strategy_id=strategy_id,
                name=name,
                spec_json=spec_json,
                tags=tags,
            )
        ).version


@dataclass(frozen=True)
class _SeedPublishAdapter:
    handler: PublishStrategyHandler

    def publish(self, *, strategy_id: str, version: int) -> None:
        self.handler.handle(
            PublishStrategyCommand(strategy_id=strategy_id, version=version)
        )


@contextmanager
def create_strategy_bundle() -> Generator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        catalog_service = container.get(StrategyCatalogService)
        yield StrategyBundle(
            strategy_facade=container.get(StrategyFacade),
            catalog_service=catalog_service,
            run_service=container.get(StrategyRunLifecycleStore),
            run_writer=container.get(StrategyRunWriterProtocol),
            signal_package_publisher=container.get(SignalPackagePublisher),
            seed_bootstrap=SeedStrategyBootstrap(
                catalog=catalog_service,
                create_port=_SeedCreateAdapter(container.get(CreateStrategyHandler)),
                publish_port=_SeedPublishAdapter(container.get(PublishStrategyHandler)),
            ),
        )
    finally:
        container.close()
