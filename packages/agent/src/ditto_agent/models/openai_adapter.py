"""OpenAI Agents SDK adapter with fail-closed capability and privacy policy."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

import orjson
from agents import (
    Agent,
    FunctionTool,
    ModelSettings,
    RunConfig,
    Runner,
    RunResult,
    RunResultStreaming,
    RunState,
)
from agents.exceptions import AgentsException
from agents.items import ToolApprovalItem, ToolCallItem
from agents.models.openai_provider import OpenAIProvider
from agents.stream_events import RawResponsesStreamEvent
from agents.tool_context import ToolContext

from ditto_agent._canonical import canonical_bytes
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.models.port import (
    ApprovalDecision,
    ModelContinuation,
    ModelInterruption,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolInvoker,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
    ResumeModelRequest,
    UnsupportedModelCapabilityError,
)

_PROVIDER_ID = "openai_agents"
type ReasoningEffort = (
    Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None
)
_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)


class _FunctionToolCall(Protocol):
    """Structural subset of the SDK's transitive Responses function-call type."""

    type: str
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class OpenAIInvocation:
    """Complete enforced settings passed from the adapter to its SDK engine."""

    request: ModelRequest
    model_id: str
    api_key: str = field(repr=False)
    project_id: str | None
    base_url: str | None = None
    provider_id: str = _PROVIDER_ID
    store: bool = False
    tracing_disabled: bool = True
    trace_include_sensitive_data: bool = False
    use_responses: bool = True
    reasoning_effort: ReasoningEffort = None
    continuation: ModelContinuation | None = None
    decisions: tuple[ApprovalDecision, ...] = ()

    def __post_init__(self) -> None:
        """Validate injected secrets and immutable privacy controls."""
        for field_name in ("model_id", "api_key", "provider_id"):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        for field_name in ("project_id", "base_url"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    normalized_text(value, field=field_name),
                )
        if self.store:
            raise ValueError("OpenAI Responses store must remain false")
        if not self.tracing_disabled or self.trace_include_sensitive_data:
            raise ValueError("OpenAI hosted sensitive tracing must remain disabled")
        if type(self.use_responses) is not bool:
            raise ValueError("OpenAI-compatible API mode must be boolean")
        if self.reasoning_effort is not None:
            normalized_effort = normalized_text(
                self.reasoning_effort,
                field="reasoning_effort",
            )
            if normalized_effort not in _REASONING_EFFORTS:
                raise ValueError("reasoning_effort is unsupported")
            object.__setattr__(
                self,
                "reasoning_effort",
                cast(ReasoningEffort, normalized_effort),
            )


class OpenAIEngine(Protocol):
    """Injectable SDK execution boundary used for deterministic adapter tests."""

    async def run(self, invocation: OpenAIInvocation) -> ModelResult:
        """Execute an initial invocation."""
        ...

    def stream(self, invocation: OpenAIInvocation) -> AsyncIterator[ModelStreamEvent]:
        """Stream an initial invocation."""
        ...

    async def resume(self, invocation: OpenAIInvocation) -> ModelResult:
        """Resume a serialized SDK RunState."""
        ...


class _UnconfiguredToolInvoker:
    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        del arguments_json
        del call_id
        raise UnsupportedModelCapabilityError(
            f"no deterministic host invoker is configured for function tool {tool_name}"
        )


def _plain_mapping(value: Mapping[str, object]) -> dict[str, object]:
    decoded: object = orjson.loads(canonical_bytes(value))
    if not isinstance(decoded, dict):
        raise TypeError("canonical mapping did not decode to an object")
    mapping = cast(dict[object, object], decoded)
    if not all(isinstance(key, str) for key in mapping):
        raise TypeError("canonical mapping keys must be strings")
    return cast(dict[str, object], mapping)


