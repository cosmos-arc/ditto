from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from ditto_agent.models.glm_adapter import (
    GLM_CODING_PLAN_RESPONSES_BASE_URL,
    GLM_FORMAL_API_BASE_URL,
    GLMAgentsModel,
    GLMEndpointKind,
)
from ditto_agent.models.openai_adapter import AgentsSDKEngine, OpenAIInvocation
from ditto_agent.models.port import (
    ModelContinuation,
    ModelOutputContract,
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
        final_output="GLM_OK",
        tool_calls=(),
        usage=ModelUsage(requests=1, input_tokens=12, output_tokens=4),
        interruptions=(),
        continuation=None,
    )


def _request(*, kind: ModelToolKind = ModelToolKind.FUNCTION) -> ModelRequest:
    return ModelRequest(
        run_id="run-glm-001",
        agent_name="glm-validation",
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


@pytest.mark.asyncio
async def test_glm_adapter_fixes_responses_endpoint_and_provider_identity() -> None:
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.3",
        api_key="test-plan-key",
        endpoint_kind=GLMEndpointKind.CODING_PLAN_RESPONSES,
        engine=engine,
    )

    result = await provider.run(_request())

    assert result == _result()
    invocation = engine.invocations[0]
    assert invocation.base_url == GLM_CODING_PLAN_RESPONSES_BASE_URL
    assert invocation.project_id is None
    assert invocation.provider_id == "glm_agents"
    assert invocation.store is False
    assert invocation.tracing_disabled is True
    assert invocation.trace_include_sensitive_data is False
    assert invocation.use_responses is True
    assert "test-plan-key" not in repr(invocation)


@pytest.mark.asyncio
async def test_glm_coding_plan_keeps_grounded_contract_local() -> None:
    """Coding Plan rejects SDK response_format but local grounding stays strict."""
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.3",
        api_key="test-plan-key",
        endpoint_kind=GLMEndpointKind.CODING_PLAN_RESPONSES,
        engine=engine,
    )

    await provider.run(
        replace(_request(), output_contract=ModelOutputContract.GROUNDED_ANSWER)
    )

    invocation = engine.invocations[0]
    agent, _run_config, _sdk_provider = AgentsSDKEngine()._sdk_inputs(invocation)
    assert agent.output_type is None


def test_glm_endpoint_reaches_the_concrete_sdk_provider() -> None:
    invocation = OpenAIInvocation(
        request=_request(),
        model_id="glm-5.3",
        api_key="test-plan-key",
        project_id=None,
        base_url=GLM_CODING_PLAN_RESPONSES_BASE_URL,
        provider_id="glm_agents",
    )

    _agent, _run_config, sdk_provider = AgentsSDKEngine()._sdk_inputs(invocation)

    assert str(sdk_provider._get_client().base_url) == (
        f"{GLM_CODING_PLAN_RESPONSES_BASE_URL}/"
    )


@pytest.mark.asyncio
async def test_glm_formal_adapter_uses_standard_chat_completions_endpoint() -> None:
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.3",
        api_key="test-formal-key",
        endpoint_kind=GLMEndpointKind.FORMAL_API_CHAT_COMPLETIONS,
        engine=engine,
    )

    await provider.run(_request())

    invocation = engine.invocations[0]
    assert invocation.base_url == GLM_FORMAL_API_BASE_URL
    assert invocation.use_responses is False
    assert invocation.provider_id == "glm_formal_api_agents"
    _agent, run_config, sdk_provider = AgentsSDKEngine()._sdk_inputs(invocation)
    assert sdk_provider._use_responses is False
    assert run_config.model_settings is not None
    assert run_config.model_settings.store is None


@pytest.mark.asyncio
async def test_glm_formal_adapter_applies_reasoning_effort_to_sdk_call() -> None:
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.2",
        api_key="test-formal-key",
        endpoint_kind=GLMEndpointKind.FORMAL_API_CHAT_COMPLETIONS,
        reasoning_effort="max",
        engine=engine,
    )

    await provider.run(_request())

    invocation = engine.invocations[0]
    assert invocation.reasoning_effort == "max"
    _agent, run_config, _sdk_provider = AgentsSDKEngine()._sdk_inputs(invocation)
    assert run_config.model_settings is not None
    assert run_config.model_settings.reasoning is not None
    assert run_config.model_settings.reasoning.effort == "max"


@pytest.mark.asyncio
async def test_glm_adapter_rejects_hosted_tools_before_engine_call() -> None:
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.3",
        api_key="test-plan-key",
        endpoint_kind=GLMEndpointKind.CODING_PLAN_RESPONSES,
        engine=engine,
    )

    with pytest.raises(UnsupportedModelCapabilityError, match="web_search"):
        await provider.run(_request(kind=ModelToolKind.WEB_SEARCH))

    assert engine.invocations == []


@pytest.mark.asyncio
async def test_glm_adapter_rejects_openai_continuation_before_engine_call() -> None:
    engine = RecordingEngine()
    provider = GLMAgentsModel(
        model_id="glm-5.3",
        api_key="test-plan-key",
        endpoint_kind=GLMEndpointKind.CODING_PLAN_RESPONSES,
        engine=engine,
    )

    with pytest.raises(ValueError, match="glm_agents"):
        await provider.resume(
            ResumeModelRequest(
                request=_request(),
                continuation=ModelContinuation(
                    provider="openai_agents", payload={"cursor": "foreign"}
                ),
                decisions=(),
            )
        )

    assert engine.invocations == []
