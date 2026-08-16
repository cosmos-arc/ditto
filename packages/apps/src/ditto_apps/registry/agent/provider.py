"""Default fail-closed Agent runtime provider."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_agent.runtime.service import AgentRuntimePort

from ditto_apps.registry.agent.runtime import DisabledAgentRuntime


class AgentRuntimeProvider(Provider):
    """Register an unavailable runtime until an explicit R5 feature profile is used."""

    scope = Scope.APP

    @provide
    def runtime(self) -> AgentRuntimePort:
        """Keep every Agent API write fail-closed by default."""
        return DisabledAgentRuntime()


__all__ = ["AgentRuntimeProvider"]
