from __future__ import annotations

from collections.abc import Callable

import pytest
from ditto_agent.runtime.service import AgentRuntimeUnavailable
from ditto_apps.registry.agent.degradation import (
    AgentDependency,
    AgentStartupBoundary,
)
from ditto_apps.registry.agent.settings import AgentFeatureSettings
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import RuntimeFlags


@pytest.mark.parametrize(
    "dependency",
    [
        AgentDependency.MODEL_PROVIDER,
        AgentDependency.DATABASE,
        AgentDependency.SANDBOX,
        AgentDependency.EXPORTER,
    ],
)
def test_agent_dependency_outage_is_isolated_from_core_ditto(
    dependency: AgentDependency,
) -> None:
    def unavailable() -> object:
        raise OSError(f"{dependency.value} unavailable")

    healthy: Callable[[], object] = object
    probes: dict[AgentDependency, Callable[[], object]] = {}
    for item in AgentDependency:
        probes[item] = healthy
    probes[dependency] = unavailable
    boundary = AgentStartupBoundary(
        settings=AgentFeatureSettings(agent_enabled=True),
        dependency_probes=probes,
    )

    status = boundary.probe()

    assert status.available is False
    assert status.reason_code == f"agent_{dependency.value}_unavailable"
    container = make_app_container()
    try:
        core_flags = container.get(RuntimeFlags)
    finally:
        container.close()
    assert isinstance(core_flags, RuntimeFlags)


def test_disabled_agent_does_not_probe_optional_dependencies() -> None:
    calls: list[AgentDependency] = []

    def forbidden(dependency: AgentDependency) -> Callable[[], object]:
        def probe() -> object:
            calls.append(dependency)
            raise AssertionError("disabled Agent must not initialize dependencies")

        return probe

    boundary = AgentStartupBoundary(
        settings=AgentFeatureSettings(),
        dependency_probes={item: forbidden(item) for item in AgentDependency},
    )

    status = boundary.probe()

    assert status.available is False
    assert status.reason_code == "agent_feature_disabled"
    assert calls == []


def test_unavailable_boundary_never_falls_back_to_agent_answer() -> None:
    boundary = AgentStartupBoundary(
        settings=AgentFeatureSettings(agent_enabled=True),
        dependency_probes=dict.fromkeys(AgentDependency, object),
    )
    boundary = boundary.with_probe(
        AgentDependency.MODEL_PROVIDER,
        lambda: (_ for _ in ()).throw(RuntimeError("provider offline")),
    )

    with pytest.raises(AgentRuntimeUnavailable) as exc_info:
        boundary.require_available()

    assert exc_info.value.reason_code == "agent_model_provider_unavailable"
