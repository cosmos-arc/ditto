"""Default fail-closed Agent runtime provider."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_agent.observability import AgentObservability
from ditto_agent.runtime.service import AgentRuntimePort
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_agent.tools.memory import ResearchMemoryTool
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.research_memory_approval_contracts import (
    DisabledResearchMemoryApprovalVerifier,
    ResearchMemoryApprovalVerifier,
)

from ditto_apps.registry.agent.campaign_runtime import DisabledCampaignRuntime
from ditto_apps.registry.agent.observability import build_agent_observability
from ditto_apps.registry.agent.runtime import DisabledAgentRuntime


class AgentRuntimeProvider(Provider):
    """Register an unavailable runtime until an explicit R5 feature profile is used."""

    scope = Scope.APP

    @provide
    def runtime(self) -> AgentRuntimePort:
        """Keep every Agent API write fail-closed by default."""
        return DisabledAgentRuntime()

    @provide
    def agent_observability(self) -> AgentObservability:
        """Keep Agent OTel export disabled pending an explicit feature profile."""
        return build_agent_observability(enabled=False)

    @provide
    def campaign_runtime(self) -> CampaignRuntimePort:
        """Keep Campaign public mutations unavailable until explicitly enabled."""
        return DisabledCampaignRuntime()

    @provide
    def research_memory_approval_verifier(self) -> ResearchMemoryApprovalVerifier:
        """Keep memory promotion and revocation disabled by default."""
        return DisabledResearchMemoryApprovalVerifier()

    @provide
    def campaign_proposal_tool(
        self,
        commands: AutonomousCampaignCommandPort,
    ) -> CampaignProposalTool:
        """Compose the thin Agent tool over the Application command boundary."""
        return CampaignProposalTool(commands=commands)

    @provide
    def research_memory_tool(
        self,
        facade: ResearchMemoryQueryFacade,
    ) -> ResearchMemoryTool:
        """Compose the host-scoped memory tool over its Application query."""
        return ResearchMemoryTool(facade=facade)


__all__ = ["AgentRuntimeProvider"]
