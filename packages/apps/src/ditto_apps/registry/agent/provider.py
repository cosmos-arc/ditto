"""Feature-gated production composition for governed Agent surfaces."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.runtime import AgentManifest, ModelProfile
from ditto_agent.observability import AgentObservability
from ditto_agent.runtime.service import AgentRuntimePort
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_agent.tools.memory import ResearchMemoryTool
from ditto_analysis.experiments.campaign_persistence import CampaignReaderProtocol
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
)
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceQueryPort,
)
from ditto_application.queries.decision_evidence import DecisionEvidenceQueryFacade
from ditto_application.queries.decision_opinion import (
    DecisionOpinionQueryPort,
    DecisionOpinionQueryService,
    UnavailableDecisionOpinionQuery,
)
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.research_memory_approval_contracts import (
    DisabledResearchMemoryApprovalVerifier,
    ResearchMemoryApprovalVerifier,
)

from ditto_apps.registry.agent.campaign_runtime import (
    DisabledCampaignRuntime,
    PersistedCampaignRuntime,
)
from ditto_apps.registry.agent.database_provider import (
    AgentDatabaseBundle,
    build_agent_database,
)
from ditto_apps.registry.agent.decision_briefing import (
    DecisionOpinionShadowStoreBundle,
    build_decision_opinion_shadow_store,
)
from ditto_apps.registry.agent.observability import build_agent_observability
from ditto_apps.registry.agent.runtime import (
    DisabledAgentRuntime,
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from ditto_apps.registry.agent.settings import AgentFeatureSettings


def _clock() -> datetime:
    return datetime.now(UTC)


def _manifest(settings: AgentFeatureSettings) -> AgentManifest:
    profile = "live-enabled" if settings.model_calls_available else "offline"
    return AgentManifest(
        manifest_id=f"r5-governed-{profile}",
        agent_version="r5",
        prompt_version="governed-evidence-v1",
        prompt_hash=canonical_sha256({"prompt": "governed-evidence-v1"}),
        tool_schema_version="governed-tools-v1",
        tool_schema_hash=canonical_sha256({"tools": "governed-tools-v1"}),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=profile,
    )


@dataclass(frozen=True, slots=True)
class AgentRuntimeResources:
    """Apps-owned optional databases shared by enabled Agent surfaces."""

    database: AgentDatabaseBundle | None
    manifest: AgentManifest | None
    decision_store: DecisionOpinionShadowStoreBundle | None


class AgentRuntimeProvider(Provider):
    """Keep defaults closed and compose local persisted surfaces when enabled."""

    scope = Scope.APP

    @provide
    def feature_settings(self) -> AgentFeatureSettings:
        """Read the closed R5 flag set at the composition root."""
        return AgentFeatureSettings.from_environment()

    @provide
    def resources(
        self,
        settings: AgentFeatureSettings,
        data_root: Path,
    ) -> Iterator[AgentRuntimeResources]:
        """Own optional Agent database lifecycles without probing when disabled."""
        if not settings.agent_enabled:
            yield AgentRuntimeResources(None, None, None)
            return
        database = build_agent_database(data_root)
        decision_store: DecisionOpinionShadowStoreBundle | None = None
        try:
            manifest = _manifest(settings)
            database.writer.put_manifest(manifest)
            if settings.decision_shadow_available:
                decision_store = build_decision_opinion_shadow_store(data_root)
            yield AgentRuntimeResources(database, manifest, decision_store)
        finally:
            if decision_store is not None:
                decision_store.close()
            database.close()

    @provide
    def runtime(
        self,
        settings: AgentFeatureSettings,
        resources: AgentRuntimeResources,
    ) -> AgentRuntimePort:
        """Expose durable local sessions and runs behind the master flag."""
        if not settings.agent_enabled:
            return DisabledAgentRuntime("agent_feature_disabled")
        if resources.database is None or resources.manifest is None:
            return DisabledAgentRuntime("agent_database_unavailable")
        return PersistedAgentRuntime(
            reader=resources.database.reader,
            writer=resources.database.writer,
            manifest=resources.manifest,
            clock=_clock,
            options=PersistedAgentRuntimeOptions(
                provider_name="local-governed",
                presentation_reader=resources.database.presentation_reader,
                presentation_writer=resources.database.presentation_writer,
            ),
        )

    @provide
    def agent_observability(
        self,
        settings: AgentFeatureSettings,
    ) -> AgentObservability:
        """Keep Agent OTel export disabled pending an explicit feature profile."""
        return build_agent_observability(enabled=settings.agent_enabled)

    @provide
    def campaign_runtime(
        self,
        settings: AgentFeatureSettings,
        resources: AgentRuntimeResources,
        coordinator: AutonomousCampaignCoordinator,
        reader: CampaignReaderProtocol,
    ) -> CampaignRuntimePort:
        """Compose Campaign mutations only under the explicit Campaign flag."""
        if not settings.campaign_available or resources.database is None:
            return DisabledCampaignRuntime()
        return PersistedCampaignRuntime(
            coordinator=coordinator,
            reader=reader,
            idempotency_reader=resources.database.reader,
            idempotency_writer=resources.database.writer,
            clock=_clock,
        )

    @provide
    def decision_briefing_evidence_query(
        self,
        facade: DecisionEvidenceQueryFacade,
    ) -> DecisionBriefingEvidenceQueryPort:
        """Expose the existing exact-V3 facade through its leaf protocol."""
        return facade

    @provide
    def decision_opinion_query(
        self,
        settings: AgentFeatureSettings,
        resources: AgentRuntimeResources,
        evidence_reader: DecisionBriefingEvidenceQueryPort,
    ) -> DecisionOpinionQueryPort:
        """Compose exact-provenance shadow reads when explicitly enabled."""
        if not settings.decision_shadow_available:
            return UnavailableDecisionOpinionQuery()
        if resources.decision_store is None:
            return UnavailableDecisionOpinionQuery("decision_opinion_store_unavailable")
        return DecisionOpinionQueryService(
            evidence_reader=evidence_reader,
            opinion_reader=resources.decision_store.query_reader,
        )

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


__all__ = ["AgentRuntimeProvider", "AgentRuntimeResources"]
