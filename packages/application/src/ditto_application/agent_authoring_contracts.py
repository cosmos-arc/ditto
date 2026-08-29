"""Pure application contracts for governed Agent authoring mutations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol, cast

import orjson

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_request_hash,
    mutation_event_id,
)

AUTHOR_SAVE_STRATEGY_DRAFT = "author_save_strategy_draft"
AUTHOR_SUBMIT_STRATEGY_REVIEW = "author_submit_strategy_review"
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_RECEIPT_KIND = "ditto_agent_authoring_command_receipt"


def _text(value: str, *, field: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return normalized


def _hash(value: str, *, field: str) -> str:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        raw = cast("Mapping[object, object]", value)
        return {str(key): _plain_json(item) for key, item in raw.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_plain_json(item) for item in sequence]
    return value


def _frozen_mapping(value: Mapping[str, object], *, field: str) -> Mapping[str, object]:
    try:
        canonical_request_hash(value)
        decoded: object = orjson.loads(
            orjson.dumps(_plain_json(value), option=orjson.OPT_SORT_KEYS)
        )
    except (AppCommandError, orjson.JSONEncodeError) as exc:
        raise ValueError(f"{field} must be canonical JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field} must be a JSON object")
    raw = cast("dict[object, object]", decoded)
    if not all(type(key) is str for key in raw):
        raise ValueError(f"{field} must have string keys")
    return MappingProxyType(cast("dict[str, object]", raw))


@dataclass(frozen=True, slots=True)
class AgentAuthoringApprovalCheck:
    """Exact host identity and arguments presented to the approval verifier."""

    run_id: str
    episode_id: str
    call_id: str
    tool_name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize host identities and freeze canonical arguments."""
        for field_name in ("run_id", "episode_id", "call_id", "tool_name"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        if self.episode_id != f"episode-{self.run_id}":
            raise ValueError("episode_id must be bound to run_id")
        object.__setattr__(
            self,
            "arguments",
            _frozen_mapping(self.arguments, field="arguments"),
        )

    @property
    def arguments_hash(self) -> str:
        """Return the exact canonical provider-argument digest."""
        return canonical_request_hash(self.arguments)

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete verifier input without raw argument bytes."""
        return {
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
        }


@dataclass(frozen=True, slots=True)
class VerifiedAgentAuthoringApproval:
    """Verifier-issued proof of one exact durable operator decision."""

    approval_id: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    approved: bool
    run_id: str
    episode_id: str
    call_id: str
    tool_name: str
    arguments_hash: str
    verification_hash: str

    def __post_init__(self) -> None:
        """Validate proof fields without trusting its self-hash."""
        if type(self.approved) is not bool:
            raise TypeError("approved must be a boolean")
        for field_name in (
            "approval_id",
            "operator_id",
            "run_id",
            "episode_id",
            "call_id",
            "tool_name",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self, "action_hash", _hash(self.action_hash, field="action_hash")
        )
        object.__setattr__(
            self,
            "arguments_hash",
            _hash(self.arguments_hash, field="arguments_hash"),
        )
        object.__setattr__(
            self,
            "verification_hash",
            _hash(self.verification_hash, field="verification_hash"),
        )
        object.__setattr__(
            self, "approved_at", _utc(self.approved_at, field="approved_at")
        )

    @classmethod
    def issue(
        cls,
        *,
        check: AgentAuthoringApprovalCheck,
        approval_id: str,
        action_hash: str,
        operator_id: str,
        approved_at: datetime,
        approved: bool,
    ) -> VerifiedAgentAuthoringApproval:
        """Issue one verifier-owned proof for an exact approval check."""
        proof = cls(
            approval_id=approval_id,
            action_hash=action_hash,
            operator_id=operator_id,
            approved_at=approved_at,
            approved=approved,
            run_id=check.run_id,
            episode_id=check.episode_id,
            call_id=check.call_id,
            tool_name=check.tool_name,
            arguments_hash=check.arguments_hash,
            verification_hash="0" * 64,
        )
        return replace(
            proof,
            verification_hash=canonical_request_hash(proof.canonical_payload()),
        )

    @property
    def audit_identity(self) -> str:
        """Return the stable approval identity embedded in governance audit."""
        return f"agent-approval:{self.approval_id}"

    def canonical_payload(self) -> dict[str, object]:
        """Return every proof field covered by the verification hash."""
        return {
            "schema_version": 1,
            "kind": "ditto_verified_agent_authoring_approval",
            "approval_id": self.approval_id,
            "action_hash": self.action_hash,
            "operator_id": self.operator_id,
            "approved_at": _utc_text(self.approved_at),
            "approved": self.approved,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
            "audit_identity": self.audit_identity,
        }

    def verify_integrity(self) -> bool:
        """Verify the proof's self-hash after transport."""
        return (
            canonical_request_hash(self.canonical_payload()) == self.verification_hash
        )

    def matches(self, check: AgentAuthoringApprovalCheck) -> bool:
        """Require the proof to identify the exact current tool call."""
        return (
            self.run_id == check.run_id
            and self.episode_id == check.episode_id
            and self.call_id == check.call_id
            and self.tool_name == check.tool_name
            and self.arguments_hash == check.arguments_hash
        )


class AgentAuthoringApprovalVerifier(Protocol):
    """Consumer-owned port implemented by the durable Agent approval plane."""

    def verify(
        self,
        check: AgentAuthoringApprovalCheck,
    ) -> VerifiedAgentAuthoringApproval:
        """Resolve and revalidate the current operator decision."""
        ...


@dataclass(frozen=True, slots=True)
class AgentSaveStrategyDraftCommand:
    """Save a new or exact-base-derived immutable strategy draft."""

    strategy_id: str
    name: str
    spec_json: Mapping[str, object]
    base_version: int | None
    tags: tuple[str, ...]
    run_id: str
    episode_id: str
    call_id: str


@dataclass(frozen=True, slots=True)
class AgentSubmitStrategyReviewCommand:
    """Submit one exact draft version to the existing review gate."""

    strategy_id: str
    version: int
    bundle_hash: str
    reason: str
    run_id: str
    episode_id: str
    call_id: str


@dataclass(frozen=True, slots=True)
class AgentAuthoringCommandReceipt:
    """Evidence-safe receipt binding mutation, approval, run, and audit identity."""

    operation_id: str
    resource_id: str
    result_identity: str
    result: Mapping[str, object]
    approval_id: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    run_id: str
    episode_id: str
    audit_identity: str
    audit_event_id: str
    key_hash: str
    request_hash: str
    receipt_hash: str

    def __post_init__(self) -> None:
        """Normalize receipt identities and freeze the result payload."""
        for field_name in (
            "operation_id",
            "resource_id",
            "result_identity",
            "approval_id",
            "operator_id",
            "run_id",
            "episode_id",
            "audit_identity",
            "audit_event_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        for field_name in ("action_hash", "key_hash", "request_hash", "receipt_hash"):
            object.__setattr__(
                self,
                field_name,
                _hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self, "approved_at", _utc(self.approved_at, field="approved_at")
        )
        object.__setattr__(
            self,
            "result",
            _frozen_mapping(self.result, field="result"),
        )

    @classmethod
    def issue(
        cls,
        *,
        identity: MutationIdempotency,
        approval: VerifiedAgentAuthoringApproval,
        result_identity: str,
        result: Mapping[str, object],
    ) -> AgentAuthoringCommandReceipt:
        """Issue one receipt from verified approval and mutation identities."""
        receipt = cls(
            operation_id=identity.operation_id,
            resource_id=identity.resource_id,
            result_identity=result_identity,
            result=result,
            approval_id=approval.approval_id,
            action_hash=approval.action_hash,
            operator_id=approval.operator_id,
            approved_at=approval.approved_at,
            run_id=approval.run_id,
            episode_id=approval.episode_id,
            audit_identity=approval.audit_identity,
            audit_event_id=mutation_event_id(identity),
            key_hash=identity.key_hash,
            request_hash=identity.request_hash,
            receipt_hash="0" * 64,
        )
        return replace(
            receipt,
            receipt_hash=canonical_request_hash(receipt.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every evidence and replay identity covered by the hash."""
        return {
            "schema_version": 1,
            "kind": _RECEIPT_KIND,
            "operation_id": self.operation_id,
            "resource_id": self.resource_id,
            "result_identity": self.result_identity,
            "result": self.result,
            "approval_id": self.approval_id,
            "action_hash": self.action_hash,
            "operator_id": self.operator_id,
            "approved_at": _utc_text(self.approved_at),
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "audit_identity": self.audit_identity,
            "audit_event_id": self.audit_event_id,
            "key_hash": self.key_hash,
            "request_hash": self.request_hash,
        }

    def verify_integrity(self) -> bool:
        """Verify that no receipt identity or result changed."""
        return canonical_request_hash(self.canonical_payload()) == self.receipt_hash


class AgentAuthoringCommandPort(Protocol):
    """Leaf application command surface consumed by Agent write tools."""

    def save_strategy_draft(
        self,
        command: AgentSaveStrategyDraftCommand,
    ) -> AgentAuthoringCommandReceipt:
        """Save one approved draft and return its command receipt."""
        ...

    def submit_strategy_review(
        self,
        command: AgentSubmitStrategyReviewCommand,
    ) -> AgentAuthoringCommandReceipt:
        """Submit one approved draft to review and return its receipt."""
        ...


__all__ = [
    "AUTHOR_SAVE_STRATEGY_DRAFT",
    "AUTHOR_SUBMIT_STRATEGY_REVIEW",
    "AgentAuthoringApprovalCheck",
    "AgentAuthoringApprovalVerifier",
    "AgentAuthoringCommandPort",
    "AgentAuthoringCommandReceipt",
    "AgentSaveStrategyDraftCommand",
    "AgentSubmitStrategyReviewCommand",
    "VerifiedAgentAuthoringApproval",
]