def _arguments(raw: str) -> Mapping[str, object]:
    try:
        decoded: object = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise ModelProviderError("model tool arguments are not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ModelProviderError("model tool arguments must be a JSON object")
    mapping = cast(dict[object, object], decoded)
    if not all(isinstance(key, str) for key in mapping):
        raise ModelProviderError("model tool arguments must be a JSON object")
    return cast(dict[str, object], mapping)


def _function_tool_call(raw: object) -> _FunctionToolCall | None:
    if getattr(raw, "type", None) != "function_call":
        return None
    fields = tuple(
        getattr(raw, name, None) for name in ("call_id", "name", "arguments")
    )
    if not all(isinstance(value, str) for value in fields):
        raise ModelProviderError("OpenAI function tool call is malformed")
    return cast(_FunctionToolCall, raw)


def _response_text_delta(raw: object) -> str | None:
    if getattr(raw, "type", None) != "response.output_text.delta":
        return None
    delta = getattr(raw, "delta", None)
    if not isinstance(delta, str):
        raise ModelProviderError("OpenAI response text delta is malformed")
    return delta or None


def _tool_call(raw: _FunctionToolCall) -> ModelToolCall:
    return ModelToolCall(
        call_id=raw.call_id,
        tool_name=raw.name,
        arguments=_arguments(raw.arguments),
    )


def _interruption(item: ToolApprovalItem) -> ModelInterruption:
    raw_call = _function_tool_call(item.raw_item)
    if raw_call is None:
        raise UnsupportedModelCapabilityError(
            "OpenAI returned a non-function tool interruption"
        )
    call = _tool_call(raw_call)
    return ModelInterruption(
        call_id=call.call_id,
        tool_name=call.tool_name,
        arguments=call.arguments,
    )


class AgentsSDKEngine:
    """Concrete zero-global-state bridge to openai-agents 0.20.x."""

    def __init__(self, *, tool_invoker: ModelToolInvoker | None = None) -> None:
        self._tool_invoker = tool_invoker or _UnconfiguredToolInvoker()

    def _function_tool(self, spec: ModelToolSpec) -> FunctionTool:
        async def invoke(context: ToolContext[object], arguments_json: str) -> object:
            return await self._tool_invoker.invoke(
                spec.name,
                arguments_json,
                call_id=context.tool_call_id,
            )

        return FunctionTool(
            name=spec.name,
            description=spec.description,
            params_json_schema=_plain_mapping(spec.input_schema),
            on_invoke_tool=invoke,
            strict_json_schema=True,
            needs_approval=spec.requires_approval,
        )

    def _sdk_inputs(
        self, invocation: OpenAIInvocation
    ) -> tuple[Agent[object], RunConfig, OpenAIProvider]:
        settings = ModelSettings(
            store=False if invocation.use_responses else None,
            max_tokens=invocation.request.max_output_tokens,
            tool_choice=invocation.request.required_tool_name,
            parallel_tool_calls=False,
            reasoning=(
                {"effort": invocation.reasoning_effort}
                if invocation.reasoning_effort is not None
                else None
            ),
        )
        provider = OpenAIProvider(
            api_key=invocation.api_key,
            project=invocation.project_id,
            base_url=invocation.base_url,
            use_responses=invocation.use_responses,
            strict_feature_validation=True,
        )
        agent = Agent[object](
            name=invocation.request.agent_name,
            instructions=invocation.request.instructions,
            tools=[self._function_tool(tool) for tool in invocation.request.tools],
            model=invocation.model_id,
            model_settings=settings,
        )
        run_config = RunConfig(
            model_provider=provider,
            model_settings=settings,
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
        return agent, run_config, provider

    @staticmethod
    def _result(
        result: RunResult | RunResultStreaming,
        *,
        provider_id: str = _PROVIDER_ID,
    ) -> ModelResult:
        tool_calls: list[ModelToolCall] = []
        for item in result.new_items:
            if isinstance(item, ToolCallItem):
                raw_call = _function_tool_call(item.raw_item)
                if raw_call is not None:
                    tool_calls.append(_tool_call(raw_call))
        interruptions = tuple(_interruption(item) for item in result.interruptions)
        continuation = (
            ModelContinuation(
                provider=provider_id,
                payload=result.to_state().to_json(
                    strict_context=True,
                    include_tracing_api_key=False,
                ),
            )
            if interruptions
            else None
        )
        usage = result.context_wrapper.usage
        raw_output: object = result.final_output
        if raw_output is not None and not isinstance(raw_output, (str, Mapping)):
            raise ModelProviderError(
                "OpenAI final output must be text or a structured mapping"
            )
        output = cast(str | Mapping[str, object] | None, raw_output)
        return ModelResult(
            final_output=output,
            tool_calls=tuple(tool_calls),
            usage=ModelUsage(
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            ),
            interruptions=interruptions,
            continuation=continuation,
        )

    async def run(self, invocation: OpenAIInvocation) -> ModelResult:
        """Run through the SDK with explicit provider and privacy settings."""
        agent, run_config, _provider = self._sdk_inputs(invocation)
        try:
            result = await Runner.run(
                agent,
                invocation.request.input_text,
                context={},
                max_turns=invocation.request.max_turns,
                run_config=run_config,
            )
        except AgentsException as exc:
            raise ModelProviderError("OpenAI Agents SDK run failed") from exc
        return self._result(result, provider_id=invocation.provider_id)

    async def stream(
        self, invocation: OpenAIInvocation
    ) -> AsyncIterator[ModelStreamEvent]:
        """Translate SDK text deltas and emit one provider-neutral completion."""
        agent, run_config, _provider = self._sdk_inputs(invocation)
        streamed = Runner.run_streamed(
            agent,
            invocation.request.input_text,
            context={},
            max_turns=invocation.request.max_turns,
            run_config=run_config,
        )
        try:
            async for event in streamed.stream_events():
                if isinstance(event, RawResponsesStreamEvent):
                    delta = _response_text_delta(event.data)
                    if delta is None:
                        continue
                    yield ModelStreamEvent(
                        kind=ModelStreamEventKind.TEXT_DELTA,
                        text_delta=delta,
                    )
        except AgentsException as exc:
            raise ModelProviderError("OpenAI Agents SDK stream failed") from exc
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.COMPLETED,
            result=self._result(streamed, provider_id=invocation.provider_id),
        )

    @staticmethod
    def _apply_decisions(
        state: RunState[object], decisions: tuple[ApprovalDecision, ...]
    ) -> None:
        interruptions = state.get_interruptions()
        by_call_id: dict[str, ToolApprovalItem] = {}
        for item in interruptions:
            raw_call = _function_tool_call(item.raw_item)
            if raw_call is None:
                raise UnsupportedModelCapabilityError(
                    "serialized state contains a non-function interruption"
                )
            by_call_id[raw_call.call_id] = item
        if set(by_call_id) != {decision.call_id for decision in decisions}:
            raise ValueError(
                "approval decisions must match every interrupted call exactly"
            )
        for decision in decisions:
            item = by_call_id[decision.call_id]
            if decision.approved:
                state.approve(item)
            else:
                state.reject(item, rejection_message=decision.rejection_message)

    async def resume(self, invocation: OpenAIInvocation) -> ModelResult:
        """Restore local SDK state, apply exact decisions, and continue."""
        if invocation.continuation is None:
            raise ValueError("resume invocation requires continuation state")
        agent, run_config, _provider = self._sdk_inputs(invocation)
        state = await RunState.from_json(
            agent,
            _plain_mapping(invocation.continuation.payload),
            context_override={},
            strict_context=True,
        )
        self._apply_decisions(state, invocation.decisions)
        try:
            result = await Runner.run(
                agent,
                state,
                max_turns=invocation.request.max_turns,
                run_config=run_config,
            )
        except AgentsException as exc:
            raise ModelProviderError("OpenAI Agents SDK resume failed") from exc
        return self._result(result, provider_id=invocation.provider_id)


class OpenAICompatibleAgentsModel:
    """Internal OpenAI-compatible adapter with provider-specific identity."""

    _provider_name = "OpenAI"

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        engine: OpenAIEngine | None = None,
        base_url: str | None = None,
        provider_id: str = _PROVIDER_ID,
        use_responses: bool = True,
        reasoning_effort: ReasoningEffort = None,
    ) -> None:
        self._model_id = normalized_text(model_id, field="model_id")
        self._api_key = normalized_text(api_key, field="api_key")
        self._project_id: str | None = None
        self._base_url = (
            normalized_text(base_url, field="base_url")
            if base_url is not None
            else None
        )
        self._provider_id = normalized_text(provider_id, field="provider_id")
        if type(use_responses) is not bool:
            raise ValueError("OpenAI-compatible API mode must be boolean")
        self._use_responses = use_responses
        if reasoning_effort is not None and reasoning_effort not in _REASONING_EFFORTS:
            raise ValueError("reasoning_effort is unsupported")
        self._reasoning_effort: ReasoningEffort = reasoning_effort
        self._engine = engine or AgentsSDKEngine()

    def _validate_tools(self, request: ModelRequest) -> None:
        disabled = tuple(
            tool.kind.value
            for tool in request.tools
            if tool.kind is not ModelToolKind.FUNCTION
        )
        if disabled:
            names = ", ".join(disabled)
            raise UnsupportedModelCapabilityError(
                f"disabled {self._provider_name} hosted tools requested: {names}"
            )

    def _invocation(
        self,
        request: ModelRequest,
        *,
        continuation: ModelContinuation | None = None,
        decisions: tuple[ApprovalDecision, ...] = (),
    ) -> OpenAIInvocation:
        self._validate_tools(request)
        return OpenAIInvocation(
            request=request,
            model_id=self._model_id,
            api_key=self._api_key,
            project_id=self._project_id,
            base_url=self._base_url,
            provider_id=self._provider_id,
            use_responses=self._use_responses,
            reasoning_effort=self._reasoning_effort,
            continuation=continuation,
            decisions=decisions,
        )

    async def run(self, request: ModelRequest) -> ModelResult:
        """Execute an initial request without exposing SDK types."""
        return await self._engine.run(self._invocation(request))

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Stream provider-neutral events with the same enforced settings."""
        return self._engine.stream(self._invocation(request))

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        """Resume only continuation state owned by this provider."""
        if request.continuation.provider != self._provider_id:
            raise ValueError(f"continuation provider must be {self._provider_id}")
        invocation = self._invocation(
            request.request,
            continuation=request.continuation,
            decisions=request.decisions,
        )
        return await self._engine.resume(invocation)


class OpenAIAgentsModel(OpenAICompatibleAgentsModel):
    """OpenAI adapter preserving the required project-isolation contract."""

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        project_id: str,
        engine: OpenAIEngine | None = None,
        reasoning_effort: ReasoningEffort = None,
    ) -> None:
        if cast(object, project_id) is None:
            raise ValueError("project_id is required for the OpenAI provider")
        super().__init__(
            model_id=model_id,
            api_key=api_key,
            engine=engine,
            reasoning_effort=reasoning_effort,
        )
        self._project_id = normalized_text(project_id, field="project_id")


__all__ = [
    "AgentsSDKEngine",
    "ModelToolInvoker",
    "OpenAIAgentsModel",
    "OpenAIEngine",
    "OpenAIInvocation",
    "ReasoningEffort",
]
