"""Deterministic scripted model provider used by tests and offline defaults."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from threading import Lock

from ditto_agent._canonical import canonical_bytes
from ditto_agent.contracts._validation import enum_value, normalized_text
from ditto_agent.models.port import (
    ModelFailureKind,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolInvoker,
    ResumeModelRequest,
)


@dataclass(frozen=True, slots=True)
class ScriptedOutcome:
    """One deterministic response and optional text stream segmentation."""

    result: ModelResult
    stream_deltas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate every scripted text segment."""
        for delta in self.stream_deltas:
            _ = ModelStreamEvent(
                kind=ModelStreamEventKind.TEXT_DELTA,
                text_delta=delta,
            )


@dataclass(frozen=True, slots=True)
class ScriptedFailure:
    """One deterministic typed failure."""

    kind: ModelFailureKind
    message: str

    def __post_init__(self) -> None:
        """Validate the failure family and safe message."""
        enum_value(self.kind, ModelFailureKind, field="kind")
        object.__setattr__(
            self,
            "message",
            normalized_text(self.message, field="message", maximum=4096),
        )


ScriptedStep = ScriptedOutcome | ScriptedFailure


class ScriptedAgentModel:
    """Thread-safe, zero-network provider that consumes one scripted step per call."""

    def __init__(
        self,
        *,
        script: tuple[ScriptedStep, ...] = (),
        tool_invoker: ModelToolInvoker | None = None,
    ) -> None:
        self._script = list(script)
        self._tool_invoker = tool_invoker
        self._lock = Lock()
        self.requests: list[ModelRequest | ResumeModelRequest] = []

    def _next(self, request: ModelRequest | ResumeModelRequest) -> ScriptedOutcome:
        with self._lock:
            self.requests.append(request)
            if not self._script:
                raise ModelProviderError("scripted model has no remaining outcomes")
            step = self._script.pop(0)
        if isinstance(step, ScriptedFailure):
            if step.kind is ModelFailureKind.TIMEOUT:
                raise TimeoutError(step.message)
            raise ModelProviderError(f"{step.kind.value}: {step.message}")
        return step

    async def _execute_tools(self, result: ModelResult) -> None:
        interrupted_call_ids = {
            interruption.call_id for interruption in result.interruptions
        }
        runnable_calls = tuple(
            call
            for call in result.tool_calls
            if call.call_id not in interrupted_call_ids
        )
        if self._tool_invoker is None:
            return
        for call in runnable_calls:
            await self._tool_invoker.invoke(
                call.tool_name,
                canonical_bytes(call.arguments).decode(),
                call_id=call.call_id,
            )

    async def run(self, request: ModelRequest) -> ModelResult:
        """Return the next scripted run result."""
        result = self._next(request).result
        await self._execute_tools(result)
        return result

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Yield scripted deltas followed by exactly one completed event."""
        outcome = self._next(request)
        await self._execute_tools(outcome.result)
        for delta in outcome.stream_deltas:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TEXT_DELTA,
                text_delta=delta,
            )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.COMPLETED,
            result=outcome.result,
        )

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        """Return the next scripted result after validating provider ownership."""
        if request.continuation.provider != "scripted":
            raise ValueError("continuation provider must be scripted")
        result = self._next(request).result
        await self._execute_tools(result)
        return result


__all__ = ["ScriptedAgentModel", "ScriptedFailure", "ScriptedOutcome"]
