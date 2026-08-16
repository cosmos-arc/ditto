"""Deterministic scripted model provider used by tests and offline defaults."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from threading import Lock

from ditto_agent.contracts._validation import enum_value, normalized_text
from ditto_agent.models.port import (
    ModelFailureKind,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventKind,
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

    def __init__(self, *, script: tuple[ScriptedStep, ...] = ()) -> None:
        self._script = list(script)
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

    async def run(self, request: ModelRequest) -> ModelResult:
        """Return the next scripted run result."""
        return self._next(request).result

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Yield scripted deltas followed by exactly one completed event."""
        outcome = self._next(request)
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
        return self._next(request).result


__all__ = ["ScriptedAgentModel", "ScriptedFailure", "ScriptedOutcome"]
