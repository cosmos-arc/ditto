"""Execute one Q5 Agent Author save only after exact operator approval."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
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
    AuthorSaveStrategyDraftTool,
    AuthorWriteToolInvoker,
    AuthorWriteToolRegistry,
)
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalVerifier,
    AgentAuthoringCommandPort,
)
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import SubmitReviewHandler
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.container import make_app_container
from ditto_apps.scripts.q5_live_agent_author_support import (
    _AUTHOR_SPEC_TEMPLATE,
    _NoBaseCatalog,
    _parse_datetime,
    _plain_mapping,
    _validate_author_spec,
)

_HASH = re.compile(r"[0-9a-f]{64}")
_EXPECTED_SCHEMA = "ditto.q5-live-agent-author-proposal.v1"
_EXPECTED_TOOL = "author_save_strategy_draft"
_EXPECTED_STRATEGY_ID = "agent_etf_518880_rotation"
_EXPECTED_INSTRUMENT_ID = 2_001_724
_EXPECTED_INSTRUMENT_CODE = "518880.SH"
_EXPECTED_INSTRUMENT_NAME = "华安易富黄金ETF"
_EXPECTED_ARGUMENT_KEYS = frozenset(
    {"strategy_id", "name", "spec_json", "base_version", "tags"}
)


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{field} must be an object")
    return cast("Mapping[str, object]", raw)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _text_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a sequence")
    items = cast("Sequence[object]", value)
    result = tuple(_text(item, field=field) for item in items)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{field} must be non-empty and unique")
    return result


def _strict_json_value(value: object) -> object:
    """Detach immutable views without changing JSON number types."""
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        if not all(type(key) is str for key in mapping):
            raise ValueError("exact save arguments contain a non-string key")
        return {
            cast("str", key): _strict_json_value(item) for key, item in mapping.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_strict_json_value(item) for item in sequence]
    raise ValueError("exact save arguments contain a non-JSON value")


def _strict_json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    copied = _strict_json_value(value)
    if type(copied) is not dict:
        raise ValueError("exact save arguments must be an object")
    return cast("dict[str, object]", copied)


@dataclass(frozen=True, slots=True)
class ApprovedSaveRequest:
    """Host-revalidated exact draft request authorized by the operator."""

    arguments: Mapping[str, object]
    request_hash: str
    proposal_run_id: str
    episode_manifest_hash: str
    episode_replay_identity: str
    selection_run_id: str
    research_case_id: str
    market_context_feature_set_id: str
    technical_snapshot_id: str
    instrument_id: int
    instrument_code: str
    instrument_name: str
    last_visible_bar_at: str
    source_snapshot_ids: tuple[str, ...]


AgentAuthoringFacadeFactory = Callable[
    [AgentAuthoringApprovalVerifier], AgentAuthoringCommandPort
]


@dataclass(frozen=True, slots=True)
class _ExactSaveActionResolver(ApprovalActionResolver):
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


class _ExactSaveResumeModel(AgentModelPort):
    """Local continuation executor; it never calls an external model provider."""

    def __init__(self, *, arguments: Mapping[str, object], call_id: str) -> None:
        self._arguments = arguments
        self._call_id = call_id
        self.invoker: AuthorWriteToolInvoker | None = None

    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        raise RuntimeError("Q5 exact-save model supports resume only")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        if False:  # pragma: no cover - structural async-generator marker
            yield cast("ModelStreamEvent", None)
        raise RuntimeError("Q5 exact-save model does not stream")

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        if (
            len(request.decisions) != 1
            or request.decisions[0].call_id != self._call_id
            or request.decisions[0].approved is not True
            or self.invoker is None
        ):
            raise RuntimeError("Q5 exact-save continuation lacks exact approval")
        result = await self.invoker.invoke(
            _EXPECTED_TOOL,
            orjson.dumps(self._arguments, option=orjson.OPT_SORT_KEYS).decode(),
            call_id=self._call_id,
        )
        result_mapping = _mapping(result, field="author save tool result")
        return ModelResult(
            final_output={
                "saved": True,
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


def _proposal_boundary(
    payload: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    if (
        payload.get("schema") != _EXPECTED_SCHEMA
        or payload.get("status") != "passed"
        or payload.get("passed") is not True
        or payload.get("holdout_excluded") is not True
        or payload.get("episode_verified") is not True
    ):
        raise ValueError("Q5 Author proposal is not a verified passing proposal")
    proposal = _mapping(payload.get("proposal"), field="proposal")
    request = _mapping(payload.get("exact_save_request"), field="exact_save_request")
    if (
        request.get("tool_name") != _EXPECTED_TOOL
        or request.get("requires_exact_approval") is not True
        or request.get("status") != "pending_operator_approval"
        or proposal.get("publishable") is not False
    ):
        raise ValueError("Q5 Author exact-save boundary is invalid")
    return proposal, request


def _approved_arguments(
    request: Mapping[str, object],
    *,
    approved_hash: str,
) -> tuple[Mapping[str, object], str]:
    raw_arguments = _mapping(request.get("arguments"), field="save arguments")
    if frozenset(raw_arguments) != _EXPECTED_ARGUMENT_KEYS:
        raise ValueError("Q5 Author save arguments have an invalid surface")
    stored_hash = _hash(request.get("arguments_hash"), field="arguments_hash")
    if approved_hash != stored_hash:
        raise ValueError("operator approval hash does not match the exact save request")
    return raw_arguments, stored_hash


def _host_frozen_spec(spec: Mapping[str, object]) -> dict[str, object]:
    producer_spec = _plain_mapping(_AUTHOR_SPEC_TEMPLATE)
    producer_spec["signal_weights"] = spec["signal_weights"]
    producer_spec["params"] = spec["params"]
    return _validate_author_spec(producer_spec)


def _host_frozen_arguments(
    *,
    strategy_id: str,
    name: str,
    tags: tuple[str, ...],
    spec: Mapping[str, object],
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "name": name,
        "spec_json": _host_frozen_spec(spec),
        "base_version": None,
        "tags": tags,
    }


def _arguments_bound_to_hash(
    *,
    raw_arguments: Mapping[str, object],
    stored_hash: str,
    strategy_id: str,
    name: str,
    tags: tuple[str, ...],
    spec: Mapping[str, object],
) -> Mapping[str, object]:
    arguments: dict[str, object] = {
        "strategy_id": strategy_id,
        "name": name,
        "spec_json": MappingProxyType(dict(spec)),
        "base_version": None,
        "tags": tags,
    }
    if canonical_request_hash(arguments) == stored_hash:
        return MappingProxyType(arguments)

    producer_arguments = _host_frozen_arguments(
        strategy_id=strategy_id,
        name=name,
        tags=tags,
        spec=spec,
    )
    if (
        canonical_bytes(producer_arguments) != canonical_bytes(raw_arguments)
        or canonical_request_hash(producer_arguments) != stored_hash
    ):
        raise ValueError("Q5 Author save arguments hash is invalid")
    return MappingProxyType(producer_arguments)


def _validated_strategy(
    proposal: Mapping[str, object],
    raw_arguments: Mapping[str, object],
) -> tuple[str, str, tuple[str, ...], Mapping[str, object]]:
    strategy_id = _text(raw_arguments.get("strategy_id"), field="strategy_id")
    name = _text(raw_arguments.get("name"), field="name")
    if (
        strategy_id != _EXPECTED_STRATEGY_ID
        or raw_arguments.get("base_version") is not None
    ):
        raise ValueError("Q5 acceptance permits only the frozen new draft")
    tags = _text_tuple(raw_arguments.get("tags"), field="tags")
    spec = _mapping(raw_arguments.get("spec_json"), field="spec_json")
    validated_spec = _plain_mapping(_validate_author_spec(spec))
    if canonical_request_hash(validated_spec) != canonical_request_hash(spec):
        raise ValueError("Q5 Author spec normalization changed the approved payload")
    proposal_spec = _mapping(proposal.get("spec_json"), field="proposal spec_json")
    identities_match = (
        spec.get("strategy_id") == strategy_id
        and spec.get("name") == name
        and _text_tuple(spec.get("tags"), field="spec tags") == tags
        and proposal.get("strategy_id") == strategy_id
        and canonical_request_hash(proposal_spec) == canonical_request_hash(spec)
    )
    if not identities_match:
        raise ValueError("Q5 Author proposal and save request identity differ")
    preview_facade = AuthoringPreviewFacade(catalog=_NoBaseCatalog())
    preview = preview_facade.create_draft(spec_json=spec)
    if preview.payload.value.get("canonical_hash") != proposal.get("canonical_hash"):
        producer_spec = _host_frozen_spec(spec)
        if canonical_bytes(producer_spec) != canonical_bytes(spec):
            raise ValueError("Q5 Author proposal no longer validates canonically")
        preview = preview_facade.create_draft(spec_json=producer_spec)
    if (
        preview.valid is not True
        or preview.subject_id != strategy_id
        or preview.payload.value.get("canonical_hash") != proposal.get("canonical_hash")
    ):
        raise ValueError("Q5 Author proposal no longer validates canonically")
    return strategy_id, name, tags, spec


def _lineage_and_technical(
    proposal_payload: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object], int, str]:
    egress = _mapping(proposal_payload.get("egress"), field="egress")
    payload = _mapping(egress.get("payload"), field="egress.payload")
    lineage = _mapping(payload.get("lineage"), field="egress.payload.lineage")
    technical = _mapping(payload.get("technical"), field="egress.payload.technical")
    instrument_id = technical.get("instrument_id")
    if type(instrument_id) is not int or instrument_id != _EXPECTED_INSTRUMENT_ID:
        raise ValueError("Q5 Author technical instrument identity is invalid")
    instrument_name = _text(
        technical.get("instrument_name"), field="technical.instrument_name"
    )
    if instrument_name != _EXPECTED_INSTRUMENT_NAME:
        raise ValueError("Q5 Author technical instrument name is invalid")
    return lineage, technical, cast("int", instrument_id), instrument_name


def approved_save_request(
    proposal_payload: Mapping[str, object],
    *,
    approved_request_hash: str,
) -> ApprovedSaveRequest:
    """Fail closed unless approval and proposal identify one frozen safe save."""
    approved_hash = _hash(approved_request_hash, field="approval hash")
    proposal, request = _proposal_boundary(proposal_payload)
    raw_arguments, stored_hash = _approved_arguments(
        request, approved_hash=approved_hash
    )
    strategy_id, name, tags, spec = _validated_strategy(proposal, raw_arguments)
    lineage, technical, instrument_id, instrument_name = _lineage_and_technical(
        proposal_payload
    )

    arguments = _arguments_bound_to_hash(
        raw_arguments=raw_arguments,
        stored_hash=stored_hash,
        strategy_id=strategy_id,
        name=name,
        tags=tags,
        spec=spec,
    )
    return ApprovedSaveRequest(
        arguments=MappingProxyType(arguments),
        request_hash=stored_hash,
        proposal_run_id=_text(proposal_payload.get("run_id"), field="run_id"),
        episode_manifest_hash=_hash(
            proposal_payload.get("episode_manifest_hash"),
            field="episode_manifest_hash",
        ),
        episode_replay_identity=_hash(
            proposal_payload.get("episode_replay_identity"),
            field="episode_replay_identity",
        ),
        selection_run_id=_text(
            lineage.get("selection_run_id"), field="selection_run_id"
        ),
        research_case_id=_text(
            lineage.get("research_case_id"), field="research_case_id"
        ),
        market_context_feature_set_id=_text(
            lineage.get("market_context_feature_set_id"),
            field="market_context_feature_set_id",
        ),
        technical_snapshot_id=_text(
            lineage.get("technical_snapshot_id"), field="technical_snapshot_id"
        ),
        instrument_id=instrument_id,
        instrument_code=_EXPECTED_INSTRUMENT_CODE,
        instrument_name=instrument_name,
        last_visible_bar_at=_text(
            technical.get("last_visible_bar_at"), field="last_visible_bar_at"
        ),
        source_snapshot_ids=_text_tuple(
            technical.get("source_snapshot_ids"), field="source_snapshot_ids"
        ),
    )


def _temporal_context(
    approved: ApprovedSaveRequest,
    *,
    decision_time: datetime,
) -> TemporalToolContext:
    visible_at = _parse_datetime(
        approved.last_visible_bar_at, field="last_visible_bar_at"
    )
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=visible_at,
            publication_cutoff=visible_at,
            source_snapshot_id=approved.source_snapshot_ids[0],
            execution_eligible_at="not_applicable",
            allowed_universe=(approved.instrument_code,),
            license_class="approved-research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _manifest(tool: AuthorSaveStrategyDraftTool) -> AgentManifest:
    return AgentManifest(
        manifest_id="personal-workstation-q5-exact-save",
        agent_version="r5.2",
        prompt_version="q5-exact-save-local-resume-v1",
        prompt_hash=canonical_sha256(
            {"prompt": "q5-exact-save-local-resume", "version": 1}
        ),
        tool_schema_version="author-exact-save-v1",
        tool_schema_hash=canonical_sha256((tool.spec,)),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="controlled-local-approval-resume-v1",
    )


async def execute_governed_save(
    approved: ApprovedSaveRequest,
    *,
    agent_data_root: Path,
    facade_factory: AgentAuthoringFacadeFactory,
    operator_id: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Persist, approve, revalidate, and execute one exact local-only save."""
    now = clock().astimezone(UTC)
    context = _temporal_context(approved, decision_time=now)
    authority_hash = canonical_sha256(
        {
            "kind": "q5-agent-author-exact-save",
            "request_hash": approved.request_hash,
            "proposal_run_id": approved.proposal_run_id,
            "episode_manifest_hash": approved.episode_manifest_hash,
            "episode_replay_identity": approved.episode_replay_identity,
            "selection_run_id": approved.selection_run_id,
            "research_case_id": approved.research_case_id,
            "market_context_feature_set_id": (approved.market_context_feature_set_id),
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
    session_id = f"session-q5-save-{invocation_hash[:32]}"
    run_id = f"run-q5-save-{invocation_hash[:32]}"
    call_id = f"call-q5-save-{approved.request_hash[:32]}"
    arguments = _strict_json_mapping(approved.arguments)
    database = build_agent_database(agent_data_root)
    try:
        model = _ExactSaveResumeModel(arguments=arguments, call_id=call_id)
        request_holder: dict[str, ModelRequest] = {}
        resolver = _ExactSaveActionResolver(
            authority_hash=authority_hash,
            temporal_context=context,
        )
        runtime = AgentApprovalRuntime(
            reader=database.reader,
            writer=database.writer,
            model=model,
            request_resolver=request_holder.get,
            action_resolver=resolver,
            clock=clock,
            settings=ApprovalRuntimeSettings(
                approval_ttl=timedelta(minutes=15),
                resume_lease_ttl=timedelta(minutes=2),
                provider_timeout=timedelta(seconds=30),
            ),
        )
        facade = facade_factory(ApprovalRuntimeAuthoringVerifier(runtime=runtime))
        tool = AuthorSaveStrategyDraftTool(commands=facade)
        invoker = AuthorWriteToolInvoker(
            registry=AuthorWriteToolRegistry(tools=(tool,)),
            context=context,
            run_id=run_id,
        )
        model.invoker = invoker
        manifest = _manifest(tool)
        request = ModelRequest(
            run_id=run_id,
            agent_name="q5-author-exact-save",
            instructions=(
                "Resume only the exact host-frozen author_save_strategy_draft call."
            ),
            input_text=(
                "Save the operator-approved immutable draft without publishing it."
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
                objective="Save one exact operator-approved Q5 Agent Author draft.",
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
        interruption = ModelInterruption(
            call_id=call_id,
            tool_name=tool.spec.name,
            arguments=arguments,
        )
        batch = runtime.suspend(
            request=request,
            result=ModelResult(
                final_output=None,
                tool_calls=(),
                usage=ModelUsage(requests=0, input_tokens=0, output_tokens=0),
                interruptions=(interruption,),
                continuation=ModelContinuation(
                    provider="controlled-local-approval-resume-v1",
                    payload={
                        "request_hash": approved.request_hash,
                        "proposal_run_id": approved.proposal_run_id,
                        "call_id": call_id,
                    },
                ),
            ),
        )
        if len(batch.approvals) != 1:
            raise RuntimeError("Q5 exact-save did not create one approval")
        pending = batch.approvals[0]
        outcome = await runtime.decide_and_resume(
            request_id=pending.request_id,
            expected_action_hash=pending.action_hash,
            approved=True,
            operator_id=operator_id,
            reason=(
                "Workspace user approved exact Q5 save request sha256:"
                + approved.request_hash
            ),
        )
        run = database.reader.get_run(run_id)
        if (
            outcome.resumed is not True
            or run is None
            or run.status is not RunStatus.COMPLETED
            or len(invoker.executions) != 1
        ):
            raise RuntimeError("Q5 exact-save approval did not complete exactly once")
        execution = invoker.executions[0]
        receipt_hash = _hash(
            execution.evidence.result.get("receipt_hash"), field="receipt_hash"
        )
        receipt = _mapping(
            execution.evidence.result.get("receipt"), field="command receipt"
        )
        strategy = _mapping(receipt.get("result"), field="strategy result")
        if strategy != {
            "strategy_id": _EXPECTED_STRATEGY_ID,
            "version": 1,
            "state": "draft",
        }:
            raise RuntimeError("Q5 exact-save returned an unexpected strategy state")
        audit_event_count, audit_head_hash = database.verify_audit()
        return {
            "schema": "ditto.q5-live-agent-author-save.v1",
            "generated_at": now.isoformat(),
            "status": "passed",
            "passed": True,
            "provider_calls": 0,
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
            "receipt_hash": receipt_hash,
            "strategy": dict(strategy),
            "publishable": False,
            "lineage": {
                "proposal_run_id": approved.proposal_run_id,
                "selection_run_id": approved.selection_run_id,
                "research_case_id": approved.research_case_id,
                "market_context_feature_set_id": (
                    approved.market_context_feature_set_id
                ),
                "technical_snapshot_id": approved.technical_snapshot_id,
            },
            "agent_audit": {
                "event_count": audit_event_count,
                "head_hash": audit_head_hash,
            },
        }
    finally:
        database.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--approved-request-hash", required=True)
    parser.add_argument("--operator-id", default="workspace-user")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local-only governed save after an exact CLI approval binding."""
    arguments = _parser().parse_args(argv)
    proposal_path = Path(arguments.proposal).resolve(strict=True)
    data_root = Path(arguments.data_root).resolve(strict=True)
    output_path = Path(arguments.output)
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_proposal: object = orjson.loads(proposal_path.read_bytes())
    proposal = _mapping(raw_proposal, field="proposal artifact")
    approved = approved_save_request(
        proposal,
        approved_request_hash=str(arguments.approved_request_hash),
    )

    previous_state_root = os.environ.get("DITTO_STATE_ROOT")
    os.environ["DITTO_STATE_ROOT"] = str(data_root)
    container = make_app_container()
    try:

        def facade_factory(
            verifier: AgentAuthoringApprovalVerifier,
        ) -> AgentAuthoringCommandPort:
            return AgentAuthoringCommandFacade(
                approval_verifier=verifier,
                create_handler=container.get(CreateStrategyHandler),
                update_handler=container.get(UpdateStrategyHandler),
                submit_review_handler=container.get(SubmitReviewHandler),
            )

        result = asyncio.run(
            execute_governed_save(
                approved,
                agent_data_root=data_root,
                facade_factory=facade_factory,
                operator_id=str(arguments.operator_id),
            )
        )
    finally:
        container.close()
        if previous_state_root is None:
            del os.environ["DITTO_STATE_ROOT"]
        else:
            os.environ["DITTO_STATE_ROOT"] = previous_state_root
    output_path.write_bytes(canonical_bytes(result))
    return 0


__all__ = [
    "AgentAuthoringFacadeFactory",
    "ApprovedSaveRequest",
    "approved_save_request",
    "execute_governed_save",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
