from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from agents import Agent, Runner, RunResult, RunResultStreaming, RunState
from agents.exceptions import AgentsException
from agents.items import ToolApprovalItem, ToolCallItem
from agents.stream_events import RawResponsesStreamEvent
from ditto_agent.models import openai_adapter as adapter
from ditto_agent.models.port import (
    ApprovalDecision,
    ModelContinuation,
    ModelOutputContract,
    ModelProviderError,
    ModelRequest,
    ModelStreamEventKind,
    UnsupportedModelCapabilityError,
)


def _request() -> ModelRequest:
    return ModelRequest(
        run_id="run-sdk-engine",
        agent_name="governed-agent",
        instructions="Return only evidence-grounded results.",
        input_text="Summarize the approved evidence.",
        max_turns=4,
        max_output_tokens=512,
        tools=(),
        output_contract=ModelOutputContract.GROUNDED_ANSWER,
    )


def _invocation(
    *,
    continuation: ModelContinuation | None = None,
    decisions: tuple[ApprovalDecision, ...] = (),
) -> adapter.OpenAIInvocation:
    return adapter.OpenAIInvocation(
        request=_request(),
        model_id="test-model",
        api_key="test-key",
        project_id="test-project",
        provider_id="provider-test",
        continuation=continuation,
        decisions=decisions,
    )


def _sdk_agent() -> Agent[object]:
    return Agent[object](
        name="test-agent",
        instructions="Stay deterministic.",
        model="test-model",
    )


