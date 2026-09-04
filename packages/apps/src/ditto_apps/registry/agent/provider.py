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
from ditto_agent.tools._common import EvidenceFunctionTool
from ditto_agent.tools.account_event import AccountEventEvidenceTool
from ditto_agent.tools.author import (
    AuthorCompileExpressionTool,
    AuthorDiffStrategyTool,
    AuthorDraftStrategyTool,
    AuthorValidateStrategyTool,
)
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_agent.tools.decision import DecisionEvidenceTool
from ditto_agent.tools.market_context import MarketContextEvidenceTool
from ditto_agent.tools.memory import ResearchMemoryTool
from ditto_agent.tools.portfolio import PortfolioEvidenceTool
from ditto_agent.tools.portfolio_comparison import (
    PortfolioComparisonEvidenceTool,
    PortfolioScenarioPreviewTool,
)
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_agent.tools.research import (
    BacktestEvidenceTool,
    ExperimentEvidenceTool,
    FactorEvidenceTool,
    StrategyEvidenceTool,
)
from ditto_agent.tools.risk import RiskEvidenceTool
from ditto_agent.tools.selection import (
    IndustryRotationEvidenceTool,
    SelectionRunEvidenceTool,
)
from ditto_agent.tools.technical_analysis import InstrumentTechnicalEvidenceTool
from ditto_analysis.experiments.campaign_persistence import CampaignReaderProtocol
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_application.agent_campaign_runtime import CampaignRuntimePort
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
)
from ditto_application.queries.account_event_evidence import (
    AccountEventEvidenceQueryFacade,
)
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_application.queries.decision_briefing_contracts import (
    DecisionBriefingEvidenceQueryPort,
)
from ditto_application.queries.decision_evidence import DecisionEvidenceQueryFacade
from ditto_application.queries.decision_opinion import (
    DecisionOpinionQueryPort,
    DecisionOpinionQueryService,
    UnavailableDecisionOpinionQuery,
)
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_application.queries.portfolio_comparison_evidence import (
    PortfolioComparisonEvidenceQueryFacade,
)
from ditto_application.queries.research_evidence import ResearchEvidenceQueryFacade
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.queries.selection_evidence import (
    IndustryRotationEvidenceQueryFacade,
    SelectionRunEvidenceQueryFacade,
)
from ditto_application.queries.technical_analysis_evidence import (
    InstrumentTechnicalEvidenceQueryFacade,
)
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
from ditto_apps.registry.agent.model_provider import (
    AgentModelProviderSettings,
    build_agent_model,
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


def _tool_schema_hash(registry: EvidenceToolRegistry) -> str:
    return canonical_sha256(
        tuple(
            {
                "kind": spec.kind,
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "requires_approval": spec.requires_approval,
            }
            for spec in registry.specs
        )
    )


def _manifest(
    settings: AgentFeatureSettings,
    registry: EvidenceToolRegistry,
) -> AgentManifest:
    profile = "live-enabled" if settings.model_calls_available else "offline"
    return AgentManifest(
        manifest_id=f"r5-governed-{profile}",
        agent_version="r5",
        prompt_version="governed-evidence-v1",
        prompt_hash=canonical_sha256({"prompt": "governed-evidence-v1"}),
        tool_schema_version="governed-tools-v1",
        tool_schema_hash=_tool_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=profile,
    )


@dataclass(frozen=True, slots=True)
class AgentRuntimeResources:
    """Apps-owned optional databases shared by enabled Agent surfaces."""

    database: AgentDatabaseBundle | None
    manifest: AgentManifest | None
    decision_store: DecisionOpinionShadowStoreBundle | None


@dataclass(frozen=True, slots=True)
class _CoreEvidenceTools:
    tools: tuple[EvidenceFunctionTool, ...]


@dataclass(frozen=True, slots=True)
class _WorkflowEvidenceTools:
    tools: tuple[EvidenceFunctionTool, ...]


class AgentRuntimeProvider(Provider):
    """Keep defaults closed and compose local persisted surfaces when enabled."""

    scope = Scope.APP

    @provide
    def feature_settings(self) -> AgentFeatureSettings:
        """Read the closed R5 flag set at the composition root."""
        return AgentFeatureSettings.from_environment()

    @provide
    def model_settings(self) -> AgentModelProviderSettings:
        """Load provider identity and secret only at the Apps composition root."""
        return AgentModelProviderSettings.from_environment()

    @provide
    def core_evidence_tools(
        self,
        decision: DecisionEvidenceQueryFacade,
        market_context: MarketContextEvidenceQueryFacade,
        industry_rotation: IndustryRotationEvidenceQueryFacade,
        selection_run: SelectionRunEvidenceQueryFacade,
        technical_analysis: InstrumentTechnicalEvidenceQueryFacade,
    ) -> _CoreEvidenceTools:
        """Build the context/selection/decision evidence group."""
        return _CoreEvidenceTools(
            tools=(
                DecisionEvidenceTool(facade=decision),
                MarketContextEvidenceTool(facade=market_context),
                IndustryRotationEvidenceTool(facade=industry_rotation),
                SelectionRunEvidenceTool(facade=selection_run),
                InstrumentTechnicalEvidenceTool(facade=technical_analysis),
                PortfolioEvidenceTool(facade=decision),
                RiskEvidenceTool(facade=decision),
            )
        )

    @provide
    def workflow_evidence_tools(
        self,
        research: ResearchEvidenceQueryFacade,
        portfolio_comparison: PortfolioComparisonEvidenceQueryFacade,
        authoring_preview: AuthoringPreviewFacade,
        account_event: AccountEventEvidenceQueryFacade,
    ) -> _WorkflowEvidenceTools:
        """Build research, portfolio, Manual, and Author preview tools."""
        return _WorkflowEvidenceTools(
            tools=(
                PortfolioComparisonEvidenceTool(facade=portfolio_comparison),
                PortfolioScenarioPreviewTool(facade=portfolio_comparison),
                AccountEventEvidenceTool(facade=account_event),
                BacktestEvidenceTool(facade=research),
                ExperimentEvidenceTool(facade=research),
                FactorEvidenceTool(facade=research),
                StrategyEvidenceTool(facade=research),
                AuthorDraftStrategyTool(facade=authoring_preview),
                AuthorCompileExpressionTool(facade=authoring_preview),
                AuthorValidateStrategyTool(facade=authoring_preview),
                AuthorDiffStrategyTool(facade=authoring_preview),
            )
        )

    @provide
    def evidence_tool_registry(
        self,
        core: _CoreEvidenceTools,
        workflows: _WorkflowEvidenceTools,
    ) -> EvidenceToolRegistry:
        """Register the fixed R5 read-only evidence surface over Application."""
        return EvidenceToolRegistry(tools=(*core.tools, *workflows.tools))

    @provide
    def resources(
        self,
        settings: AgentFeatureSettings,
        data_root: Path,
        registry: EvidenceToolRegistry,
    ) -> Iterator[AgentRuntimeResources]:
        """Own optional Agent database lifecycles without probing when disabled."""
        if not settings.agent_enabled:
            yield AgentRuntimeResources(None, None, None)
            return
        database = build_agent_database(data_root)
        decision_store: DecisionOpinionShadowStoreBundle | None = None
        try:
            manifest = _manifest(settings, registry)
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
        model_settings: AgentModelProviderSettings,
        registry: EvidenceToolRegistry,
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
                provider_name=(
                    model_settings.provider.value
                    if settings.model_calls_available
                    else None
                ),
                presentation_reader=resources.database.presentation_reader,
                presentation_writer=resources.database.presentation_writer,
                presentation_projector=resources.database.presentation_projector,
                episode_writer=resources.database.episode_writer,
                tool_registry=registry,
                model_factory=(
                    (
                        lambda invoker: build_agent_model(
                            model_settings,
                            tool_invoker=invoker,
                        )
                    )
                    if settings.model_calls_available
                    else None
                ),
                approved_license_classes=model_settings.approved_license_classes,
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
