"""SDK-independent model contracts consumed by the governed Agent runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast, runtime_checkable

from ditto_agent.contracts._validation import (
    enum_value,
    freeze_json,
    normalized_text,
    normalized_unique_tuple,
    positive_int,
)

_MAX_STREAM_DELTA_CHARS = 65_536


def _frozen_mapping(value: Mapping[str, object], *, field: str) -> Mapping[str, object]:
    frozen = freeze_json(value, field=field)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return cast(Mapping[str, object], frozen)


def _nonnegative_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


class ModelToolKind(StrEnum):
    """Tool capability classes visible at the provider boundary."""

    FUNCTION = "function"
    WEB_SEARCH = "web_search"
    FILE_SEARCH = "file_search"
    CODE_INTERPRETER = "code_interpreter"
    SHELL = "shell"
    COMPUTER = "computer"
    MCP = "mcp"


class ModelFailureKind(StrEnum):
    """Deterministic failure families exposed by scripted providers."""

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER = "provider"


class ModelStreamEventKind(StrEnum):
    """Stable semantic events emitted by model providers."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    COMPLETED = "completed"


class ModelOutputContract(StrEnum):
    """Provider-neutral structured outputs enforced before governed grounding."""

    GROUNDED_ANSWER = "grounded_answer"


@dataclass(frozen=True, slots=True)
class ModelToolSpec:
    """One explicitly registered tool definition."""

    kind: ModelToolKind
    name: str
    description: str
    input_schema: Mapping[str, object]
    requires_approval: bool

    def __post_init__(self) -> None:
        """Validate identity, schema, kind, and approval policy."""
        enum_value(self.kind, ModelToolKind, field="kind")
        object.__setattr__(self, "name", normalized_text(self.name, field="name"))
        object.__setattr__(
            self,
            "description",
            normalized_text(self.description, field="description", maximum=4096),
        )
        object.__setattr__(
            self,
            "input_schema",
            _frozen_mapping(self.input_schema, field="input_schema"),
        )


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """One bounded model execution request with no provider-specific types."""

    run_id: str
    agent_name: str
    instructions: str
    input_text: str
    max_turns: int
    max_output_tokens: int
    tools: tuple[ModelToolSpec, ...]
    required_tool_name: str | None = None
    output_contract: ModelOutputContract | None = None

    def __post_init__(self) -> None:
        """Validate bounded inputs and unique tool identities."""
        for field_name in ("run_id", "agent_name"):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "instructions",
            normalized_text(self.instructions, field="instructions", maximum=32_768),
        )
        object.__setattr__(
            self,
            "input_text",
            normalized_text(self.input_text, field="input_text", maximum=65_536),
        )
        positive_int(self.max_turns, field="max_turns")
        positive_int(self.max_output_tokens, field="max_output_tokens")
        tool_names = tuple(tool.name for tool in self.tools)
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("tools must have unique names")
        if self.required_tool_name is not None:
            required_tool_name = normalized_text(
                self.required_tool_name,
                field="required_tool_name",
            )
            if required_tool_name not in tool_names:
                raise ValueError("required_tool_name must identify a request tool")
            object.__setattr__(self, "required_tool_name", required_tool_name)
        if self.output_contract is not None:
            enum_value(
                self.output_contract,
                ModelOutputContract,
                field="output_contract",
            )


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Provider-neutral aggregate token usage."""

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int = -1

    def __post_init__(self) -> None:
        """Validate counters and derive the aggregate token count."""
        _nonnegative_int(self.requests, field="requests")
        _nonnegative_int(self.input_tokens, field="input_tokens")
        _nonnegative_int(self.output_tokens, field="output_tokens")
        expected = self.input_tokens + self.output_tokens
        if self.total_tokens == -1:
            object.__setattr__(self, "total_tokens", expected)
        elif self.total_tokens != expected:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    """Provider-neutral function tool intent."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize identity and deeply freeze arguments."""
        object.__setattr__(
            self, "call_id", normalized_text(self.call_id, field="call_id")
        )
        object.__setattr__(
            self, "tool_name", normalized_text(self.tool_name, field="tool_name")
        )
        object.__setattr__(
            self,
            "arguments",
            _frozen_mapping(self.arguments, field="arguments"),
        )


@dataclass(frozen=True, slots=True)
class ModelInterruption:
    """Function tool call awaiting a deterministic host decision."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize identity and deeply freeze arguments."""
        object.__setattr__(
            self, "call_id", normalized_text(self.call_id, field="call_id")
        )
        object.__setattr__(
            self, "tool_name", normalized_text(self.tool_name, field="tool_name")
        )
        object.__setattr__(
            self,
            "arguments",
            _frozen_mapping(self.arguments, field="arguments"),
        )