def _raw_call(
    call_id: str,
    *,
    name: str = "read_evidence",
    arguments: str = '{"evidence_id":"evidence-1"}',
    item_type: str = "function_call",
) -> Any:
    return SimpleNamespace(
        type=item_type,
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _tool_item(raw_item: object) -> ToolCallItem:
    return ToolCallItem(
        agent=_sdk_agent(),
        raw_item=cast(Any, raw_item),
    )


def _approval_item(raw_item: object) -> ToolApprovalItem:
    return ToolApprovalItem(
        agent=_sdk_agent(),
        raw_item=cast(Any, raw_item),
    )


class _SerializedState:
    def __init__(self) -> None:
        self.serialization_calls: list[dict[str, object]] = []

    def to_json(self, **kwargs: object) -> dict[str, object]:
        self.serialization_calls.append(dict(kwargs))
        return {"schemaVersion": 1, "cursor": "approval-1"}


class _FakeRunResult:
    def __init__(
        self,
        *,
        final_output: object = "grounded answer",
        new_items: list[object] | None = None,
        interruptions: list[ToolApprovalItem] | None = None,
        state: _SerializedState | None = None,
    ) -> None:
        self.final_output = final_output
        self.new_items = new_items or []
        self.interruptions = interruptions or []
        self.context_wrapper = SimpleNamespace(
            usage=SimpleNamespace(
                requests=1,
                input_tokens=21,
                output_tokens=8,
                total_tokens=29,
            )
        )
        self.state = state or _SerializedState()

    def to_state(self) -> _SerializedState:
        return self.state


class _FakeStreamedResult(_FakeRunResult):
    def __init__(
        self,
        events: tuple[object, ...],
        *,
        failure: AgentsException | None = None,
    ) -> None:
        super().__init__()
        self._events = events
        self._failure = failure

    async def stream_events(self) -> AsyncIterator[object]:
        for event in self._events:
            yield event
        if self._failure is not None:
            raise self._failure


class _DecisionState:
    def __init__(self, interruptions: list[ToolApprovalItem]) -> None:
        self._interruptions = interruptions
        self.approved: list[ToolApprovalItem] = []
        self.rejected: list[tuple[ToolApprovalItem, str | None]] = []

    def get_interruptions(self) -> list[ToolApprovalItem]:
        return list(self._interruptions)

    def approve(self, item: ToolApprovalItem) -> None:
        self.approved.append(item)

    def reject(
        self,
        item: ToolApprovalItem,
        *,
        rejection_message: str | None = None,
    ) -> None:
        self.rejected.append((item, rejection_message))


def _as_run_result(result: _FakeRunResult) -> RunResult:
    return cast(RunResult, result)


def _as_streamed_result(result: _FakeStreamedResult) -> RunResultStreaming:
    return cast(RunResultStreaming, result)


def _as_run_state(state: _DecisionState) -> RunState[object]:
    return cast(RunState[object], state)


def test_result_translates_sdk_items_interruptions_usage_and_structured_output() -> (
    None
):
    state = _SerializedState()
    tool_call = _tool_item(_raw_call("call-tool"))
    non_function_tool_call = _tool_item(_raw_call("call-message", item_type="message"))
    approval = _approval_item(_raw_call("call-approval"))
    grounded = adapter._GroundedAnswerOutput(
        claims=[
            adapter._GroundedClaimOutput(
                claim="Evidence is approved.",
                evidence_refs=["evidence-1"],
            )
        ],
        uncertainty=None,
    )
    sdk_result = _FakeRunResult(
        final_output=grounded,
        new_items=[SimpleNamespace(type="message"), non_function_tool_call, tool_call],
        interruptions=[approval],
        state=state,
    )

    result = adapter.AgentsSDKEngine._result(
        _as_run_result(sdk_result),
        provider_id="provider-test",
    )

    assert isinstance(result.final_output, Mapping)
    assert result.final_output["uncertainty"] is None
    claims = result.final_output["claims"]
    assert isinstance(claims, tuple)
    assert len(claims) == 1
    assert claims[0] == {
        "claim": "Evidence is approved.",
        "evidence_refs": ("evidence-1",),
    }
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "call-tool"
    assert result.tool_calls[0].tool_name == "read_evidence"
    assert result.tool_calls[0].arguments == {"evidence_id": "evidence-1"}
    assert len(result.interruptions) == 1
    assert result.interruptions[0].call_id == "call-approval"
    assert result.continuation == ModelContinuation(
        provider="provider-test",
        payload={"schemaVersion": 1, "cursor": "approval-1"},
    )
    assert result.usage.requests == 1
    assert result.usage.input_tokens == 21
    assert result.usage.output_tokens == 8
    assert result.usage.total_tokens == 29
    assert state.serialization_calls == [
        {"strict_context": True, "include_tracing_api_key": False}
    ]


def test_result_rejects_an_sdk_output_outside_the_provider_neutral_contract() -> None:
    sdk_result = _FakeRunResult(final_output=42)

    with pytest.raises(
        ModelProviderError,
        match="final output must be text or a structured mapping",
    ):
        adapter.AgentsSDKEngine._result(_as_run_result(sdk_result))


@pytest.mark.asyncio
async def test_run_passes_bounded_inputs_and_translates_the_sdk_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_result = _FakeRunResult(final_output='{"status":"ready"}')
    run = AsyncMock(return_value=_as_run_result(sdk_result))
    monkeypatch.setattr(Runner, "run", run)
    invocation = _invocation()

    result = await adapter.AgentsSDKEngine().run(invocation)

    assert result.final_output == {"status": "ready"}
    run.assert_awaited_once()
    awaited = run.await_args
    assert awaited is not None
    args = awaited.args
    kwargs = awaited.kwargs
    assert isinstance(args[0], Agent)
    assert args[1] == invocation.request.input_text
    assert kwargs["context"] == {}
    assert kwargs["max_turns"] == invocation.request.max_turns
    assert kwargs["run_config"].tracing_disabled is True
    assert kwargs["run_config"].trace_include_sensitive_data is False


@pytest.mark.asyncio
async def test_run_maps_an_sdk_failure_to_the_provider_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_failure = AgentsException("provider unavailable")
    monkeypatch.setattr(Runner, "run", AsyncMock(side_effect=sdk_failure))

    with pytest.raises(ModelProviderError, match="SDK run failed") as exc_info:
        await adapter.AgentsSDKEngine().run(_invocation())

    assert exc_info.value.__cause__ is sdk_failure


@pytest.mark.asyncio
async def test_stream_emits_only_text_deltas_then_one_completed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamed = _FakeStreamedResult(
        (
            SimpleNamespace(type="run_item_stream_event"),
            RawResponsesStreamEvent(
                data=cast(Any, SimpleNamespace(type="response.created"))
            ),
            RawResponsesStreamEvent(
                data=cast(
                    Any,
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta="next",
                    ),
                )
            ),
        )
    )
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def run_streamed(*args: object, **kwargs: object) -> RunResultStreaming:
        calls.append((args, kwargs))
        return _as_streamed_result(streamed)

    monkeypatch.setattr(Runner, "run_streamed", run_streamed)
    invocation = _invocation()

    events = [event async for event in adapter.AgentsSDKEngine().stream(invocation)]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.TEXT_DELTA,
        ModelStreamEventKind.COMPLETED,
    ]
    assert events[0].text_delta == "next"
    assert events[1].result is not None
    assert events[1].result.final_output == "grounded answer"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert isinstance(args[0], Agent)
    assert args[1] == invocation.request.input_text
    assert kwargs["context"] == {}
    assert kwargs["max_turns"] == invocation.request.max_turns


