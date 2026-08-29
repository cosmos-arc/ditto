"""Offline R5.1 Evidence Copilot end-to-end acceptance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    ModelProfile,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.fake import ScriptedFailure, ScriptedOutcome
from ditto_agent.models.port import (
    ModelFailureKind,
    ModelResult,
    ModelToolCall,
    ModelUsage,
)
from ditto_agent.runtime.budgets import BudgetLedger, BudgetLimits, ModelPricing
from ditto_agent.runtime.egress_policy import EvidenceEgressPolicy
from ditto_agent.runtime.guardrails import GuardedEvidenceToolExecutor
from ditto_agent.runtime.orchestrator import (
    AgentOrchestrationRequest,
    GovernedAgentOrchestrator,
)
from ditto_agent.runtime.replay import EpisodeReplayer
from ditto_agent.tools._common import application_context, seal_research_evidence
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_agent.tools.research import ExperimentEvidenceTool
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    ResearchEvidenceKind,
    ResearchEvidenceQueryPort,
    ResearchEvidenceReadModel,
)
from ditto_apps.registry.agent.model_provider import (
    AgentModelProviderSettings,
    build_agent_model,
)

_NOW = datetime(2026, 8, 16, 8, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_TOOL_NAME = "research_experiment_evidence"


class _Clock:
    def monotonic(self) -> float:
        return 0.0

    def now(self) -> datetime:
        return _NOW


class _PITExperimentFacade:
    """Application-port fixture that exposes only publication-visible data."""

    def __init__(self, result: ResearchEvidenceReadModel) -> None:
        self._result = result
        self.contexts: list[object] = []

    def get_experiment_evidence(
        self,
        *,
        experiment_id: str,
        context: EvidenceTemporalContext,
        candidate_id: str | None = None,
        fold_id: str | None = None,
    ) -> ResearchEvidenceReadModel:
        del experiment_id, candidate_id, fold_id
        self.contexts.append(context)
        return self._result


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=_NOW,
            knowledge_cutoff=datetime(2026, 8, 16, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 16, 6, tzinfo=UTC),
            source_snapshot_id="snapshot-r51",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _read_model(context: TemporalToolContext) -> ResearchEvidenceReadModel:
    return ResearchEvidenceReadModel(
        kind=ResearchEvidenceKind.EXPERIMENT,
        subject_id="experiment-r51",
        subject_version="4",
        strategy_id="strategy-r51",
        strategy_version="3",
        dataset_id="etf-daily",
        temporal_context=application_context(context),
        payload=EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "status": "completed",
                "visible_metric": 0.73,
                "publication_cutoff": "2026-08-16T06:00:00Z",
            },
        ),
        artifact_refs=(
            EvidenceArtifactReference(
                artifact_id="artifact-r51",
                artifact_kind="experiment_report",
                content_hash=_HASH_A,
                schema_hash=_HASH_B,
            ),
        ),
        lineage=("experiment:experiment-r51", "snapshot:snapshot-r51"),
    )


def _runtime(
    *,
    script: tuple[ScriptedOutcome | ScriptedFailure, ...],
) -> tuple[
    GovernedAgentOrchestrator,
    AgentOrchestrationRequest,
    GuardedEvidenceToolExecutor,
    _PITExperimentFacade,
]:
    context = _context()
    read_model = _read_model(context)
    facade = _PITExperimentFacade(read_model)
    tool = ExperimentEvidenceTool(facade=cast(ResearchEvidenceQueryPort, facade))
    budget = BudgetLedger(
        limits=BudgetLimits(
            max_turns=4,
            max_model_tokens=1_000,
            max_model_spend_usd=Decimal("0.25"),
            max_wall_time_seconds=30.0,
            max_retries=1,
        ),
        pricing=ModelPricing(
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("4"),
        ),
        monotonic=_Clock().monotonic,
    )
    executor = GuardedEvidenceToolExecutor(
        registry=EvidenceToolRegistry(tools=(tool,)),
        context=context,
        authority_hash=_HASH_A,
        allowed_tools=(_TOOL_NAME,),
        egress_policy=EvidenceEgressPolicy(
            approved_license_classes=("approved-research",)
        ),
        budget=budget,
    )
    manifest = AgentManifest(
        manifest_id="manifest-r51-e2e-v1",
        agent_version="r5.1.0",
        prompt_version="evidence-v1",
        prompt_hash=_HASH_B,
        tool_schema_version="read-tools-v1",
        tool_schema_hash=executor.tool_schema_hash,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )
    run = AgentRun(
        run_id="run-r51-e2e",
        session_id="session-r51-e2e",
        status=RunStatus.QUEUED,
        objective="Explain experiment-r51 without using future publications.",
        authority_hash=_HASH_A,
        max_model_tokens=1_000,
        max_model_spend_usd=Decimal("0.25"),
        model_profile=ModelProfile.BALANCED,
        manifest_hash=manifest.manifest_hash,
        created_at=_NOW,
    )
    model = build_agent_model(
        AgentModelProviderSettings(),
        script=script,
        tool_invoker=executor,
    )
    return (
        GovernedAgentOrchestrator(
            model=model,
            tool_executor=executor,
            budget=budget,
            clock=_Clock(),
        ),
        AgentOrchestrationRequest(
            run=run,
            manifest=manifest,
            temporal_context=context,
            agent_name="evidence-copilot",
            instructions="Use only host tools and cite every factual claim.",
            allowed_tools=(_TOOL_NAME,),
            max_output_tokens=256,
        ),
        executor,
        facade,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_fake_evidence_copilot_is_grounded_pit_safe_and_replayable() -> None:
    context = _context()
    expected = seal_research_evidence(
        tool_name=_TOOL_NAME,
        expected_kind=ResearchEvidenceKind.EXPERIMENT.value,
        read_model=_read_model(context),
        context=context,
    )
    call = ModelToolCall(
        call_id="call-r51-e2e",
        tool_name=_TOOL_NAME,
        arguments={
            "experiment_id": "experiment-r51",
            "candidate_id": None,
            "fold_id": None,
        },
    )
    result = ModelResult(
        final_output={
            "claims": [
                {
                    "claim": "The visible host metric is 0.73.",
                    "evidence_refs": [expected.evidence_id],
                }
            ],
            "uncertainty": "Bound to snapshot-r51 and the publication cutoff.",
        },
        tool_calls=(call,),
        usage=ModelUsage(requests=2, input_tokens=120, output_tokens=40),
        interruptions=(),
        continuation=None,
    )
    orchestrator, request, executor, facade = _runtime(
        script=(ScriptedOutcome(result=result),)
    )

    outcome = await orchestrator.execute(request)

    assert outcome.status is RunStatus.COMPLETED
    assert outcome.answer is not None
    assert outcome.answer.claims[0].evidence_refs == (expected.evidence_id,)
    assert facade.contexts == [application_context(context)]
    evidence_payload = cast(
        Mapping[str, object],
        executor.executions[0].evidence.result["payload"],
    )
    assert evidence_payload["visible_metric"] == 0.73
    assert "future_sentinel" not in evidence_payload
    assert outcome.budget.model_spend_usd <= Decimal("0.25")
    assert outcome.episode is not None
    first = EpisodeReplayer().replay(outcome.episode)
    second = EpisodeReplayer().replay(outcome.episode)
    assert first == second
    assert first.replay_identity == outcome.episode.replay_identity


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_fake_provider_failure_is_terminal_and_never_fabricates_evidence() -> (
    None
):
    orchestrator, request, executor, facade = _runtime(
        script=(
            ScriptedFailure(
                kind=ModelFailureKind.PROVIDER,
                message="offline provider unavailable",
            ),
        )
    )

    outcome = await orchestrator.execute(request)

    assert outcome.status is RunStatus.FAILED
    assert outcome.failure_code == "model_provider_failed"
    assert outcome.answer is None
    assert not executor.executions
    assert not facade.contexts
    assert outcome.episode is not None
    assert EpisodeReplayer().replay(outcome.episode).tool_results == ()
