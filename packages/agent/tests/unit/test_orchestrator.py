from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
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
from ditto_agent.models.fake import ScriptedAgentModel, ScriptedFailure, ScriptedOutcome
from ditto_agent.models.port import (
    ModelFailureKind,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
    ResumeModelRequest,
)
from ditto_agent.runtime.budgets import BudgetLedger, BudgetLimits, ModelPricing
from ditto_agent.runtime.egress_policy import EvidenceEgressPolicy
from ditto_agent.runtime.guardrails import GuardedEvidenceToolExecutor
from ditto_agent.runtime.orchestrator import (
    AgentOrchestrationRequest,
    GovernedAgentOrchestrator,
)
from ditto_agent.tools.registry import EvidenceToolRegistry


class _Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.current = datetime(2026, 8, 16, 8, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return self.current


class _EvidenceTool:
    spec = ModelToolSpec(
        kind=ModelToolKind.FUNCTION,
        name="research_experiment_evidence",
        description="Read an experiment.",
        input_schema={
            "type": "object",
            "properties": {"experiment_id": {"type": "string"}},
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        requires_approval=False,
    )

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        return EvidenceEnvelope.seal(
            evidence_id=f"evidence-{arguments['experiment_id']}",
            tool_name=self.spec.name,
            result={"status": "completed", "metric": 0.73},
            artifact_refs=("experiment:001:sha256:" + "a" * 64,),
            temporal_context=context,
            lineage=("experiment:001",),
        )


class _InvokingModel:
    def __init__(self, executor: GuardedEvidenceToolExecutor) -> None:
        self._executor = executor
        self.requests: list[ModelRequest] = []

    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        call = ModelToolCall(
            call_id="call-001",
            tool_name="research_experiment_evidence",
            arguments={"experiment_id": "experiment-001"},
        )
        payload = await self._executor.invoke(
            call.tool_name,
            '{"experiment_id":"experiment-001"}',
            call_id=call.call_id,
        )
        return ModelResult(
            final_output={
                "claims": [
                    {
                        "claim": "The experiment completed with IR 0.73.",
                        "evidence_refs": [payload["evidence_id"]],
                    }
                ],
                "uncertainty": "Bound to snapshot-1.",
            },
            tool_calls=(call,),
            usage=ModelUsage(requests=2, input_tokens=100, output_tokens=30),
            interruptions=(),
            continuation=None,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        result = await self.run(request)
        yield ModelStreamEvent(kind=ModelStreamEventKind.COMPLETED, result=result)

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise AssertionError("read-only orchestration must not resume an interruption")


class _ToolThenFailureModel:
    def __init__(self, executor: GuardedEvidenceToolExecutor) -> None:
        self._executor = executor

    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        await self._executor.invoke(
            "research_experiment_evidence",
            '{"experiment_id":"experiment-001"}',
            call_id="call-before-failure",
        )
        raise ModelProviderError("provider stopped after tool execution")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        raise AssertionError("orchestration uses the non-streaming boundary")
        yield

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise AssertionError("read-only orchestration must not resume an interruption")


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 16, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 16, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 16, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-1",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _limits(**overrides: object) -> BudgetLimits:
    values: dict[str, object] = {
        "max_turns": 4,
        "max_model_tokens": 1_000,
        "max_model_spend_usd": Decimal("0.10"),
        "max_wall_time_seconds": 30.0,
        "max_retries": 1,
    }
    values.update(overrides)
    return BudgetLimits(**values)


def _runtime(
    *,
    limits: BudgetLimits | None = None,
) -> tuple[
    _Clock,
    BudgetLedger,
    GuardedEvidenceToolExecutor,
    AgentOrchestrationRequest,
]:
    clock = _Clock()
    selected_limits = limits or _limits()
    budget = BudgetLedger(
        limits=selected_limits,
        pricing=ModelPricing(
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("4"),
        ),
        monotonic=clock.monotonic,
    )
    tool = _EvidenceTool()
    executor = GuardedEvidenceToolExecutor(
        registry=EvidenceToolRegistry(tools=(tool,)),
        context=_context(),
        authority_hash="a" * 64,
        allowed_tools=(tool.spec.name,),
        egress_policy=EvidenceEgressPolicy(
            approved_license_classes=("approved-research",)
        ),
        budget=budget,
    )
    manifest = AgentManifest(
        manifest_id="manifest-r5-read-v1",
        agent_version="r5.1.0",
        prompt_version="evidence-v1",
        prompt_hash="b" * 64,
        tool_schema_version="read-tools-v1",
        tool_schema_hash=executor.tool_schema_hash,
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )
    run = AgentRun(
        run_id="run-001",
        session_id="session-001",
        status=RunStatus.QUEUED,
        objective="Explain experiment-001.",
        authority_hash="a" * 64,
        max_model_tokens=selected_limits.max_model_tokens,
        max_model_spend_usd=selected_limits.max_model_spend_usd,
        model_profile=ModelProfile.BALANCED,
        manifest_hash=manifest.manifest_hash,
        created_at=clock.now(),
    )
    request = AgentOrchestrationRequest(
        run=run,
        manifest=manifest,
        temporal_context=_context(),
        agent_name="evidence-copilot",
        instructions="Return claim intents citing only tool evidence IDs.",
        allowed_tools=(tool.spec.name,),
        max_output_tokens=min(256, selected_limits.max_model_tokens),
    )
    return clock, budget, executor, request


def _terminal_result(*, usage: ModelUsage | None = None) -> ModelResult:
    return ModelResult(
        final_output={"claims": [], "uncertainty": None},
        tool_calls=(),
        usage=usage or ModelUsage(requests=1, input_tokens=10, output_tokens=5),
        interruptions=(),
        continuation=None,
    )


@pytest.mark.asyncio
async def test_orchestrator_completes_only_grounded_claims_and_full_episode() -> None:
    clock, budget, executor, request = _runtime()
    model = _InvokingModel(executor)
    orchestrator = GovernedAgentOrchestrator(
        model=model,
        tool_executor=executor,
        budget=budget,
        clock=clock,
    )

    outcome = await orchestrator.execute(request)

    assert outcome.status is RunStatus.COMPLETED
    assert outcome.failure_code is None
    assert outcome.answer is not None
    assert outcome.answer.refusal_reason is None
    assert outcome.answer.claims[0].evidence_refs == ("evidence-experiment-001",)
    assert outcome.episode is not None
    assert outcome.episode.verify_manifest_hash()
    assert outcome.episode.tool_calls[0].call_id == "call-001"
    assert outcome.episode.tool_results[0].evidence_refs == ("evidence-experiment-001",)
    assert outcome.events[-1].event_type == "run_completed"
    assert model.requests[0].max_turns == budget.limits.max_turns
    assert model.requests[0].tools == executor.specs


@pytest.mark.asyncio
async def test_transient_failure_retries_once_then_returns_structured_refusal() -> None:
    clock, budget, executor, request = _runtime()
    model = ScriptedAgentModel(
        script=(
            ScriptedFailure(ModelFailureKind.RATE_LIMIT, "retry later"),
            ScriptedOutcome(result=_terminal_result()),
        )
    )
    outcome = await GovernedAgentOrchestrator(
        model=model,
        tool_executor=executor,
        budget=budget,
        clock=clock,
    ).execute(request)

    assert outcome.status is RunStatus.COMPLETED
    assert outcome.answer is not None
    assert outcome.answer.refusal_reason == "no_grounded_claims"
    assert outcome.budget.retries == 1
    assert len(model.requests) == 2
    assert any(event.event_type == "provider_retry" for event in outcome.events)


@pytest.mark.asyncio
async def test_budget_overrun_pauses_without_any_further_provider_call() -> None:
    limits = _limits(max_turns=2, max_model_tokens=100)
    clock, budget, executor, request = _runtime(limits=limits)
    model = ScriptedAgentModel(
        script=(
            ScriptedOutcome(
                result=_terminal_result(
                    usage=ModelUsage(
                        requests=3,
                        input_tokens=90,
                        output_tokens=11,
                    )
                )
            ),
            ScriptedOutcome(result=_terminal_result()),
        )
    )
    outcome = await GovernedAgentOrchestrator(
        model=model,
        tool_executor=executor,
        budget=budget,
        clock=clock,
    ).execute(request)

    assert outcome.status is RunStatus.PAUSED
    assert outcome.failure_code in {
        "max_model_tokens_exceeded",
        "max_turns_exceeded",
    }
    assert outcome.answer is None
    assert outcome.episode is None
    assert len(model.requests) == 1
    assert model.requests[0].max_turns == 2


@pytest.mark.asyncio
async def test_nontransient_provider_failure_is_terminal_and_never_fabricated() -> None:
    clock, budget, executor, request = _runtime()
    model = ScriptedAgentModel(
        script=(ScriptedFailure(ModelFailureKind.PROVIDER, "provider unavailable"),)
    )
    outcome = await GovernedAgentOrchestrator(
        model=model,
        tool_executor=executor,
        budget=budget,
        clock=clock,
    ).execute(request)

    assert outcome.status is RunStatus.FAILED
    assert outcome.failure_code == "model_provider_failed"
    assert outcome.answer is None
    assert outcome.episode is not None
    assert outcome.episode.final_status is RunStatus.FAILED
    assert outcome.episode.final_output_hash is None
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_failure_after_tool_execution_keeps_complete_audit_episode() -> None:
    clock, budget, executor, request = _runtime()
    outcome = await GovernedAgentOrchestrator(
        model=_ToolThenFailureModel(executor),
        tool_executor=executor,
        budget=budget,
        clock=clock,
    ).execute(request)

    assert outcome.status is RunStatus.FAILED
    assert outcome.episode is not None
    assert outcome.episode.tool_calls[0].call_id == "call-before-failure"
    assert tuple(event.event_type for event in outcome.events[-3:]) == (
        "tool_call",
        "tool_result",
        "run_failed",
    )


@pytest.mark.asyncio
async def test_reported_tool_call_without_host_execution_fails_closed() -> None:
    clock, budget, executor, request = _runtime()
    call = ModelToolCall(
        call_id="call-unexecuted",
        tool_name="research_experiment_evidence",
        arguments={"experiment_id": "experiment-001"},
    )
    model = ScriptedAgentModel(
        script=(
            ScriptedOutcome(
                result=ModelResult(
                    final_output={
                        "claims": [
                            {
                                "claim": "Fabricated completion.",
                                "evidence_refs": ["evidence-experiment-001"],
                            }
                        ],
                        "uncertainty": None,
                    },
                    tool_calls=(call,),
                    usage=ModelUsage(requests=1, input_tokens=10, output_tokens=5),
                    interruptions=(),
                    continuation=None,
                )
            ),
        )
    )
    outcome = await GovernedAgentOrchestrator(
        model=model,
        tool_executor=executor,
        budget=budget,
        clock=clock,
    ).execute(request)

    assert outcome.status is RunStatus.FAILED
    assert outcome.failure_code == "tool_execution_mismatch"
    assert outcome.answer is None
    assert outcome.episode is not None
