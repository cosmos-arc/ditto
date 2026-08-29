"""Strict canonical codec for durable approval continuation state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

import orjson

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.approval_errors import ApprovalRuntimeViolation
from ditto_agent.contracts.approval import (
    ActionBudget,
    ApprovalAction,
    ApprovalRequest,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelContinuation, ModelRequest

MAX_CONTINUATION_BYTES = 8 * 1024 * 1024
_SCHEMA_VERSION = 1
_SHA256_HEX_LENGTH = 64
_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "cookie",
        "password",
        "secret",
    }
)


@dataclass(frozen=True, slots=True)
class ModelRequestIdentity:
    """Hashes and bounded scalars that bind persisted state to one request."""

    run_id: str
    agent_name: str
    instructions_hash: str
    input_hash: str
    max_turns: int
    max_output_tokens: int
    tool_schema_hash: str

    @classmethod
    def from_request(cls, request: ModelRequest) -> ModelRequestIdentity:
        """Derive a secret-free identity from one immutable model request."""
        return cls(
            run_id=request.run_id,
            agent_name=request.agent_name,
            instructions_hash=canonical_sha256(request.instructions),
            input_hash=canonical_sha256(request.input_text),
            max_turns=request.max_turns,
            max_output_tokens=request.max_output_tokens,
            tool_schema_hash=canonical_sha256(request.tools),
        )

    def payload(self) -> dict[str, object]:
        """Return the canonical JSON-ready identity payload."""
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "instructions_hash": self.instructions_hash,
            "input_hash": self.input_hash,
            "max_turns": self.max_turns,
            "max_output_tokens": self.max_output_tokens,
            "tool_schema_hash": self.tool_schema_hash,
        }


@dataclass(frozen=True, slots=True)
class InterruptionBinding:
    """Immutable identity binding between an SDK call and an approval."""

    call_id: str
    tool_name: str
    arguments_hash: str
    request_id: str
    action_hash: str

    def payload(self) -> dict[str, object]:
        """Return the canonical JSON-ready interruption binding."""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
            "request_id": self.request_id,
            "action_hash": self.action_hash,
        }


@dataclass(frozen=True, slots=True)
class ResumeEnvelope:
    """Versioned provider continuation and its exact approval bindings."""

    run_id: str
    request_identity: ModelRequestIdentity
    continuation: ModelContinuation
    interruptions: tuple[InterruptionBinding, ...]

    def payload(self) -> dict[str, object]:
        """Return the versioned canonical envelope payload."""
        return {
            "schema_version": _SCHEMA_VERSION,
            "run_id": self.run_id,
            "request_identity": self.request_identity.payload(),
            "continuation": {
                "provider": self.continuation.provider,
                "payload": self.continuation.payload,
            },
            "interruptions": tuple(item.payload() for item in self.interruptions),
        }


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ApprovalRuntimeViolation(
            f"{field} must be a JSON object",
            reason_code="agent_continuation_invalid",
        )
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise ApprovalRuntimeViolation(
            f"{field} must be a JSON object",
            reason_code="agent_continuation_invalid",
        )
    return cast(Mapping[str, object], mapping)


def _exact_keys(
    value: Mapping[str, object], *, expected: frozenset[str], field: str
) -> None:
    if frozenset(value) != expected:
        raise ApprovalRuntimeViolation(
            f"{field} has an unexpected schema",
            reason_code="agent_continuation_invalid",
        )


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ApprovalRuntimeViolation(
            f"{field} must be non-empty text",
            reason_code="agent_continuation_invalid",
        )
    return value


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApprovalRuntimeViolation(
            f"{field} must be a positive integer",
            reason_code="agent_continuation_invalid",
        )
    return value


def _datetime(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovalRuntimeViolation(
            f"{field} must be an ISO datetime",
            reason_code="agent_approval_action_invalid",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApprovalRuntimeViolation(
            f"{field} must be offset-aware",
            reason_code="agent_approval_action_invalid",
        )
    return parsed


def _sha256(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ApprovalRuntimeViolation(
            f"{field} must be a lowercase SHA-256 digest",
            reason_code="agent_continuation_invalid",
        )
    return text


def reject_sensitive_keys(value: object, *, path: str = "continuation") -> None:
    """Reject credentials and secrets recursively before persistence."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for raw_key, item in mapping.items():
            if not isinstance(raw_key, str):
                raise ApprovalRuntimeViolation(
                    f"{path} contains a non-text key",
                    reason_code="agent_continuation_invalid",
                )
            normalized = raw_key.lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                raise ApprovalRuntimeViolation(
                    f"{path} contains forbidden sensitive state",
                    reason_code="agent_continuation_sensitive",
                )
            reject_sensitive_keys(item, path=f"{path}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        for index, item in enumerate(sequence):
            reject_sensitive_keys(item, path=f"{path}[{index}]")


def _decode_request_identity(value: object) -> ModelRequestIdentity:
    payload = _mapping(value, field="request_identity")
    _exact_keys(
        payload,
        expected=frozenset(
            {
                "run_id",
                "agent_name",
                "instructions_hash",
                "input_hash",
                "max_turns",
                "max_output_tokens",
                "tool_schema_hash",
            }
        ),
        field="request_identity",
    )
    return ModelRequestIdentity(
        run_id=_text(payload["run_id"], field="request_identity.run_id"),
        agent_name=_text(payload["agent_name"], field="request_identity.agent_name"),
        instructions_hash=_sha256(
            payload["instructions_hash"],
            field="request_identity.instructions_hash",
        ),
        input_hash=_sha256(payload["input_hash"], field="request_identity.input_hash"),
        max_turns=_integer(payload["max_turns"], field="request_identity.max_turns"),
        max_output_tokens=_integer(
            payload["max_output_tokens"],
            field="request_identity.max_output_tokens",
        ),
        tool_schema_hash=_sha256(
            payload["tool_schema_hash"],
            field="request_identity.tool_schema_hash",
        ),
    )


def _decode_binding(value: object) -> InterruptionBinding:
    payload = _mapping(value, field="interruption binding")
    _exact_keys(
        payload,
        expected=frozenset(
            {
                "call_id",
                "tool_name",
                "arguments_hash",
                "request_id",
                "action_hash",
            }
        ),
        field="interruption binding",
    )
    return InterruptionBinding(
        call_id=_text(payload["call_id"], field="binding.call_id"),
        tool_name=_text(payload["tool_name"], field="binding.tool_name"),
        arguments_hash=_sha256(
            payload["arguments_hash"], field="binding.arguments_hash"
        ),
        request_id=_text(payload["request_id"], field="binding.request_id"),
        action_hash=_sha256(payload["action_hash"], field="binding.action_hash"),
    )


def decode_envelope(payload_json: bytes) -> ResumeEnvelope:
    """Decode and authenticate one canonical continuation envelope."""
    if not payload_json or len(payload_json) > MAX_CONTINUATION_BYTES:
        raise ApprovalRuntimeViolation(
            "continuation size is outside the approved bound",
            reason_code="agent_continuation_invalid",
        )
    try:
        decoded = orjson.loads(payload_json)
    except orjson.JSONDecodeError as exc:
        raise ApprovalRuntimeViolation(
            "continuation is not valid JSON",
            reason_code="agent_continuation_invalid",
        ) from exc
    if canonical_bytes(decoded) != payload_json:
        raise ApprovalRuntimeViolation(
            "continuation is not canonical JSON",
            reason_code="agent_continuation_invalid",
        )
    payload = _mapping(decoded, field="continuation envelope")
    _exact_keys(
        payload,
        expected=frozenset(
            {
                "schema_version",
                "run_id",
                "request_identity",
                "continuation",
                "interruptions",
            }
        ),
        field="continuation envelope",
    )
    if payload["schema_version"] != _SCHEMA_VERSION:
        raise ApprovalRuntimeViolation(
            "continuation schema version is unsupported",
            reason_code="agent_continuation_version_unsupported",
        )
    continuation_payload = _mapping(payload["continuation"], field="continuation")
    _exact_keys(
        continuation_payload,
        expected=frozenset({"provider", "payload"}),
        field="continuation",
    )
    provider_payload = _mapping(
        continuation_payload["payload"], field="continuation.payload"
    )
    reject_sensitive_keys(provider_payload)
    raw_bindings = payload["interruptions"]
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ApprovalRuntimeViolation(
            "continuation must bind at least one interruption",
            reason_code="agent_continuation_invalid",
        )
    binding_values = cast(list[object], raw_bindings)
    bindings = tuple(_decode_binding(item) for item in binding_values)
    if len({item.call_id for item in bindings}) != len(bindings):
        raise ApprovalRuntimeViolation(
            "continuation interruption call IDs must be unique",
            reason_code="agent_continuation_invalid",
        )
    if len({item.request_id for item in bindings}) != len(bindings):
        raise ApprovalRuntimeViolation(
            "continuation approval request IDs must be unique",
            reason_code="agent_continuation_invalid",
        )
    return ResumeEnvelope(
        run_id=_text(payload["run_id"], field="continuation run_id"),
        request_identity=_decode_request_identity(payload["request_identity"]),
        continuation=ModelContinuation(
            provider=_text(
                continuation_payload["provider"], field="continuation provider"
            ),
            payload=provider_payload,
        ),
        interruptions=bindings,
    )


def decode_action_payload(payload_json: bytes) -> ApprovalRequest:
    """Decode one canonical approval action and recompute its action hash."""
    try:
        decoded = orjson.loads(payload_json)
    except orjson.JSONDecodeError as exc:
        raise ApprovalRuntimeViolation(
            "approval action is not valid JSON",
            reason_code="agent_approval_action_invalid",
        ) from exc
    if canonical_bytes(decoded) != payload_json:
        raise ApprovalRuntimeViolation(
            "approval action is not canonical JSON",
            reason_code="agent_approval_action_invalid",
        )
    payload = _mapping(decoded, field="approval action")
    _exact_keys(
        payload,
        expected=frozenset(
            {
                "request_id",
                "run_id",
                "action_kind",
                "tool_name",
                "parameters",
                "subject_identity",
                "required_authority",
                "authority_hash",
                "temporal_context",
                "budget",
                "expires_at",
            }
        ),
        field="approval action",
    )
    context = _mapping(payload["temporal_context"], field="temporal_context")
    _exact_keys(
        context,
        expected=frozenset(
            {
                "decision_time",
                "knowledge_cutoff",
                "publication_cutoff",
                "source_snapshot_id",
                "execution_eligible_at",
                "allowed_universe",
                "license_class",
                "egress_class",
                "campaign_authorization_id",
                "campaign_authority_hash",
            }
        ),
        field="temporal_context",
    )
    raw_universe = context["allowed_universe"]
    if not isinstance(raw_universe, list):
        raise ApprovalRuntimeViolation(
            "temporal_context.allowed_universe is invalid",
            reason_code="agent_approval_action_invalid",
        )
    universe_values = cast(list[object], raw_universe)
    if not all(isinstance(item, str) for item in universe_values):
        raise ApprovalRuntimeViolation(
            "temporal_context.allowed_universe is invalid",
            reason_code="agent_approval_action_invalid",
        )
    raw_execution = context["execution_eligible_at"]
    execution: datetime | Literal["not_applicable"]
    if raw_execution == "not_applicable":
        execution = "not_applicable"
    else:
        execution = _datetime(
            raw_execution, field="temporal_context.execution_eligible_at"
        )
    campaign_id = context["campaign_authorization_id"]
    campaign_hash = context["campaign_authority_hash"]
    if campaign_id is not None and not isinstance(campaign_id, str):
        raise ApprovalRuntimeViolation(
            "campaign authorization ID is invalid",
            reason_code="agent_approval_action_invalid",
        )
    if campaign_hash is not None and not isinstance(campaign_hash, str):
        raise ApprovalRuntimeViolation(
            "campaign authority hash is invalid",
            reason_code="agent_approval_action_invalid",
        )
    try:
        temporal_context = TemporalToolContext.from_host(
            TemporalContextInput(
                decision_time=_datetime(
                    context["decision_time"], field="temporal_context.decision_time"
                ),
                knowledge_cutoff=_datetime(
                    context["knowledge_cutoff"],
                    field="temporal_context.knowledge_cutoff",
                ),
                publication_cutoff=_datetime(
                    context["publication_cutoff"],
                    field="temporal_context.publication_cutoff",
                ),
                source_snapshot_id=_text(
                    context["source_snapshot_id"],
                    field="temporal_context.source_snapshot_id",
                ),
                execution_eligible_at=execution,
                allowed_universe=cast(tuple[str, ...], tuple(universe_values)),
                license_class=_text(
                    context["license_class"], field="temporal_context.license_class"
                ),
                egress_class=EgressClass(
                    _text(
                        context["egress_class"],
                        field="temporal_context.egress_class",
                    )
                ),
                campaign_authorization_id=campaign_id,
                campaign_authority_hash=campaign_hash,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ApprovalRuntimeViolation(
            "approval temporal context is invalid",
            reason_code="agent_approval_action_invalid",
        ) from exc
    budget = _mapping(payload["budget"], field="approval budget")
    _exact_keys(
        budget,
        expected=frozenset(
            {
                "max_tool_calls",
                "max_output_bytes",
                "max_model_tokens",
                "max_model_spend_usd",
            }
        ),
        field="approval budget",
    )
    parameters = _mapping(payload["parameters"], field="approval parameters")
    try:
        action = ApprovalAction(
            action_kind=_text(payload["action_kind"], field="action_kind"),
            tool_name=_text(payload["tool_name"], field="tool_name"),
            parameters=parameters,
            subject_identity=_text(
                payload["subject_identity"], field="subject_identity"
            ),
            required_authority=_text(
                payload["required_authority"], field="required_authority"
            ),
            authority_hash=_sha256(payload["authority_hash"], field="authority_hash"),
            temporal_context=temporal_context,
            budget=ActionBudget(
                max_tool_calls=_integer(
                    budget["max_tool_calls"], field="budget.max_tool_calls"
                ),
                max_output_bytes=_integer(
                    budget["max_output_bytes"], field="budget.max_output_bytes"
                ),
                max_model_tokens=_integer(
                    budget["max_model_tokens"], field="budget.max_model_tokens"
                ),
                max_model_spend_usd=Decimal(
                    _text(
                        budget["max_model_spend_usd"],
                        field="budget.max_model_spend_usd",
                    )
                ),
            ),
            expires_at=_datetime(payload["expires_at"], field="expires_at"),
        )
        return ApprovalRequest.issue(
            request_id=_text(payload["request_id"], field="request_id"),
            run_id=_text(payload["run_id"], field="run_id"),
            action=action,
        )
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ApprovalRuntimeViolation(
            "approval action contract is invalid",
            reason_code="agent_approval_action_invalid",
        ) from exc


__all__ = [
    "MAX_CONTINUATION_BYTES",
    "InterruptionBinding",
    "ModelRequestIdentity",
    "ResumeEnvelope",
    "decode_action_payload",
    "decode_envelope",
    "reject_sensitive_keys",
]
