"""Optional Agent startup probes isolated from every core Ditto capability."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from ditto_agent.runtime.service import AgentRuntimeUnavailable

from ditto_apps.registry.agent.settings import AgentFeatureSettings


class AgentDependency(StrEnum):
    """Closed optional dependency set covered by the R5 degradation runbook."""

    MODEL_PROVIDER = "model_provider"
    DATABASE = "database"
    SANDBOX = "sandbox"
    EXPORTER = "exporter"


@dataclass(frozen=True, slots=True)
class AgentStartupStatus:
    """Non-sensitive result of optional Agent dependency probing."""

    available: bool
    reason_code: str | None
    failed_dependency: AgentDependency | None


@dataclass(frozen=True, slots=True)
class AgentStartupBoundary:
    """Probe Agent-only dependencies without touching a core service path."""

    settings: AgentFeatureSettings
    dependency_probes: Mapping[AgentDependency, Callable[[], object]]

    def with_probe(
        self,
        dependency: AgentDependency,
        probe: Callable[[], object],
    ) -> AgentStartupBoundary:
        """Return a copy with one explicit dependency probe replaced."""
        probes = dict(self.dependency_probes)
        probes[dependency] = probe
        return replace(self, dependency_probes=probes)

    def probe(self) -> AgentStartupStatus:
        """Return the first stable failure code; never leak provider details."""
        if not self.settings.agent_enabled:
            return AgentStartupStatus(
                available=False,
                reason_code="agent_feature_disabled",
                failed_dependency=None,
            )
        for dependency in AgentDependency:
            probe = self.dependency_probes.get(dependency)
            if probe is None:
                return self._unavailable(dependency)
            try:
                probe()
            except (OSError, RuntimeError, ValueError):
                return self._unavailable(dependency)
        return AgentStartupStatus(
            available=True,
            reason_code=None,
            failed_dependency=None,
        )

    def require_available(self) -> None:
        """Raise the transport-neutral fail-closed error for Agent callers."""
        status = self.probe()
        if not status.available:
            raise AgentRuntimeUnavailable(status.reason_code or "agent_unavailable")

    @staticmethod
    def _unavailable(dependency: AgentDependency) -> AgentStartupStatus:
        return AgentStartupStatus(
            available=False,
            reason_code=f"agent_{dependency.value}_unavailable",
            failed_dependency=dependency,
        )


__all__ = [
    "AgentDependency",
    "AgentStartupBoundary",
    "AgentStartupStatus",
]
