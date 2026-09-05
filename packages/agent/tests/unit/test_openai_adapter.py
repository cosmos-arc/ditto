from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from types import MappingProxyType, SimpleNamespace
from typing import cast

import pytest
from agents.items import ToolApprovalItem
from agents.tool_context import ToolContext
from ditto_agent.models.openai_adapter import (
    AgentsSDKEngine,
    OpenAIAgentsModel,
    OpenAICompatibleAgentsModel,
    OpenAIInvocation,
    _arguments,
    _decode_model_output,
    _function_tool_call,
    _interruption,
    _response_text_delta,
)
from ditto_agent.models.port import (
    ModelContinuation,
    ModelOutputContract,
    ModelProviderError,
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


def test_model_output_decodes_an_exact_json_object_for_governed_grounding() -> None:
    raw = (
        '{"claims":[{"claim":"Ready.","evidence_refs":["evidence-1"]}],'
        '"uncertainty":null}'
    )

    assert _decode_model_output(raw) == {
        "claims": [{"claim": "Ready.", "evidence_refs": ["evidence-1"]}],
        "uncertainty": None,
    }
    assert _decode_model_output("ordinary text") == "ordinary text"
    assert _decode_model_output("[1,2,3]") == "[1,2,3]"


def test_model_output_decodes_one_json_markdown_fence() -> None:
    """OpenAI-compatible providers may fence an otherwise exact JSON object."""
    raw = (
        "```json\n"
        '{"claims":[{"claim":"Ready.","evidence_refs":["evidence-1"]}],'
        '"uncertainty":null}\n'
        "```"
    )

    assert _decode_model_output(raw) == {
        "claims": [{"claim": "Ready.", "evidence_refs": ["evidence-1"]}],
        "uncertainty": None,
    }


def test_model_output_preserves_non_text_and_non_object_json_values() -> None:
    frozen = MappingProxyType({"status": "ready"})
    assert _decode_model_output(frozen) is frozen
    assert _decode_model_output(None) is None
    assert _decode_model_output("true") == "true"


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
async def test_sdk_function_tool_materializes_read_only_host_mappings() -> None:
    class ReadOnlyMappingInvoker(RecordingToolInvoker):
        async def invoke(
            self,
            tool_name: str,
            arguments_json: str,
            *,
            call_id: str,
        ) -> object:
            await super().invoke(
                tool_name,
                arguments_json,
                call_id=call_id,
            )
            return MappingProxyType({"status": "ok"})

    invoker = ReadOnlyMappingInvoker()
    sdk_tool = AgentsSDKEngine(tool_invoker=invoker)._function_tool(_request().tools[0])
    context = ToolContext(
        context={},
        tool_name=sdk_tool.name,
        tool_call_id="call-provider-002",
        tool_arguments='{"experiment_id":"experiment-001"}',
    )

    result = await sdk_tool.on_invoke_tool(
        context,
        '{"experiment_id":"experiment-001"}',
    )

    assert type(result) is dict
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_sdk_function_tool_returns_scalars_and_fails_closed_without_invoker() -> (
    None
):
    class ScalarInvoker(RecordingToolInvoker):
        async def invoke(
            self,
            tool_name: str,
            arguments_json: str,
            *,
            call_id: str,
        ) -> object:
            await super().invoke(tool_name, arguments_json, call_id=call_id)
            return 42

    context = ToolContext(
        context={},
        tool_name="experiment_summary",
        tool_call_id="call-provider-003",
        tool_arguments="{}",
    )
    scalar_tool = AgentsSDKEngine(tool_invoker=ScalarInvoker())._function_tool(
        _request().tools[0]
    )
    assert await scalar_tool.on_invoke_tool(context, "{}") == 42

    unconfigured = AgentsSDKEngine()._function_tool(_request().tools[0])
    with pytest.raises(UnsupportedModelCapabilityError, match="no deterministic host"):
        await unconfigured.on_invoke_tool(context, "{}")


def test_provider_tool_payload_decoders_reject_malformed_shapes() -> None:
    with pytest.raises(ModelProviderError, match="not valid JSON"):
        _arguments("{invalid")
    with pytest.raises(ModelProviderError, match="must be a JSON object"):
        _arguments("[1, 2]")

    assert _function_tool_call(SimpleNamespace(type="message")) is None
    with pytest.raises(ModelProviderError, match="function tool call is malformed"):
        _function_tool_call(SimpleNamespace(type="function_call", call_id=1))

    assert _response_text_delta(SimpleNamespace(type="message")) is None
    with pytest.raises(ModelProviderError, match="text delta is malformed"):
        _response_text_delta(
            SimpleNamespace(type="response.output_text.delta", delta=1)
        )
    assert (
        _response_text_delta(
            SimpleNamespace(type="response.output_text.delta", delta="")
        )
        is None
    )
    assert (
        _response_text_delta(
            SimpleNamespace(type="response.output_text.delta", delta="next")
        )
        == "next"
    )


def test_interruption_requires_an_exact_function_call() -> None:
    non_function = cast(
        "ToolApprovalItem",
        SimpleNamespace(raw_item=SimpleNamespace(type="message")),
    )
    with pytest.raises(UnsupportedModelCapabilityError, match="non-function"):
        _interruption(non_function)

    valid = cast(
        "ToolApprovalItem",
        SimpleNamespace(
            raw_item=SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="experiment_summary",
                arguments='{"experiment_id":"experiment-1"}',
            )
        ),
    )
    interruption = _interruption(valid)
    assert interruption.call_id == "call-1"
    assert interruption.arguments == {"experiment_id": "experiment-1"}


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("store", True, "store must remain false"),
        ("tracing_disabled", False, "sensitive tracing"),
        ("trace_include_sensitive_data", True, "sensitive tracing"),
        ("use_responses", 1, "API mode must be boolean"),
        ("native_structured_outputs", 1, "capability must be boolean"),
        ("reasoning_effort", "extreme", "reasoning_effort is unsupported"),
    ],
)
def test_invocation_rejects_privacy_or_capability_drift(
    field_name: str,
    value: object,
    message: str,
) -> None:
    invocation = OpenAIInvocation(
        request=_request(),
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
    )
    with pytest.raises(ValueError, match=message):
        replace(invocation, **{field_name: value})


