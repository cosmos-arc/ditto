"""Deterministic single-Agent orchestration with bounded model authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.evidence import GroundedAnswer
from ditto_agent.contracts.runtime import AgentManifest, AgentRun, RunStatus
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.grounding import GroundingBuilder, GroundingDraft
from ditto_agent.models.port import (
    AgentModelPort,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelToolCall,
)
from ditto_agent.runtime.budgets import BudgetExceeded, BudgetLedger, BudgetSnapshot
from ditto_agent.runtime.egress_policy import EvidenceEgressPolicyError
from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    EpisodeToolCallRecord,
    EpisodeToolEffect,
    EpisodeToolResultRecord,
)
from ditto_agent.runtime.guardrails import (
    GuardedEvidenceToolExecutor,
    ToolGuardrailViolation,
)
from ditto_agent.runtime.state_machine import transition_run


class RuntimeClock(Protocol):
    """Explicit time boundary required by orchestration and episode sealing."""

    def monotonic(self) -> float:
        """Return process-local monotonic seconds."""
        ...

    def now(self) -> datetime:
        """Return the current aware wall-clock timestamp."""
        ...


@dataclass(frozen=True, slots=True)
class AgentOrchestrationRequest:
    """Host-selected immutable inputs for one governed read-only run."""

    run: AgentRun
    manifest: AgentManifest
    temporal_context: TemporalToolContext
    agent_name: str
    instructions: str
    allowed_tools: tuple[str, ...]
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class AgentOrchestrationOutcome:
    """Terminal or paused orchestration result with audit evidence."""

    status: RunStatus
    failure_code: str | None
    answer: GroundedAnswer | None
    budget: BudgetSnapshot
    events: tuple[EpisodeEventRecord, ...]
    episode: AgentEpisodeManifest | None


class _EventChain:
    def __init__(self, *, run_id: str, clock: RuntimeClock) -> None:
        self._run_id = run_id
        self._clock = clock
        self._events: list[EpisodeEventRecord] = []

    @property
    def events(self) -> tuple[EpisodeEventRecord, ...]:
        return tuple(self._events)

    def append(self, event_type: str, payload: object) -> None:
        sequence = len(self._events) + 1
        previous = self._events[-1].event_hash if self._events else None
        self._events.append(
            EpisodeEventRecord.create(
                event_id=sequence,
                run_id=self._run_id,
                run_sequence=sequence,
                event_type=event_type,
                payload_hash=canonical_sha256(payload),
                occurred_at=self._clock.now(),
                prev_hash=previous,
            )
        )


def _answer_payload(answer: GroundedAnswer) -> dict[str, object]:
    return {
        "claims": tuple(
            {"claim": claim.claim, "evidence_refs": claim.evidence_refs}
            for claim in answer.claims
        ),
        "uncertainty": answer.uncertainty,
        "missing_evidence": answer.missing_evidence,
        "refusal_reason": answer.refusal_reason,
    }


def _structured_refusal(reason: str) -> GroundedAnswer:
    return GroundedAnswer(
        claims=(),
        uncertainty=None,
        missing_evidence=("model_output",),
        refusal_reason=reason,
    )


def _drafts(result: ModelResult) -> tuple[tuple[GroundingDraft, ...], str | None]:
    output = result.final_output
    if not isinstance(output, Mapping) or set(output) != {"claims", "uncertainty"}:
        raise ValueError("model output must contain claims and uncertainty")
    uncertainty_raw = output["uncertainty"]
    if uncertainty_raw is not None and not isinstance(uncertainty_raw, str):
        raise ValueError("model uncertainty must be text or null")
    claims_raw = output["claims"]
    if not isinstance(claims_raw, (tuple, list)):
        raise ValueError("model claims must be an array")
    drafts: list[GroundingDraft] = []
    for raw_item in cast(tuple[object, ...] | list[object], claims_raw):
        if not isinstance(raw_item, Mapping):
            raise ValueError("each model claim must be an object")
        item = cast(Mapping[str, object], raw_item)
        if set(item) != {
            "claim",
            "evidence_refs",
        }:
            raise ValueError("each model claim must contain claim and evidence_refs")
        claim = item["claim"]
        references = item["evidence_refs"]
        if not isinstance(claim, str) or not isinstance(references, (tuple, list)):
            raise ValueError("model claim fields have invalid types")
        refs = tuple(cast(tuple[object, ...] | list[object], references))
        if not all(isinstance(item, str) for item in refs):
            raise ValueError("model evidence_refs must contain strings")
        drafts.append(
            GroundingDraft(
                claim=claim,
                evidence_refs=cast(tuple[str, ...], refs),
            )
        )
    return tuple(drafts), uncertainty_raw


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or (
        isinstance(exc, ModelProviderError) and str(exc).startswith("rate_limit:")
    )


class GovernedAgentOrchestrator:
    """Run one model loop while the host owns tools, budgets, and final claims."""

    def __init__(
        self,
        *,
        model: AgentModelPort,
        tool_executor: GuardedEvidenceToolExecutor,
        budget: BudgetLedger,
        clock: RuntimeClock,
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor
        self._budget = budget
        self._clock = clock

    def _validate_request(self, request: AgentOrchestrationRequest) -> None:
        if request.run.status is not RunStatus.QUEUED:
            raise ValueError("orchestration requires a queued run")
        if request.run.manifest_hash != request.manifest.manifest_hash:
            raise ValueError("run manifest hash does not match the supplied manifest")
        if request.run.model_profile is not request.manifest.model_profile:
            raise ValueError("run model profile does not match the manifest")
        if request.run.max_model_tokens != self._budget.limits.max_model_tokens:
            raise ValueError("run token limit does not match the budget ledger")
        if request.run.max_model_spend_usd != self._budget.limits.max_model_spend_usd:
            raise ValueError("run spend limit does not match the budget ledger")
        executor_tools = tuple(spec.name for spec in self._tool_executor.specs)
        if request.allowed_tools != executor_tools:
            raise ValueError("run tool allowlist does not match the guarded executor")
        if (
            isinstance(request.max_output_tokens, bool)
            or request.max_output_tokens <= 0
            or request.max_output_tokens > request.run.max_model_tokens
        ):
            raise ValueError("max_output_tokens must fit inside the run token limit")
        self._tool_executor.validate_run(
            authority_hash=request.run.authority_hash,
            context=request.temporal_context,
            tool_schema_hash=request.manifest.tool_schema_hash,
        )

    def _model_request(self, request: AgentOrchestrationRequest) -> ModelRequest:
        return ModelRequest(
            run_id=request.run.run_id,
            agent_name=request.agent_name,
            instructions=request.instructions,
            input_text=request.run.objective,
            max_turns=self._budget.limits.max_turns,
            max_output_tokens=request.max_output_tokens,
            tools=self._tool_executor.specs,
        )

    def _tool_records(
        self,
    ) -> tuple[tuple[EpisodeToolCallRecord, ...], tuple[EpisodeToolResultRecord, ...]]:
        calls = tuple(
            EpisodeToolCallRecord(
                call_id=item.call_id,
                tool_name=item.tool_name,
                arguments_hash=item.arguments_hash,
                effect=EpisodeToolEffect.READ_ONLY,
                action_hash=None,
            )
            for item in self._tool_executor.executions
        )
        results = tuple(
            EpisodeToolResultRecord(
                call_id=item.call_id,
                result_hash=item.evidence.integrity_hash,
                evidence_refs=(item.evidence.evidence_id,),
                artifact_refs=item.evidence.artifact_refs,
            )
            for item in self._tool_executor.executions
        )
        return calls, results

    def _episode(
        self,
        *,
        request: AgentOrchestrationRequest,
        status: RunStatus,
        events: tuple[EpisodeEventRecord, ...],
        answer: GroundedAnswer | None,
    ) -> AgentEpisodeManifest:
        calls, results = self._tool_records()
        return AgentEpisodeManifest(
            episode_id=f"episode-{request.run.run_id}",
            run_id=request.run.run_id,
            input_hash=canonical_sha256(request.run.objective),
            authority_hash=request.run.authority_hash,
            temporal_context_hash=self._tool_executor.temporal_context_hash,
            agent_manifest=request.manifest,
            final_status=status,
            events=events,
            tool_calls=calls,
            tool_results=results,
            final_output_hash=(
                canonical_sha256(_answer_payload(answer))
                if answer is not None
                else None
            ),
            sealed_at=self._clock.now(),
        )

    def _outcome(
        self,
        *,
        request: AgentOrchestrationRequest,
        status: RunStatus,
        failure_code: str | None,
        answer: GroundedAnswer | None,
        chain: _EventChain,
    ) -> AgentOrchestrationOutcome:
        episode = (
            self._episode(
                request=request,
                status=status,
                events=chain.events,
                answer=answer,
            )
            if status in {RunStatus.COMPLETED, RunStatus.FAILED}
            else None
        )
        return AgentOrchestrationOutcome(
            status=status,
            failure_code=failure_code,
            answer=answer,
            budget=self._budget.snapshot(),
            events=chain.events,
            episode=episode,
        )

    def _failed(
        self,
        *,
        request: AgentOrchestrationRequest,
        chain: _EventChain,
        reason: str,
    ) -> AgentOrchestrationOutcome:
        status = transition_run(RunStatus.RUNNING, RunStatus.FAILED)
        self._append_tool_events(chain)
        chain.append("run_failed", {"reason": reason})
        return self._outcome(
            request=request,
            status=status,
            failure_code=reason,
            answer=None,
            chain=chain,
        )

    def _paused(
        self,
        *,
        request: AgentOrchestrationRequest,
        chain: _EventChain,
        reason: str,
    ) -> AgentOrchestrationOutcome:
        status = transition_run(RunStatus.RUNNING, RunStatus.PAUSED)
        self._append_tool_events(chain)
        chain.append("run_paused", {"reason": reason})
        return self._outcome(
            request=request,
            status=status,
            failure_code=reason,
            answer=None,
            chain=chain,
        )

    async def _invoke_model(
        self,
        *,
        request: AgentOrchestrationRequest,
        model_request: ModelRequest,
        chain: _EventChain,
    ) -> ModelResult | AgentOrchestrationOutcome:
        while True:
            executions_before = len(self._tool_executor.executions)
            try:
                self._budget.before_model_attempt()
                chain.append(
                    "provider_attempt",
                    {"attempt": self._budget.snapshot().model_attempts},
                )
                result = await self._model.run(model_request)
                self._budget.record_model_usage(result.usage)
            except BudgetExceeded as exc:
                return self._paused(
                    request=request,
                    chain=chain,
                    reason=exc.reason_code,
                )
            except (EvidenceEgressPolicyError, ToolGuardrailViolation) as exc:
                return self._failed(
                    request=request,
                    chain=chain,
                    reason=exc.reason_code,
                )
            except (TimeoutError, ModelProviderError) as exc:
                no_tool_effect = (
                    len(self._tool_executor.executions) == executions_before
                )
                if not _is_transient(exc) or not no_tool_effect:
                    return self._failed(
                        request=request,
                        chain=chain,
                        reason="model_provider_failed",
                    )
                try:
                    self._budget.register_retry()
                except BudgetExceeded as budget_error:
                    return self._paused(
                        request=request,
                        chain=chain,
                        reason=budget_error.reason_code,
                    )
                chain.append(
                    "provider_retry",
                    {"retry": self._budget.snapshot().retries},
                )
                continue
            return result

    def _append_tool_events(self, chain: _EventChain) -> None:
        for execution in self._tool_executor.executions:
            chain.append(
                "tool_call",
                {
                    "call_id": execution.call_id,
                    "tool_name": execution.tool_name,
                    "arguments_hash": execution.arguments_hash,
                },
            )
            chain.append(
                "tool_result",
                {
                    "call_id": execution.call_id,
                    "result_hash": execution.evidence.integrity_hash,
                },
            )

    @staticmethod
    def _tool_calls_match(
        reported: tuple[ModelToolCall, ...],
        executor: GuardedEvidenceToolExecutor,
    ) -> bool:
        executed = executor.executions
        if len(reported) != len(executed):
            return False
        by_id = {item.call_id: item for item in executed}
        if len(by_id) != len(executed):
            return False
        return all(
            call.call_id in by_id
            and call.tool_name == by_id[call.call_id].tool_name
            and canonical_sha256(call.arguments) == by_id[call.call_id].arguments_hash
            for call in reported
        )

    async def execute(
        self,
        request: AgentOrchestrationRequest,
    ) -> AgentOrchestrationOutcome:
        """Execute one bounded run and seal every terminal outcome."""
        self._validate_request(request)
        _ = transition_run(RunStatus.QUEUED, RunStatus.RUNNING)
        chain = _EventChain(run_id=request.run.run_id, clock=self._clock)
        chain.append(
            "run_started",
            {
                "manifest_hash": request.manifest.manifest_hash,
                "temporal_context_hash": self._tool_executor.temporal_context_hash,
            },
        )
        model_request = self._model_request(request)
        invocation = await self._invoke_model(
            request=request,
            model_request=model_request,
            chain=chain,
        )
        if isinstance(invocation, AgentOrchestrationOutcome):
            return invocation
        result = invocation
        if result.interruptions:
            return self._failed(
                request=request,
                chain=chain,
                reason="model_interruption_not_supported",
            )
        if not self._tool_calls_match(result.tool_calls, self._tool_executor):
            return self._failed(
                request=request,
                chain=chain,
                reason="tool_execution_mismatch",
            )
        self._append_tool_events(chain)
        try:
            drafts, uncertainty = _drafts(result)
            answer = GroundingBuilder(expected_context=request.temporal_context).build(
                drafts=drafts,
                evidence=tuple(
                    item.evidence for item in self._tool_executor.executions
                ),
                uncertainty=uncertainty,
            )
        except (TypeError, ValueError):
            answer = _structured_refusal("model_output_invalid")
        status = transition_run(RunStatus.RUNNING, RunStatus.COMPLETED)
        chain.append(
            "run_completed",
            {"final_output_hash": canonical_sha256(_answer_payload(answer))},
        )
        return self._outcome(
            request=request,
            status=status,
            failure_code=None,
            answer=answer,
            chain=chain,
        )


__all__ = [
    "AgentOrchestrationOutcome",
    "AgentOrchestrationRequest",
    "GovernedAgentOrchestrator",
    "RuntimeClock",
]
