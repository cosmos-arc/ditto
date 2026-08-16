"""Default fail-closed Agent runtime provider."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_agent.runtime.service import AgentRuntimePort
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort

from ditto_apps.registry.agent.runtime import DisabledAgentRuntime


class AgentRuntimeProvider(Provider):
    """Register an unavailable runtime until an explicit R5 feature profile is used."""

    scope = Scope.APP

    @provide
    def runtime(self) -> AgentRuntimePort:
        """Keep every Agent API write fail-closed by default."""
        return DisabledAgentRuntime()

    @provide
    def campaign_proposal_tool(
        self,
        commands: AutonomousCampaignCommandPort,
    ) -> CampaignProposalTool:
        """Compose the thin Agent tool over the Application command boundary."""
        return CampaignProposalTool(commands=commands)


__all__ = ["AgentRuntimeProvider"]
