from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from agents.tool_context import ToolContext
from ditto_agent.models.openai_adapter import (
    AgentsSDKEngine,
    OpenAIAgentsModel,
    OpenAIInvocation,
)
from ditto_agent.models.port import (
    ModelContinuation,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
    ResumeModelRequest,
    UnsupportedModelCapabilityError,
)


def _result() -> ModelResult:
    return ModelResult(
        final_output="grounded answer",
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=12, output_tokens=4),
        interruptions=(),
        continuation=None,
    )


def _request(*, kind: ModelToolKind = ModelToolKind.FUNCTION) -> ModelRequest:
    return ModelRequest(
        run_id="run-001",
        agent_name="evidence-copilot",
        instructions="Use only registered Ditto tools.",
        input_text="Read exp-001.",
        max_turns=3,
        max_output_tokens=1_024,
        tools=(
            ModelToolSpec(
                kind=kind,
                name="experiment_summary",
                description="Read one experiment summary.",
                input_schema={
                    "type": "object",
                    "properties": {"experiment_id": {"type": "string"}},
                    "required": ["experiment_id"],
                    "additionalProperties": False,
                },
                requires_approval=False,
            ),
        ),
    )


class RecordingEngine:
    def __init__(self) -> None:
        self.invocations: list[OpenAIInvocation] = []

    async def run(self, invocation: OpenAIInvocation) -> ModelResult:
        self.invocations.append(invocation)
        return _result()

    async def stream(
        self, invocation: OpenAIInvocation
    ) -> AsyncIterator[ModelStreamEvent]:
        self.invocations.append(invocation)
        yield ModelStreamEvent(kind=ModelStreamEventKind.COMPLETED, result=_result())

    async def resume(self, invocation: OpenAIInvocation) -> ModelResult:
        self.invocations.append(invocation)
        return _result()


class RecordingToolInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        self.calls.append((tool_name, arguments_json, call_id))
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_sdk_function_tool_preserves_provider_call_id_for_host_audit() -> None:
    invoker = RecordingToolInvoker()
    sdk_tool = AgentsSDKEngine(tool_invoker=invoker)._function_tool(_request().tools[0])
    context = ToolContext(
        context={},
        tool_name=sdk_tool.name,
        tool_call_id="call-provider-001",
        tool_arguments='{"experiment_id":"experiment-001"}',
    )

    result = await sdk_tool.on_invoke_tool(
        context,
        '{"experiment_id":"experiment-001"}',
    )

    assert result == {"status": "ok"}
    assert invoker.calls == [
        (
            "experiment_summary",
            '{"experiment_id":"experiment-001"}',
            "call-provider-001",
        )
    ]


@pytest.mark.asyncio
async def test_openai_adapter_forces_private_responses_and_local_tracing() -> None:
    engine = RecordingEngine()
    provider = OpenAIAgentsModel(
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        engine=engine,
    )

    result = await provider.run(_request())

    assert result == _result()
    invocation = engine.invocations[0]
    assert invocation.store is False
    assert invocation.tracing_disabled is True
    assert invocation.trace_include_sensitive_data is False
    assert invocation.use_responses is True
    assert invocation.model_id == "gpt-5.6-terra-2026-08-01"
    assert invocation.request.tools[0].kind is ModelToolKind.FUNCTION
    assert "test-key" not in repr(invocation)


@pytest.mark.asyncio
async def test_openai_adapter_requires_a_tool_when_the_host_contract_says_so() -> None:
    engine = RecordingEngine()
    provider = OpenAIAgentsModel(
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        engine=engine,
    )

    tool_name = _request().tools[0].name
    await provider.run(replace(_request(), required_tool_name=tool_name))

    _agent, run_config, _sdk_provider = AgentsSDKEngine()._sdk_inputs(
        engine.invocations[0]
    )
    assert run_config.model_settings is not None
    assert run_config.model_settings.tool_choice == tool_name


def test_openai_adapter_requires_project_identity() -> None:
    with pytest.raises(ValueError, match="project_id"):
        OpenAIAgentsModel(
            model_id="gpt-5.6-terra-2026-08-01",
            api_key="test-key",
            project_id=None,
        )


@pytest.mark.parametrize(
    "kind",
    [
        ModelToolKind.WEB_SEARCH,
        ModelToolKind.FILE_SEARCH,
        ModelToolKind.CODE_INTERPRETER,
        ModelToolKind.SHELL,
        ModelToolKind.COMPUTER,
        ModelToolKind.MCP,
    ],
)
@pytest.mark.asyncio
async def test_openai_adapter_rejects_hosted_tools_before_engine_call(
    kind: ModelToolKind,
) -> None:
    engine = RecordingEngine()
    provider = OpenAIAgentsModel(
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        engine=engine,
    )

    with pytest.raises(UnsupportedModelCapabilityError, match=kind.value):
        await provider.run(_request(kind=kind))

    assert engine.invocations == []


@pytest.mark.asyncio
async def test_openai_adapter_stream_and_resume_preserve_enforced_settings() -> None:
    engine = RecordingEngine()
    provider = OpenAIAgentsModel(
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        engine=engine,
    )

    events = [event async for event in provider.stream(_request())]
    result = await provider.resume(
        ResumeModelRequest(
            request=_request(),
            continuation=ModelContinuation(
                provider="openai_agents", payload={"$schemaVersion": "1.13"}
            ),
            decisions=(),
        )
    )

    assert events[-1].result == _result()
    assert result == _result()
    assert all(invocation.store is False for invocation in engine.invocations)
    assert engine.invocations[-1].continuation is not None


@pytest.mark.asyncio
async def test_openai_adapter_rejects_foreign_continuation_before_engine_call() -> None:
    engine = RecordingEngine()
    provider = OpenAIAgentsModel(
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        engine=engine,
    )

    with pytest.raises(ValueError, match="provider"):
        await provider.resume(
            ResumeModelRequest(
                request=_request(),
                continuation=ModelContinuation(
                    provider="scripted", payload={"cursor": "step-2"}
                ),
                decisions=(),
            )
        )

    assert engine.invocations == []
