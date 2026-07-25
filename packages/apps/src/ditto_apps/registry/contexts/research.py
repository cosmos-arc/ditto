"""研究实验上下文组合包（control + query）。"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from ditto_application.commands.experiments import (
    CancelExperimentHandler,
    PauseExperimentHandler,
    ResumeExperimentHandler,
    RetryExperimentFoldHandler,
)
from ditto_application.queries.experiments import ExperimentQueryFacade

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import ResearchBundle


@contextmanager
def create_research_bundle() -> Generator[ResearchBundle]:
    """创建研究实验上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        yield ResearchBundle(
            experiment_query=container.get(ExperimentQueryFacade),
            pause_handler=container.get(PauseExperimentHandler),
            cancel_handler=container.get(CancelExperimentHandler),
            resume_handler=container.get(ResumeExperimentHandler),
            retry_fold_handler=container.get(RetryExperimentFoldHandler),
        )
    finally:
        container.close()
