"""Unit tests for the experiment scheduler tick composition-root bundle."""

from __future__ import annotations

from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.processes.experiments.coordinator import (
    ExperimentExecutionCoordinator,
)
from ditto_application.processes.experiments.worker import ResearchExperimentWorker
from ditto_apps.registry.contexts import (
    ExperimentExecutionBundle,
    create_experiment_tick_bundle,
)
from ditto_apps.registry.contexts import research_execution as research_execution_ctx


class _FakeContainer:
    """Minimal stand-in for the dishka Container used by the bundle."""

    def __init__(self) -> None:
        self.coordinator = cast(ExperimentExecutionCoordinator, MagicMock())
        self.worker = cast(ResearchExperimentWorker, MagicMock())
        self.closed = False

    def get(self, key: type[object]) -> object:
        if key is ExperimentExecutionCoordinator:
            return self.coordinator
        if key is ResearchExperimentWorker:
            return self.worker
        raise AssertionError(f"unexpected container key: {key!r}")

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_container(mocker):
    container = _FakeContainer()
    mocker.patch.object(
        research_execution_ctx,
        "make_app_container",
        return_value=container,
    )
    return container


def test_create_experiment_tick_bundle_yields_concrete_coordinator_and_worker(
    fake_container: _FakeContainer,
) -> None:
    """The bundle must resolve the concrete coordinator + worker via DI."""
    with create_experiment_tick_bundle() as bundle:
        assert isinstance(bundle, ExperimentExecutionBundle)
        assert bundle.coordinator is fake_container.coordinator
        assert bundle.worker is fake_container.worker

    assert fake_container.closed is True


def test_create_experiment_tick_bundle_closes_container_on_exception(
    fake_container: _FakeContainer,
) -> None:
    """The container must be closed even when the consumer raises."""

    class _ConsumerError(Exception):
        pass

    with pytest.raises(_ConsumerError), create_experiment_tick_bundle():
        raise _ConsumerError("consumer failed mid-tick")

    assert fake_container.closed is True


def test_create_experiment_tick_bundle_context_manager_protocol(
    fake_container: _FakeContainer,
) -> None:
    """``create_experiment_tick_bundle`` must be usable as a @contextmanager."""

    @contextmanager
    def consumer() -> object:
        with create_experiment_tick_bundle() as bundle:
            yield bundle

    with consumer() as bundle:
        assert bundle.coordinator is fake_container.coordinator
        assert bundle.worker is fake_container.worker
