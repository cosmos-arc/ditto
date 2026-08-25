from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.approval_runtime import (
    AgentApprovalRuntime,
    ApprovalRuntimeSettings,
)
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
from ditto_agent.models.fake import ScriptedAgentModel, ScriptedOutcome
from ditto_agent.models.port import (
    ModelContinuation,
    ModelInterruption,
    ModelRequest,
    ModelResult,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
)
from ditto_agent.runtime.service import (
    AgentApprovalDecisionCommand,
    AgentRuntimeUnavailable,
    ApprovalDecisionKind,
)
from ditto_agent.storage.sqlite.audit import verify_audit_chain
from ditto_agent.storage.sqlite.records import ApprovalStatus
from ditto_apps.api.routes.agent_routes import decide_agent_approval
from ditto_apps.models.agent import AgentApprovalDecisionRequest
from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)

NOW = datetime(2026, 8, 16, 8, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
_decide_agent_approval = getattr(
    decide_agent_approval, "__dishka_orig_func__", decide_agent_approval
)


class _Clock:
    def __call__(self) -> datetime:
        return NOW


class _Resolver:
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
            subject_identity=str(interruption.arguments["strategy_id"]),
            required_authority="strategy.author",
            authority_hash=HASH_A,
            temporal_context=_context(),
            budget=ActionBudget(
                max_tool_calls=1,
                max_output_bytes=16_384,
                max_model_tokens=512,
                max_model_spend_usd=Decimal("0.20"),
            ),
            expires_at=expires_at,
        )


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=NOW - timedelta(minutes=5),
            publication_cutoff=NOW - timedelta(minutes=10),
            source_snapshot_id="snapshot-r52-api",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _tool() -> ModelToolSpec:
    return ModelToolSpec(
        kind=ModelToolKind.FUNCTION,
        name="author_save_strategy_draft",
        description="Save one already validated strategy draft.",
        input_schema={
            "type": "object",
            "properties": {"strategy_id": {"type": "string"}},
            "required": ["strategy_id"],
            "additionalProperties": False,
        },
        requires_approval=True,
    )


def _request() -> ModelRequest:
    return ModelRequest(
        run_id="run-r52-api",
        agent_name="author-copilot",
        instructions="Use only the registered authoring tools.",
        input_text="Save the draft.",
        max_turns=4,
        max_output_tokens=256,
        tools=(_tool(),),
    )


def _interrupted() -> ModelResult:
    return ModelResult(
        final_output=None,
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=20, output_tokens=5),
        interruptions=(
            ModelInterruption(
                call_id="call-api-write",
                tool_name="author_save_strategy_draft",
                arguments={"strategy_id": "strategy-api"},
            ),
        ),
        continuation=ModelContinuation(
            provider="scripted",
            payload={
                "run_id": "run-r52-api",
                "pending_call_ids": ["call-api-write"],
            },
        ),
    )


def _terminal() -> ModelResult:
    return ModelResult(
        final_output={"claims": [], "uncertainty": None},
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=10, output_tokens=5),
        interruptions=(),
        continuation=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_api_decision_resumes_persisted_interruption_after_restart(
    tmp_path: Path,
    decision: str,
) -> None:
    bundle = build_agent_database(tmp_path)
    manifest = AgentManifest(
        manifest_id="manifest-r52-api",
        agent_version="r5.2.0",
        prompt_version="author-v1",
        prompt_hash=HASH_B,
        tool_schema_version="author-tools-v1",
        tool_schema_hash=canonical_sha256((_tool(),)),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-v1",
    )
    bundle.writer.put_manifest(manifest)
    bundle.writer.create_session(
        AgentSession(
            session_id="session-r52-api",
            created_at=NOW,
            retention_class=RetentionClass.AUDIT,
        )
    )
    bundle.writer.create_run(
        AgentRun(
            run_id="run-r52-api",
            session_id="session-r52-api",
            status=RunStatus.QUEUED,
            objective="Save the draft.",
            authority_hash=HASH_A,
            max_model_tokens=512,
            max_model_spend_usd=Decimal("0.20"),
            model_profile=ModelProfile.BALANCED,
            manifest_hash=manifest.manifest_hash,
            created_at=NOW,
        )
    )
    bundle.writer.transition_run(
        run_id="run-r52-api",
        expected_revision=0,
        target=RunStatus.RUNNING,
        occurred_at=NOW,
        event_type="run_started",
        event_payload_hash=canonical_sha256({"run_id": "run-r52-api"}),
    )
    first_process = AgentApprovalRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        model=ScriptedAgentModel(),
        request_resolver=lambda _run_id: _request(),
        action_resolver=_Resolver(),
        clock=_Clock(),
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )
    batch = first_process.suspend(request=_request(), result=_interrupted())
    approval = batch.approvals[0]
    unconfigured_runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=_Clock(),
    )
    with pytest.raises(AgentRuntimeUnavailable) as unconfigured:
        unconfigured_runtime.decide_approval(
            AgentApprovalDecisionCommand(
                approval_id=approval.request_id,
                expected_action_hash=approval.action_hash,
                decision=ApprovalDecisionKind.APPROVE,
                operator_id="operator-unconfigured",
                reason=None,
            )
        )
    assert unconfigured.value.reason_code == "agent_approval_resume_unconfigured"
    still_pending = bundle.reader.get_approval(approval.request_id)
    assert still_pending is not None
    assert still_pending.status is ApprovalStatus.PENDING

    restarted_approval_runtime = AgentApprovalRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        model=ScriptedAgentModel(script=(ScriptedOutcome(result=_terminal()),)),
        request_resolver=lambda _run_id: _request(),
        action_resolver=_Resolver(),
        clock=_Clock(),
        settings=ApprovalRuntimeSettings(
            approval_ttl=timedelta(minutes=15),
            resume_lease_ttl=timedelta(minutes=2),
        ),
    )
    runtime = PersistedAgentRuntime(
        reader=bundle.reader,
        writer=bundle.writer,
        manifest=manifest,
        clock=_Clock(),
        options=PersistedAgentRuntimeOptions(
            approval_runtime=restarted_approval_runtime
        ),
    )

    response = await _decide_agent_approval(
        approval.request_id,
        AgentApprovalDecisionRequest(
            decision=decision,
            expected_action_hash=approval.action_hash,
            operator_id="operator-api",
            reason="Reviewed exact API action.",
        ),
        runtime,
    )

    expected_status = "approved" if decision == "approve" else "rejected"
    assert response.data.status == expected_status
    assert response.data.run_id == "run-r52-api"
    stored_run = bundle.reader.get_run("run-r52-api")
    assert stored_run is not None
    assert stored_run.status is RunStatus.COMPLETED
    assert bundle.reader.get_continuation("run-r52-api") is None
    actions = tuple(
        str(row[0])
        for row in bundle.database.get_connection().execute(
            """
            SELECT action FROM agent_audit_events
            WHERE category='approval' AND subject_id=?
            ORDER BY audit_id
            """,
            (approval.request_id,),
        )
    )
    assert actions == ("requested", expected_status)
    assert verify_audit_chain(bundle.database.get_connection()).event_count > 0
    bundle.close()
