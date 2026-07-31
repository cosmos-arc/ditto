"""研究实验上下文组合包（control + query）。"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.commands.experiments import (
    CancelExperimentHandler,
    LaunchExperimentHandler,
    PauseExperimentHandler,
    ResumeExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.queries.experiments import ExperimentQueryFacade

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import ResearchBundle


@contextmanager
def create_research_bundle() -> Generator[ResearchBundle]:
    """创建研究实验上下文组合包（单容器，含 planning/launch）。"""
    container = make_app_container()
    try:
        yield ResearchBundle(
            experiment_query=container.get(ExperimentQueryFacade),
            planning_process=container.get(ExperimentPlanningProcess),
            launch_handler=container.get(LaunchExperimentHandler),
            pause_handler=container.get(PauseExperimentHandler),
            cancel_handler=container.get(CancelExperimentHandler),
            resume_handler=container.get(ResumeExperimentHandler),
            retry_fold_handler=container.get(RetryExperimentFoldHandler),
        )
    finally:
        container.close()
