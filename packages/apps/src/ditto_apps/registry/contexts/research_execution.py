"""研究实验 scheduler tick 上下文组合包（composition root）。"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.worker import ResearchExperimentWorker

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import ExperimentExecutionBundle


@contextmanager
def create_experiment_tick_bundle() -> Generator[ExperimentExecutionBundle]:
    """
    Create one composition-root bundle for the experiment scheduler tick.

    Yields the concrete coordinator + worker resolved by the DI container; the
    flow entrypoint adapts this bundle into the Protocol-typed
    :class:`~ditto_apps.jobs.flows.experiments.ExperimentTickRuntime` required
    by ``experiment_scheduler_tick_flow``.
    """
    container = make_app_container()
    try:
        yield ExperimentExecutionBundle(
            coordinator=container.get(ExperimentExecutionCoordinator),
            worker=container.get(ResearchExperimentWorker),
        )
    finally:
        container.close()
