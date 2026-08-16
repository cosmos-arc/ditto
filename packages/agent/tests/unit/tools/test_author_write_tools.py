"""Formal Author writes require HITL and only call application commands."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import cast

import ditto_agent.tools.author_write as author_write_module
import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.author_write import (
    AUTHOR_WRITE_TOOL_NAMES,
    AuthorSaveStrategyDraftTool,
    AuthorSubmitStrategyReviewTool,
    AuthorWriteExecutionContext,
    AuthorWriteToolInvoker,
    AuthorWriteToolRegistry,
)
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalCheck,
    AgentAuthoringCommandPort,
    AgentAuthoringCommandReceipt,
    AgentSaveStrategyDraftCommand,
    AgentSubmitStrategyReviewCommand,
    VerifiedAgentAuthoringApproval,
)
from ditto_application.mutation_idempotency import build_mutation_idempotency

HASH_A = "a" * 64
HASH_B = "b" * 64


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-20260812",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _execution(call_id: str) -> AuthorWriteExecutionContext:
    return AuthorWriteExecutionContext(
        run_id="run-001",
        episode_id="episode-run-001",
        call_id=call_id,
    )


def _receipt(operation_id: str, call_id: str) -> AgentAuthoringCommandReceipt:
    tool_name = (
        "author_save_strategy_draft"
        if operation_id == "strategies_create_strategy"
        else "author_submit_strategy_review"
    )
    check = AgentAuthoringApprovalCheck(
        run_id="run-001",
        episode_id="episode-run-001",
        call_id=call_id,
        tool_name=tool_name,
        arguments={},
    )
    approval = VerifiedAgentAuthoringApproval.issue(
        check=check,
        approval_id="approval-001",
        action_hash=HASH_A,
        operator_id="operator-001",
        approved_at=datetime(2026, 8, 12, 7, 5, tzinfo=UTC),
        approved=True,
    )
    identity = build_mutation_idempotency(
        operation_id=operation_id,
        resource_id="strategy:v1:" + HASH_B,
        raw_key=HASH_A,
        request_payload={"call_id": call_id},
    )
    return AgentAuthoringCommandReceipt.issue(
        identity=identity,
        approval=approval,
        result_identity="strategy-001@1",
        result={"strategy_id": "strategy-001", "version": 1, "state": "draft"},
    )


class _Commands:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def save_strategy_draft(
        self,
        command: AgentSaveStrategyDraftCommand,
    ) -> AgentAuthoringCommandReceipt:
        self.calls.append(command)
        return _receipt("strategies_create_strategy", command.call_id)

    def submit_strategy_review(
        self,
        command: AgentSubmitStrategyReviewCommand,
    ) -> AgentAuthoringCommandReceipt:
        self.calls.append(command)
        return _receipt("strategies_submit_strategy_review", command.call_id)


def _tools(commands: _Commands) -> tuple[object, object]:
    port = cast(AgentAuthoringCommandPort, commands)
    return (
        AuthorSaveStrategyDraftTool(commands=port),
        AuthorSubmitStrategyReviewTool(commands=port),
    )


def test_only_save_and_submit_are_registered_and_both_require_approval() -> None:
    tools = _tools(_Commands())
    registry = AuthorWriteToolRegistry(tools=cast(tuple, tools))

    assert (
        frozenset({"author_save_strategy_draft", "author_submit_strategy_review"})
        == AUTHOR_WRITE_TOOL_NAMES
    )
    assert tuple(registry.tools) == (
        "author_save_strategy_draft",
        "author_submit_strategy_review",
    )
    assert all(tool.spec.requires_approval for tool in tools)
    forbidden = {"publish", "deprecate", "reactivate", "order", "broker"}
    assert all(forbidden.isdisjoint(tool.spec.name.split("_")) for tool in tools)


def test_save_tool_injects_run_episode_and_call_identity_and_seals_receipt() -> None:
    commands = _Commands()
    tool = AuthorSaveStrategyDraftTool(
        commands=cast(AgentAuthoringCommandPort, commands)
    )
    context = _context()

    envelope = tool.invoke(
        arguments={
            "strategy_id": "strategy-001",
            "name": "Momentum",
            "spec_json": {"strategy_family_id": "strategy-001"},
            "base_version": None,
            "tags": ["agent"],
        },
        context=context,
        execution=_execution("call-save-001"),
    )

    command = commands.calls[0]
    assert isinstance(command, AgentSaveStrategyDraftCommand)
    assert command.run_id == "run-001"
    assert command.episode_id == "episode-run-001"
    assert command.call_id == "call-save-001"
    assert command.tags == ("agent",)
    assert envelope.tool_name == "author_save_strategy_draft"
    assert envelope.temporal_context == context
    assert envelope.result["kind"] == "agent_authoring_command_receipt"
    assert envelope.result["receipt"]["approval_id"] == "approval-001"
    assert envelope.result["receipt"]["run_id"] == "run-001"
    artifact_ref = f"command-receipt:sha256:{envelope.result['receipt_hash']}"
    assert envelope.artifact_refs == (artifact_ref,)
    assert envelope.verify_integrity()


def test_submit_tool_is_thin_application_adapter_and_never_publishes() -> None:
    commands = _Commands()
    tool = AuthorSubmitStrategyReviewTool(
        commands=cast(AgentAuthoringCommandPort, commands)
    )

    envelope = tool.invoke(
        arguments={
            "strategy_id": "strategy-001",
            "version": 1,
            "bundle_hash": HASH_B,
            "reason": "Submit the validated draft for review.",
        },
        context=_context(),
        execution=_execution("call-submit-001"),
    )

    command = commands.calls[0]
    assert isinstance(command, AgentSubmitStrategyReviewCommand)
    assert envelope.result["receipt"]["operation_id"] == (
        "strategies_submit_strategy_review"
    )
    assert "publish" not in repr(commands.calls).lower()


@pytest.mark.parametrize(
    "field",
    ["run_id", "episode_id", "call_id", "action_hash", "operator_id"],
)
def test_model_cannot_override_trusted_write_identity(field: str) -> None:
    commands = _Commands()
    tool = AuthorSaveStrategyDraftTool(
        commands=cast(AgentAuthoringCommandPort, commands)
    )
    arguments: dict[str, object] = {
        "strategy_id": "strategy-001",
        "name": "Momentum",
        "spec_json": {"strategy_family_id": "strategy-001"},
        "base_version": None,
        "tags": [],
        field: "model-controlled",
    }

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments=arguments,
            context=_context(),
            execution=_execution("call-save-001"),
        )

    assert commands.calls == []


def test_agent_author_write_module_has_no_capability_or_store_dependency() -> None:
    source = inspect.getsource(author_write_module)

    assert "ditto_application.agent_authoring_contracts" in source
    assert "ditto_strategy" not in source
    assert "strategy_governance_store" not in source
    assert "storage.sqlite" not in source


@pytest.mark.asyncio
async def test_provider_invoker_binds_call_to_run_and_records_receipt_evidence() -> (
    None
):
    commands = _Commands()
    registry = AuthorWriteToolRegistry(tools=cast(tuple, _tools(commands)))
    invoker = AuthorWriteToolInvoker(
        registry=registry,
        context=_context(),
        run_id="run-001",
    )

    payload = await invoker.invoke(
        "author_save_strategy_draft",
        (
            '{"base_version":null,"name":"Momentum",'
            '"spec_json":{"strategy_family_id":"strategy-001"},'
            '"strategy_id":"strategy-001","tags":["agent"]}'
        ),
        call_id="call-save-001",
    )

    assert payload["tool_name"] == "author_save_strategy_draft"
    assert payload["result"]["receipt"]["run_id"] == "run-001"
    assert len(invoker.executions) == 1
    assert invoker.executions[0].call_id == "call-save-001"
    with pytest.raises(ValueError, match="duplicate"):
        await invoker.invoke(
            "author_save_strategy_draft",
            (
                '{"base_version":null,"name":"Momentum",'
                '"spec_json":{"strategy_family_id":"strategy-001"},'
                '"strategy_id":"strategy-001","tags":["agent"]}'
            ),
            call_id="call-save-001",
        )
