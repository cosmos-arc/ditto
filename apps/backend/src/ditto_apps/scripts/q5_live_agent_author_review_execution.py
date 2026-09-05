"""Execute one exactly approved Q5 Agent Author review submission."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_sha256
from ditto_agent.approval_runtime import (
    AgentApprovalRuntime,
    ApprovalActionResolver,
    ApprovalRuntimeSettings,
)
from ditto_agent.authoring_approval import ApprovalRuntimeAuthoringVerifier
from ditto_agent.contracts.approval import ActionBudget, ApprovalAction
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import (
    AgentModelPort,
    ModelContinuation,
    ModelInterruption,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelToolCall,
    ModelUsage,
    ResumeModelRequest,
)
from ditto_agent.tools.author_write import (
    AuthorSubmitStrategyReviewTool,
    AuthorWriteToolInvoker,
    AuthorWriteToolRegistry,
)
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalVerifier,
    AgentAuthoringCommandPort,
)

from ditto_apps.registry.agent.database_provider import build_agent_database

_HASH = re.compile(r"[0-9a-f]{64}")
_EXPECTED_TOOL = "author_submit_strategy_review"
_EXPECTED_STRATEGY_ID = "agent_etf_518880_rotation"
_EXPECTED_STRATEGY_VERSION = 1


@dataclass(frozen=True, slots=True)
class ApprovedReviewRequest:
    """One operator-approved submit-review request and its frozen lineage."""

    arguments: Mapping[str, object]
    request_hash: str
    arguments_hash: str
    bundle_hash: str
    experiment_id: str
    spec_hash: str
    planning_document_hash: str
    snapshot_manifest_hash: str
    knowledge_cutoff: str
    publication_cutoff: str
    source_snapshot_ids: tuple[str, ...]
    selection_run_id: str
    research_case_id: str
    market_context_feature_set_id: str
    technical_snapshot_id: str


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(type(key) is str for key in raw):
        raise ValueError(f"{field} must have string keys")
    return cast("Mapping[str, object]", raw)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _timestamp(value: object, *, field: str) -> tuple[str, datetime]:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone aware")
    utc = parsed.astimezone(UTC)
    return utc.isoformat().replace("+00:00", "Z"), utc


AgentAuthoringFacadeFactory = Callable[
    [AgentAuthoringApprovalVerifier], AgentAuthoringCommandPort
]


@dataclass(frozen=True, slots=True)
class _ExactReviewActionResolver(ApprovalActionResolver):
    authority_hash: str
    temporal_context: TemporalToolContext

    def resolve(
        self,
        *,
        run_id: str,
        interruption: ModelInterruption,
        expires_at: datetime,
    ) -> ApprovalAction:
        del run_id
        return ApprovalAction(
            action_kind="formal_author_write",
            tool_name=interruption.tool_name,
            parameters=interruption.arguments,
            subject_identity=_text(
                interruption.arguments.get("strategy_id"), field="strategy_id"
            ),
            required_authority="strategy.author",
            authority_hash=self.authority_hash,
            temporal_context=self.temporal_context,
            budget=ActionBudget(
                max_tool_calls=1,
                max_output_bytes=65_536,
                max_model_tokens=1,
                max_model_spend_usd=Decimal(0),
            ),
            expires_at=expires_at,
        )


class _ExactReviewResumeModel(AgentModelPort):
    """Local continuation executor; it never calls a model provider."""

    def __init__(self, *, arguments: Mapping[str, object], call_id: str) -> None:
        self._arguments = dict(arguments)
        self._call_id = call_id
        self.invoker: AuthorWriteToolInvoker | None = None

    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        raise RuntimeError("Q5 exact-review model supports resume only")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        if False:  # pragma: no cover - structural async-generator marker
            yield cast("ModelStreamEvent", None)
        raise RuntimeError("Q5 exact-review model does not stream")

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        if (
            len(request.decisions) != 1
            or request.decisions[0].call_id != self._call_id
            or request.decisions[0].approved is not True
            or self.invoker is None
        ):
            raise RuntimeError("Q5 exact-review continuation lacks exact approval")
        result = await self.invoker.invoke(
            _EXPECTED_TOOL,
            orjson.dumps(self._arguments, option=orjson.OPT_SORT_KEYS).decode(),
            call_id=self._call_id,
        )
        result_mapping = _mapping(result, field="author review tool result")
        return ModelResult(
            final_output={
                "submitted": True,
                "evidence_id": result_mapping.get("evidence_id"),
            },
            tool_calls=(
                ModelToolCall(
                    call_id=self._call_id,
                    tool_name=_EXPECTED_TOOL,
                    arguments=self._arguments,
                ),
            ),
            usage=ModelUsage(requests=0, input_tokens=0, output_tokens=0),
            interruptions=(),
            continuation=None,
        )


def _temporal_context(
    approved: ApprovedReviewRequest,
    *,
    decision_time: datetime,
) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=_timestamp(
                approved.knowledge_cutoff, field="knowledge_cutoff"
            )[1],
            publication_cutoff=_timestamp(
                approved.publication_cutoff, field="publication_cutoff"
            )[1],
            source_snapshot_id=approved.source_snapshot_ids[0],
            execution_eligible_at="not_applicable",
            allowed_universe=("518880.SH",),
            license_class="approved-research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _manifest(tool: AuthorSubmitStrategyReviewTool) -> AgentManifest:
    return AgentManifest(
        manifest_id="personal-workstation-q5-exact-review",
        agent_version="r5.2",
        prompt_version="q5-exact-review-local-resume-v1",
        prompt_hash=canonical_sha256(
            {"prompt": "q5-exact-review-local-resume", "version": 1}
        ),
        tool_schema_version="author-exact-review-v1",
        tool_schema_hash=canonical_sha256((tool.spec,)),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="controlled-local-approval-resume-v1",
    )


async def execute_governed_review(
    approved: ApprovedReviewRequest,
    *,
    agent_data_root: Path,
    facade_factory: AgentAuthoringFacadeFactory,
    operator_id: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Persist, approve, revalidate, and execute one exact local-only review."""
    now = clock().astimezone(UTC)
    context = _temporal_context(approved, decision_time=now)
    authority_hash = canonical_sha256(
        {
            "kind": "q5-agent-author-exact-review",
            "request_hash": approved.request_hash,
            "experiment_id": approved.experiment_id,
            "bundle_hash": approved.bundle_hash,
            "spec_hash": approved.spec_hash,
            "planning_document_hash": approved.planning_document_hash,
            "snapshot_manifest_hash": approved.snapshot_manifest_hash,
            "selection_run_id": approved.selection_run_id,
            "research_case_id": approved.research_case_id,
            "market_context_feature_set_id": approved.market_context_feature_set_id,
            "technical_snapshot_id": approved.technical_snapshot_id,
            "temporal_context": context.canonical_payload(),
        }
    )
    invocation_hash = canonical_sha256(
        {
            "request_hash": approved.request_hash,
            "operator_id": operator_id,
            "approved_at": now,
        }
    )
    session_id = f"session-q5-review-{invocation_hash[:32]}"
    run_id = f"run-q5-review-{invocation_hash[:32]}"
    call_id = f"call-q5-review-{approved.request_hash[:32]}"
    arguments = dict(approved.arguments)
    database = build_agent_database(agent_data_root)
    try:
        model = _ExactReviewResumeModel(arguments=arguments, call_id=call_id)
        request_holder: dict[str, ModelRequest] = {}
        runtime = AgentApprovalRuntime(
            reader=database.reader,
            writer=database.writer,
            model=model,
            request_resolver=request_holder.get,
            action_resolver=_ExactReviewActionResolver(
                authority_hash=authority_hash,
                temporal_context=context,
            ),
            clock=clock,
            settings=ApprovalRuntimeSettings(
                approval_ttl=timedelta(minutes=15),
                resume_lease_ttl=timedelta(minutes=2),
                provider_timeout=timedelta(seconds=30),
            ),
        )
        facade = facade_factory(ApprovalRuntimeAuthoringVerifier(runtime=runtime))
        tool = AuthorSubmitStrategyReviewTool(commands=facade)
        invoker = AuthorWriteToolInvoker(
            registry=AuthorWriteToolRegistry(tools=(tool,)),
            context=context,
            run_id=run_id,
        )
        model.invoker = invoker
        manifest = _manifest(tool)
        request = ModelRequest(
            run_id=run_id,
            agent_name="q5-author-exact-review",
            instructions=(
                "Resume only the exact host-frozen author_submit_strategy_review call."
            ),
            input_text=(
                "Submit the operator-approved draft and immutable bundle for review "
                "without publishing or trading."
            ),
            max_turns=1,
            max_output_tokens=256,
            tools=(tool.spec,),
            required_tool_name=tool.spec.name,
        )
        request_holder[run_id] = request
        database.writer.put_manifest(manifest)
        database.writer.create_session(
            AgentSession(
                session_id=session_id,
                created_at=now,
                retention_class=RetentionClass.AUDIT,
            )
        )
        database.writer.create_run(
            AgentRun(
                run_id=run_id,
                session_id=session_id,
                status=RunStatus.QUEUED,
                objective="Submit one exact operator-approved Q5 draft for review.",
                authority_hash=authority_hash,
                max_model_tokens=1,
                max_model_spend_usd=Decimal(0),
                model_profile=ModelProfile.BALANCED,
                manifest_hash=manifest.manifest_hash,
                created_at=now,
            )
        )
        database.writer.transition_run(
            run_id=run_id,
            expected_revision=0,
            target=RunStatus.RUNNING,
            occurred_at=now,
            event_type="run_started",
            event_payload_hash=canonical_sha256(
                {"run_id": run_id, "request_hash": approved.request_hash}
            ),
        )
        batch = runtime.suspend(
            request=request,
            result=ModelResult(
                final_output=None,
                tool_calls=(),
                usage=ModelUsage(requests=0, input_tokens=0, output_tokens=0),
                interruptions=(
                    ModelInterruption(
                        call_id=call_id,
                        tool_name=tool.spec.name,
                        arguments=arguments,
                    ),
                ),
                continuation=ModelContinuation(
                    provider="controlled-local-approval-resume-v1",
                    payload={
                        "request_hash": approved.request_hash,
                        "experiment_id": approved.experiment_id,
                        "bundle_hash": approved.bundle_hash,
                        "call_id": call_id,
                    },
                ),
            ),
        )
        if len(batch.approvals) != 1:
            raise RuntimeError("Q5 exact-review did not create one approval")
        pending = batch.approvals[0]
        outcome = await runtime.decide_and_resume(
            request_id=pending.request_id,
            expected_action_hash=pending.action_hash,
            approved=True,
            operator_id=operator_id,
            reason=(
                "Workspace user approved exact Q5 review request sha256:"
                + approved.request_hash
            ),
        )
        run = database.reader.get_run(run_id)
        if (
            outcome.resumed is not True
            or outcome.result is None
            or len(outcome.result.tool_calls) != 1
            or run is None
            or run.status is not RunStatus.COMPLETED
            or len(invoker.executions) != 1
        ):
            raise RuntimeError("Q5 exact-review approval did not complete exactly once")
        model_tool_call = outcome.result.tool_calls[0]
        execution = invoker.executions[0]
        if (
            model_tool_call.call_id != execution.call_id
            or model_tool_call.tool_name != execution.tool_name
            or model_tool_call.arguments != approved.arguments
            or execution.arguments_hash != approved.arguments_hash
        ):
            raise RuntimeError(
                "Q5 exact-review model and tool audit identities drifted"
            )
        receipt = _mapping(
            execution.evidence.result.get("receipt"), field="command receipt"
        )
        strategy = _mapping(receipt.get("result"), field="strategy result")
        if strategy != {
            "strategy_id": _EXPECTED_STRATEGY_ID,
            "version": _EXPECTED_STRATEGY_VERSION,
            "state": "review",
            "review_outcome": "pending",
        }:
            raise RuntimeError("Q5 exact-review returned an unexpected strategy state")
        audit_event_count, audit_head_hash = database.verify_audit()
        return {
            "schema": "ditto.q5-live-agent-author-submit-review.v1",
            "generated_at": now.isoformat(),
            "status": "passed",
            "passed": True,
            "provider_calls": 0,
            "agent_tool_call_count": len(outcome.result.tool_calls),
            "operator_id": operator_id,
            "request_hash": approved.request_hash,
            "approval_id": outcome.approval.request_id,
            "approval_action_hash": outcome.approval.action_hash,
            "approval_status": outcome.approval.status,
            "authority_hash": authority_hash,
            "run_id": run_id,
            "run_status": run.status,
            "tool_name": execution.tool_name,
            "call_id": execution.call_id,
            "arguments_hash": execution.arguments_hash,
            "evidence_id": execution.evidence.evidence_id,
            "receipt_hash": _hash(
                execution.evidence.result.get("receipt_hash"), field="receipt_hash"
            ),
            "strategy": dict(strategy),
            "publishable": False,
            "experiment_id": approved.experiment_id,
            "review_bundle_hash": approved.bundle_hash,
            "planning_document_hash": approved.planning_document_hash,
            "snapshot_manifest_hash": approved.snapshot_manifest_hash,
            "agent_audit": {
                "event_count": audit_event_count,
                "head_hash": audit_head_hash,
            },
        }
    finally:
        database.close()
