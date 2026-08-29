from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
from ditto_agent.models.fake import ScriptedAgentModel, ScriptedFailure, ScriptedOutcome
from ditto_agent.models.glm_adapter import GLMAgentsModel, GLMEndpointKind
from ditto_agent.models.openai_adapter import OpenAIAgentsModel, OpenAIInvocation
from ditto_agent.models.port import (
    AgentModelPort,
    ApprovalDecision,
    ModelContinuation,
    ModelFailureKind,
    ModelInterruption,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelUsage,
    ResumeModelRequest,
)


def _request() -> ModelRequest:
    return ModelRequest(
        run_id="run-001",
        agent_name="evidence-copilot",
        instructions="Return grounded evidence only.",
        input_text="Summarize experiment exp-001.",
        max_turns=4,
        max_output_tokens=2_048,
        tools=(),
    )


def _interrupted_result(*, provider: str = "scripted") -> ModelResult:
    return ModelResult(
        final_output=None,
        tool_calls=(
            ModelToolCall(
                call_id="call-001",
                tool_name="experiment_summary",
                arguments={"experiment_id": "exp-001"},
            ),
        ),
        usage=ModelUsage(requests=1, input_tokens=40, output_tokens=12),
        interruptions=(
            ModelInterruption(
                call_id="call-001",
                tool_name="experiment_summary",
                arguments={"experiment_id": "exp-001"},
            ),
        ),
        continuation=ModelContinuation(
            provider=provider,
            payload={"cursor": "step-002"},
        ),
    )


def _completed_result() -> ModelResult:
    return ModelResult(
        final_output={"answer": "The experiment completed."},
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=25, output_tokens=9),
        interruptions=(),
        continuation=None,
    )


class _ContractOpenAIEngine:
    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id

    async def run(self, invocation: OpenAIInvocation) -> ModelResult:
        del invocation
        return _interrupted_result(provider=self._provider_id)

    async def stream(
        self, invocation: OpenAIInvocation
    ) -> AsyncIterator[ModelStreamEvent]:
        del invocation
        for delta in ("The experiment ", "completed."):
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TEXT_DELTA,
                text_delta=delta,
            )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.COMPLETED,
            result=_completed_result(),
        )

    async def resume(self, invocation: OpenAIInvocation) -> ModelResult:
        assert invocation.continuation is not None
        assert invocation.continuation.provider == self._provider_id
        return _completed_result()


class _RecordingToolInvoker:
    def __init__(self) -> None:
        self.call_ids: list[str] = []

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        del tool_name, arguments_json
        self.call_ids.append(call_id)
        return {"status": "ok"}


def _contract_provider(kind: str) -> AgentModelPort:
    if kind == "fake":
        return ScriptedAgentModel(
            script=(
                ScriptedOutcome(result=_interrupted_result()),
                ScriptedOutcome(
                    result=_completed_result(),
                    stream_deltas=("The experiment ", "completed."),
                ),
                ScriptedOutcome(result=_completed_result()),
            )
        )
    if kind == "glm-adapter":
        return GLMAgentsModel(
            model_id="stub-model",
            api_key="stub-key",
            endpoint_kind=GLMEndpointKind.CODING_PLAN_RESPONSES,
            engine=_ContractOpenAIEngine("glm_agents"),
        )
    return OpenAIAgentsModel(
        model_id="stub-model",
        api_key="stub-key",
        project_id="stub-project",
        engine=_ContractOpenAIEngine("openai_agents"),
    )


@pytest.mark.parametrize("provider_kind", ["fake", "openai-adapter", "glm-adapter"])
@pytest.mark.asyncio
async def test_providers_satisfy_shared_run_stream_and_resume_contract(
    provider_kind: str,
) -> None:
    provider = _contract_provider(provider_kind)

    assert isinstance(provider, AgentModelPort)
    interrupted = await provider.run(_request())
    assert interrupted.usage.total_tokens == 52
    assert interrupted.interruptions[0].call_id == "call-001"
    assert interrupted.continuation is not None

    streamed = [event async for event in provider.stream(_request())]
    assert [event.kind for event in streamed] == [
        ModelStreamEventKind.TEXT_DELTA,
        ModelStreamEventKind.TEXT_DELTA,
        ModelStreamEventKind.COMPLETED,
    ]
    assert [event.text_delta for event in streamed[:-1]] == [
        "The experiment ",
        "completed.",
    ]
    assert streamed[-1].result == _completed_result()

    resumed = await provider.resume(
        ResumeModelRequest(
            request=_request(),
            continuation=interrupted.continuation,
            decisions=(ApprovalDecision(call_id="call-001", approved=True),),
        )
    )
    assert resumed.final_output == {"answer": "The experiment completed."}


@pytest.mark.parametrize(("approved", "expected_calls"), [(True, 1), (False, 0)])
@pytest.mark.asyncio
async def test_scripted_resume_executes_only_approved_interrupted_calls(
    approved: bool,
    expected_calls: int,
) -> None:
    invoker = _RecordingToolInvoker()
    interrupted = _interrupted_result()
    resumed = ModelResult(
        final_output={"answer": "The reviewed call was handled."},
        tool_calls=interrupted.tool_calls,
        usage=ModelUsage(requests=1, input_tokens=25, output_tokens=9),
        interruptions=(),
        continuation=None,
    )
    provider = ScriptedAgentModel(
        script=(ScriptedOutcome(result=resumed),),
        tool_invoker=invoker,
    )

    await provider.resume(
        ResumeModelRequest(
            request=_request(),
            continuation=ModelContinuation(
                provider="scripted",
                payload={"cursor": "step-002"},
            ),
            decisions=(ApprovalDecision(call_id="call-001", approved=approved),),
        )
    )

    assert len(invoker.call_ids) == expected_calls


@pytest.mark.parametrize(
    ("kind", "error_type"),
    [
        (ModelFailureKind.TIMEOUT, TimeoutError),
        (ModelFailureKind.RATE_LIMIT, ModelProviderError),
        (ModelFailureKind.PROVIDER, ModelProviderError),
    ],
)
@pytest.mark.asyncio
async def test_scripted_provider_exposes_typed_failures(
    kind: ModelFailureKind,
    error_type: type[Exception],
) -> None:
    provider = ScriptedAgentModel(
        script=(ScriptedFailure(kind=kind, message="scripted failure"),)
    )

    with pytest.raises(error_type, match="scripted failure"):
        await provider.run(_request())


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ModelUsage(
            requests=1, input_tokens=2, output_tokens=3, total_tokens=99
        ),
        lambda: ModelResult(
            final_output=None,
            tool_calls=(),
            usage=ModelUsage(requests=0, input_tokens=0, output_tokens=0),
            interruptions=(
                ModelInterruption(call_id="call-001", tool_name="tool", arguments={}),
            ),
            continuation=None,
        ),
        lambda: ModelStreamEvent(
            kind=ModelStreamEventKind.TEXT_DELTA,
            text_delta=" ",
            result=_completed_result(),
        ),
    ],
)
def test_model_contracts_fail_closed_on_inconsistent_state(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        factory()