@dataclass(frozen=True, slots=True)
class ModelContinuation:
    """Locally persisted provider state required to resume an interruption."""

    provider: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize provider identity and freeze local state."""
        object.__setattr__(
            self, "provider", normalized_text(self.provider, field="provider")
        )
        object.__setattr__(
            self,
            "payload",
            _frozen_mapping(self.payload, field="payload"),
        )


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """One host decision applied to an exact interrupted call identity."""

    call_id: str
    approved: bool
    rejection_message: str | None = None

    def __post_init__(self) -> None:
        """Validate one exact allow or reject decision."""
        object.__setattr__(
            self, "call_id", normalized_text(self.call_id, field="call_id")
        )
        if self.approved and self.rejection_message is not None:
            raise ValueError("approved decisions cannot include a rejection_message")
        if self.rejection_message is not None:
            object.__setattr__(
                self,
                "rejection_message",
                normalized_text(
                    self.rejection_message,
                    field="rejection_message",
                    maximum=4096,
                ),
            )


@dataclass(frozen=True, slots=True)
class ResumeModelRequest:
    """Original request, local continuation, and exact approval decisions."""

    request: ModelRequest
    continuation: ModelContinuation
    decisions: tuple[ApprovalDecision, ...]

    def __post_init__(self) -> None:
        """Reject duplicate decisions for one interrupted call."""
        decision_ids = tuple(decision.call_id for decision in self.decisions)
        if decision_ids:
            normalized_unique_tuple(decision_ids, field="decision call ids")


ModelOutput = str | Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class ModelResult:
    """Typed terminal or interrupted provider result."""

    final_output: ModelOutput
    tool_calls: tuple[ModelToolCall, ...]
    usage: ModelUsage
    interruptions: tuple[ModelInterruption, ...]
    continuation: ModelContinuation | None

    def __post_init__(self) -> None:
        """Freeze structured output and enforce resumable interruption parity."""
        if isinstance(self.final_output, Mapping):
            object.__setattr__(
                self,
                "final_output",
                _frozen_mapping(self.final_output, field="final_output"),
            )
        interruption_ids = tuple(item.call_id for item in self.interruptions)
        if interruption_ids:
            normalized_unique_tuple(interruption_ids, field="interruption call ids")
        if bool(self.interruptions) != (self.continuation is not None):
            raise ValueError("interruptions and continuation must appear together")


@dataclass(frozen=True, slots=True)
class ModelStreamEvent:
    """One provider-neutral semantic stream event."""

    kind: ModelStreamEventKind
    text_delta: str | None = None
    tool_call: ModelToolCall | None = None
    result: ModelResult | None = None

    def __post_init__(self) -> None:
        """Validate the payload required by the declared event kind."""
        enum_value(self.kind, ModelStreamEventKind, field="kind")
        if self.kind is ModelStreamEventKind.TEXT_DELTA:
            if self.text_delta is None:
                raise ValueError("text_delta event requires text_delta")
            if not self.text_delta or len(self.text_delta) > _MAX_STREAM_DELTA_CHARS:
                raise ValueError("text_delta must contain 1 to 65,536 characters")
            if self.tool_call is not None or self.result is not None:
                raise ValueError("text_delta event cannot include other payloads")
        elif self.kind is ModelStreamEventKind.TOOL_CALL:
            if self.tool_call is None:
                raise ValueError("tool_call event requires tool_call")
            if self.text_delta is not None or self.result is not None:
                raise ValueError("tool_call event cannot include other payloads")
        else:
            if self.result is None:
                raise ValueError("completed event requires result")
            if self.text_delta is not None or self.tool_call is not None:
                raise ValueError("completed event cannot include other payloads")


class ModelProviderError(RuntimeError):
    """A typed provider-side failure safe to expose to the Agent runtime."""


class UnsupportedModelCapabilityError(ModelProviderError):
    """Raised before invocation when a disabled provider capability is requested."""


@runtime_checkable
class AgentModelPort(Protocol):
    """Minimal run, stream, and resume surface used by the Agent runtime."""

    async def run(self, request: ModelRequest) -> ModelResult:
        """Execute one bounded request."""
        ...

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Stream semantic events for one bounded request."""
        ...

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        """Resume one locally persisted interruption."""
        ...


class ModelToolInvoker(Protocol):
    """Deterministic host callback used by provider function tools."""

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        """Invoke one already admitted function tool identity."""
        ...


__all__ = [
    "AgentModelPort",
    "ApprovalDecision",
    "ModelContinuation",
    "ModelFailureKind",
    "ModelInterruption",
    "ModelOutputContract",
    "ModelProviderError",
    "ModelRequest",
    "ModelResult",
    "ModelStreamEvent",
    "ModelStreamEventKind",
    "ModelToolCall",
    "ModelToolInvoker",
    "ModelToolKind",
    "ModelToolSpec",
    "ModelUsage",
    "ResumeModelRequest",
    "UnsupportedModelCapabilityError",
]
