"""Research-memory Application boundary wiring."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_analysis.experiments.campaign_persistence import (
    CampaignReaderProtocol,
    CampaignWriterProtocol,
)

from ditto_application.commands.research_memory import ResearchMemoryCommandFacade
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.research_memory_approval_contracts import (
    DisabledResearchMemoryApprovalVerifier,
    ResearchMemoryApprovalVerifier,
)
from ditto_application.research_memory_contracts import ResearchMemoryCommandPort


class AppResearchMemoryProvider(Provider):
    """Compose PIT reads and governed writes over approved Analysis ports."""

    scope = Scope.APP

    @provide
    def research_memory_approval_verifier(self) -> ResearchMemoryApprovalVerifier:
        """Keep durable memory mutations fail-closed by default."""
        return DisabledResearchMemoryApprovalVerifier()

    @provide
    def research_memory_query_facade(
        self,
        reader: CampaignReaderProtocol,
    ) -> ResearchMemoryQueryFacade:
        """Expose scoped PIT research memory through the Application boundary."""
        return ResearchMemoryQueryFacade(reader=reader)

    @provide
    def research_memory_command_facade(
        self,
        reader: CampaignReaderProtocol,
        writer: CampaignWriterProtocol,
        approval_verifier: ResearchMemoryApprovalVerifier,
    ) -> ResearchMemoryCommandFacade:
        """Compose governed memory mutations over durable Analysis ports."""
        return ResearchMemoryCommandFacade(
            reader=reader,
            writer=writer,
            approval_verifier=approval_verifier,
        )

    @provide
    def research_memory_command_port(
        self,
        facade: ResearchMemoryCommandFacade,
    ) -> ResearchMemoryCommandPort:
        """Expose only the approved promote and revoke command surface."""
        return facade


__all__ = ["AppResearchMemoryProvider"]
