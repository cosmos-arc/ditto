"""Default fail-closed Agent runtime provider."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_agent.observability import AgentObservability
from ditto_agent.runtime.service import AgentRuntimePort
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_agent.tools.memory import ResearchMemoryTool
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.queries.decision_opinion import (
    DecisionOpinionQueryPort,
    UnavailableDecisionOpinionQuery,
)
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.research_memory_approval_contracts import (
    DisabledResearchMemoryApprovalVerifier,
    ResearchMemoryApprovalVerifier,
)

from ditto_apps.registry.agent.campaign_runtime import DisabledCampaignRuntime
from ditto_apps.registry.agent.observability import build_agent_observability
from ditto_apps.registry.agent.runtime import DisabledAgentRuntime
from ditto_apps.registry.agent.settings import AgentFeatureSettings


class AgentRuntimeProvider(Provider):
    """Register an unavailable runtime until an explicit R5 feature profile is used."""

    scope = Scope.APP

    @provide
    def feature_settings(self) -> AgentFeatureSettings:
        """Read the closed R5 flag set at the composition root."""
        return AgentFeatureSettings.from_environment()

    @provide
    def runtime(self, settings: AgentFeatureSettings) -> AgentRuntimePort:
        """Keep every Agent API write fail-closed by default."""
        reason = (
            "agent_runtime_profile_unconfigured"
            if settings.agent_enabled
            else "agent_feature_disabled"
        )
        return DisabledAgentRuntime(reason)

    @provide
    def agent_observability(
        self,
        settings: AgentFeatureSettings,
    ) -> AgentObservability:
        """Keep Agent OTel export disabled pending an explicit feature profile."""
        return build_agent_observability(enabled=settings.agent_enabled)

    @provide
    def campaign_runtime(self) -> CampaignRuntimePort:
        """Keep Campaign public mutations unavailable until explicitly enabled."""
        return DisabledCampaignRuntime()

    @provide
    def decision_opinion_query(self) -> DecisionOpinionQueryPort:
        """Report explicit shadow unavailability until a store is composed."""
        return UnavailableDecisionOpinionQuery()

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