def test_sdk_inputs_preserve_compatible_api_and_reasoning_capabilities() -> None:
    invocation = OpenAIInvocation(
        request=replace(
            _request(),
            output_contract=ModelOutputContract.GROUNDED_ANSWER,
        ),
        model_id="compatible-model",
        api_key="test-key",
        project_id=None,
        base_url="http://127.0.0.1:11434/v1",
        provider_id="compatible",
        use_responses=False,
        native_structured_outputs=False,
        reasoning_effort="high",
    )

    agent, run_config, _provider = AgentsSDKEngine()._sdk_inputs(invocation)

    assert agent.output_type is None
    assert run_config.model_settings is not None
    assert run_config.model_settings.store is None
    assert run_config.model_settings.reasoning is not None
    assert run_config.model_settings.reasoning.effort == "high"


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("use_responses", 1, "API mode must be boolean"),
        ("reasoning_effort", "extreme", "reasoning_effort is unsupported"),
    ],
)
def test_compatible_model_rejects_untyped_capabilities(
    field_name: str,
    value: object,
    message: str,
) -> None:
    kwargs: dict[str, object] = {
        "model_id": "compatible-model",
        "api_key": "test-key",
        field_name: value,
    }
    with pytest.raises(ValueError, match=message):
        OpenAICompatibleAgentsModel(**kwargs)


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


def test_sdk_enforces_grounded_answer_output_contract() -> None:
    request = replace(
        _request(),
        output_contract=ModelOutputContract.GROUNDED_ANSWER,
    )
    invocation = OpenAIInvocation(
        request=request,
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
    )

    agent, _run_config, _provider = AgentsSDKEngine()._sdk_inputs(invocation)

    assert agent.output_type is not None


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