@pytest.mark.asyncio
async def test_stream_maps_an_iteration_failure_to_the_provider_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_failure = AgentsException("stream disconnected")
    streamed = _FakeStreamedResult(
        (SimpleNamespace(type="run_item_stream_event"),),
        failure=sdk_failure,
    )
    monkeypatch.setattr(
        Runner,
        "run_streamed",
        lambda *_args, **_kwargs: _as_streamed_result(streamed),
    )

    with pytest.raises(ModelProviderError, match="SDK stream failed") as exc_info:
        _ = [event async for event in adapter.AgentsSDKEngine().stream(_invocation())]

    assert exc_info.value.__cause__ is sdk_failure


def test_apply_decisions_rejects_a_non_function_interruption() -> None:
    state = _DecisionState(
        [_approval_item(_raw_call("call-message", item_type="message"))]
    )

    with pytest.raises(
        UnsupportedModelCapabilityError,
        match="serialized state contains a non-function interruption",
    ):
        adapter.AgentsSDKEngine._apply_decisions(_as_run_state(state), ())


def test_apply_decisions_requires_an_exact_decision_set() -> None:
    state = _DecisionState([_approval_item(_raw_call("call-1"))])

    with pytest.raises(
        ValueError,
        match="decisions must match every interrupted call exactly",
    ):
        adapter.AgentsSDKEngine._apply_decisions(_as_run_state(state), ())

    assert state.approved == []
    assert state.rejected == []


def test_apply_decisions_approves_and_rejects_the_matching_sdk_items() -> None:
    approved_item = _approval_item(_raw_call("call-approved"))
    rejected_item = _approval_item(_raw_call("call-rejected"))
    state = _DecisionState([approved_item, rejected_item])
    decisions = (
        ApprovalDecision(call_id="call-approved", approved=True),
        ApprovalDecision(
            call_id="call-rejected",
            approved=False,
            rejection_message="Evidence is outside the approved snapshot.",
        ),
    )

    adapter.AgentsSDKEngine._apply_decisions(_as_run_state(state), decisions)

    assert state.approved == [approved_item]
    assert state.rejected == [
        (rejected_item, "Evidence is outside the approved snapshot.")
    ]


@pytest.mark.asyncio
async def test_resume_requires_local_continuation_state() -> None:
    with pytest.raises(ValueError, match="requires continuation state"):
        await adapter.AgentsSDKEngine().resume(_invocation())


@pytest.mark.asyncio
async def test_resume_restores_strict_local_state_and_runs_after_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continuation = ModelContinuation(
        provider="provider-test",
        payload={"schemaVersion": 1, "cursor": "approval-1"},
    )
    state = _DecisionState([])
    from_json = AsyncMock(return_value=_as_run_state(state))
    resumed_result = _FakeRunResult(final_output={"status": "resumed"})
    run = AsyncMock(return_value=_as_run_result(resumed_result))
    monkeypatch.setattr(RunState, "from_json", from_json)
    monkeypatch.setattr(Runner, "run", run)
    invocation = _invocation(continuation=continuation)

    result = await adapter.AgentsSDKEngine().resume(invocation)

    assert result.final_output == {"status": "resumed"}
    from_json.assert_awaited_once()
    restored = from_json.await_args
    assert restored is not None
    args = restored.args
    kwargs = restored.kwargs
    assert isinstance(args[0], Agent)
    assert args[1] == {"schemaVersion": 1, "cursor": "approval-1"}
    assert kwargs == {"context_override": {}, "strict_context": True}
    run.assert_awaited_once()
    resumed = run.await_args
    assert resumed is not None
    assert resumed.args[1] is state
    assert resumed.kwargs["max_turns"] == invocation.request.max_turns


@pytest.mark.asyncio
async def test_resume_maps_an_sdk_failure_to_the_provider_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continuation = ModelContinuation(
        provider="provider-test",
        payload={"schemaVersion": 1, "cursor": "approval-1"},
    )
    state = _DecisionState([])
    sdk_failure = AgentsException("resume failed")
    monkeypatch.setattr(
        RunState,
        "from_json",
        AsyncMock(return_value=_as_run_state(state)),
    )
    monkeypatch.setattr(Runner, "run", AsyncMock(side_effect=sdk_failure))

    with pytest.raises(ModelProviderError, match="SDK resume failed") as exc_info:
        await adapter.AgentsSDKEngine().resume(_invocation(continuation=continuation))

    assert exc_info.value.__cause__ is sdk_failure
