"""Sanitized, non-authoritative Agent presentation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol, cast

from ditto_agent.contracts._validation import (
    enum_value,
    nonnegative_decimal,
    normalized_text,
    positive_int,
    sha256_hex,
    utc_datetime,
)
from ditto_agent.contracts.runtime import RunStatus

AgentGuardrailStatus = Literal["passed", "blocked", "unknown"]


class AgentPresentationError(RuntimeError):
    """A presentation projection could not be authenticated or persisted."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class AgentPresentationConflict(AgentPresentationError):
    """A projection write violates monotonic versioning."""


def _optional_text(value: str | None, *, field: str, maximum: int = 512) -> str | None:
    return (
        None if value is None else normalized_text(value, field=field, maximum=maximum)
    )


def _text_tuple(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    if not isinstance(cast(object, values), tuple):
        raise TypeError(f"{field} must be a tuple")
    normalized = tuple(
        normalized_text(value, field=f"{field} item") for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _nonnegative_int(value: int, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class AgentContextPresentation:
    """Stable product context attached by the host at run creation."""

    context_type: str
    context_id: str

    def __post_init__(self) -> None:
        """Normalize both bounded context identity fields."""
        object.__setattr__(
            self,
            "context_type",
            normalized_text(self.context_type, field="context_type", maximum=128),
        )
        object.__setattr__(
            self,
            "context_id",
            normalized_text(self.context_id, field="context_id", maximum=1024),
        )


@dataclass(frozen=True, slots=True)
class AgentToolPresentation:
    """Redacted tool record containing identities and authenticated references only."""

    call_id: str
    tool_name: str
    arguments_hash: str
    result_hash: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate redacted hashes, identities, and public references."""
        object.__setattr__(
            self, "call_id", normalized_text(self.call_id, field="call_id")
        )
        object.__setattr__(
            self, "tool_name", normalized_text(self.tool_name, field="tool_name")
        )
        object.__setattr__(
            self,
            "arguments_hash",
            sha256_hex(self.arguments_hash, field="arguments_hash"),
        )
        object.__setattr__(
            self,
            "result_hash",
            sha256_hex(self.result_hash, field="result_hash"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _text_tuple(self.evidence_refs, field="tool evidence_refs"),
        )
        object.__setattr__(
            self,
            "artifact_refs",
            _text_tuple(self.artifact_refs, field="tool artifact_refs"),
        )


@dataclass(frozen=True, slots=True)
class AgentGuardrailPresentation:
    """Bounded public guardrail outcome without internal policy content."""

    status: AgentGuardrailStatus
    reason_code: str | None

    def __post_init__(self) -> None:
        """Validate the closed guardrail state and blocking reason."""
        if self.status not in {"passed", "blocked", "unknown"}:
            raise ValueError("guardrail status is invalid")
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field="guardrail reason_code"),
        )
        if self.status == "blocked" and self.reason_code is None:
            raise ValueError("blocked guardrail requires a reason_code")


@dataclass(frozen=True, slots=True)
class AgentUsagePresentation:
    """Non-sensitive bounded usage counters for one run."""

    model_attempts: int
    model_turns: int
    tool_calls: int
    retries: int
    total_tokens: int
    model_spend_usd: Decimal
    exhausted_reason: str | None

    def __post_init__(self) -> None:
        """Validate bounded counters, spend, and optional stop reason."""
        for field_name in (
            "model_attempts",
            "model_turns",
            "tool_calls",
            "retries",
            "total_tokens",
        ):
            _nonnegative_int(getattr(self, field_name), field=field_name)
        nonnegative_decimal(self.model_spend_usd, field="model_spend_usd")
        object.__setattr__(
            self,
            "exhausted_reason",
            _optional_text(self.exhausted_reason, field="exhausted_reason"),
        )


@dataclass(frozen=True, slots=True)
class AgentRunPresentation:
    """Versioned readable projection; never an execution authority source."""

    run_id: str
    objective: str
    context: AgentContextPresentation | None
    status: RunStatus
    output_summary: str | None
    tool_records: tuple[AgentToolPresentation, ...]
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    guardrail: AgentGuardrailPresentation
    usage: AgentUsagePresentation | None
    failure_code: str | None
    projection_version: int
    updated_at: datetime
    event_cursor: int = 0

    def __post_init__(self) -> None:
        """Normalize and validate the complete sanitized projection."""
        object.__setattr__(self, "run_id", normalized_text(self.run_id, field="run_id"))
        object.__setattr__(
            self,
            "objective",
            normalized_text(self.objective, field="objective", maximum=4096),
        )
        raw_context = cast(object, self.context)
        if raw_context is not None and not isinstance(
            raw_context, AgentContextPresentation
        ):
            raise TypeError("context must be an AgentContextPresentation")
        enum_value(self.status, RunStatus, field="status")
        object.__setattr__(
            self,
            "output_summary",
            _optional_text(self.output_summary, field="output_summary", maximum=8192),
        )
        raw_tool_records = cast(object, self.tool_records)
        if not isinstance(raw_tool_records, tuple) or not all(
            isinstance(record, AgentToolPresentation)
            for record in cast(tuple[object, ...], raw_tool_records)
        ):
            raise TypeError("tool_records must be AgentToolPresentation values")
        if len({record.call_id for record in self.tool_records}) != len(
            self.tool_records
        ):
            raise ValueError("tool_records call_id values must be unique")
        object.__setattr__(
            self,
            "evidence_refs",
            _text_tuple(self.evidence_refs, field="evidence_refs"),
        )
        object.__setattr__(
            self,
            "artifact_refs",
            _text_tuple(self.artifact_refs, field="artifact_refs"),
        )
        if not isinstance(cast(object, self.guardrail), AgentGuardrailPresentation):
            raise TypeError("guardrail must be an AgentGuardrailPresentation")
        raw_usage = cast(object, self.usage)
        if raw_usage is not None and not isinstance(raw_usage, AgentUsagePresentation):
            raise TypeError("usage must be an AgentUsagePresentation")
        object.__setattr__(
            self,
            "failure_code",
            _optional_text(self.failure_code, field="failure_code"),
        )
        positive_int(self.projection_version, field="projection_version")
        object.__setattr__(
            self, "updated_at", utc_datetime(self.updated_at, field="updated_at")
        )
        _nonnegative_int(self.event_cursor, field="event_cursor")


@dataclass(frozen=True, slots=True)
class AgentRunPresentationUpdate:
    """Outcome-derived projection content without persistence version authority."""

    run_id: str
    objective: str
    context: AgentContextPresentation | None
    status: RunStatus
    output_summary: str | None
    tool_records: tuple[AgentToolPresentation, ...]
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    guardrail: AgentGuardrailPresentation
    usage: AgentUsagePresentation | None
    failure_code: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        """Validate content before persistence assigns its version."""
        validated = AgentRunPresentation(
            run_id=self.run_id,
            objective=self.objective,
            context=self.context,
            status=self.status,
            output_summary=self.output_summary,
            tool_records=self.tool_records,
            evidence_refs=self.evidence_refs,
            artifact_refs=self.artifact_refs,
            guardrail=self.guardrail,
            usage=self.usage,
            failure_code=self.failure_code,
            projection_version=1,
            updated_at=self.updated_at,
        )
        for field_name in self.__dataclass_fields__:
            object.__setattr__(self, field_name, getattr(validated, field_name))


class AgentPresentationSink(Protocol):
    """Non-authoritative outcome publication boundary."""

    def publish(self, update: AgentRunPresentationUpdate) -> None:
        """Publish sanitized content after orchestration has determined its outcome."""
        ...


__all__ = [
    "AgentContextPresentation",
    "AgentGuardrailPresentation",
    "AgentGuardrailStatus",
    "AgentPresentationConflict",
    "AgentPresentationError",
    "AgentPresentationSink",
    "AgentRunPresentation",
    "AgentRunPresentationUpdate",
    "AgentToolPresentation",
    "AgentUsagePresentation",
]
