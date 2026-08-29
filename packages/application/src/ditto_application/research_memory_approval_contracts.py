"""Pure Application leaf contracts for research-memory approval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol, cast

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import canonical_request_hash

CAMPAIGN_RECORD_RESEARCH_MEMORY = "campaign_record_research_memory"
RESEARCH_MEMORY_PROMOTE = "research_memory_promote"
RESEARCH_MEMORY_REVOKE = "research_memory_revoke"
_SHA256_HEX_LENGTH = 64


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return text


def _utc(value: object, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in mapping.items()}
        )
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return tuple(_deep_freeze(item) for item in cast("Sequence[object]", value))
    return value


@dataclass(frozen=True, slots=True)
class ResearchMemoryApprovalCheck:
    """Exact mutation intent resolved by the durable approval authority."""

    run_id: str
    episode_id: str
    call_id: str
    tool_name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        """Normalize identities and deeply freeze canonical JSON arguments."""
        for field_name in ("run_id", "episode_id", "call_id", "tool_name"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        if self.episode_id != f"episode-{self.run_id}":
            raise ValueError("episode_id must be bound to run_id")
        canonical_request_hash(self.arguments)
        object.__setattr__(
            self,
            "arguments",
            cast("Mapping[str, object]", _deep_freeze(self.arguments)),
        )

    @property
    def arguments_hash(self) -> str:
        """Return the exact argument identity verified at the write boundary."""
        return canonical_request_hash(self.arguments)

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete approval lookup identity."""
        return {
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
        }


@dataclass(frozen=True, slots=True)
class VerifiedResearchMemoryApproval:
    """Verifier-issued proof for one exact promote or revoke action."""

    approval_id: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    expires_at: datetime
    approved: bool
    run_id: str
    episode_id: str
    call_id: str
    tool_name: str
    arguments_hash: str
    verification_hash: str

    def __post_init__(self) -> None:
        """Validate fields without trusting the self-hash."""
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
                _text(getattr(self, field_name), field_name),
            )
        for field_name in ("action_hash", "arguments_hash", "verification_hash"):
            object.__setattr__(
                self,
                field_name,
                _hash(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "approved_at", _utc(self.approved_at, "approved_at"))
        object.__setattr__(self, "expires_at", _utc(self.expires_at, "expires_at"))
        if self.expires_at <= self.approved_at or type(self.approved) is not bool:
            raise ValueError("research memory approval interval is invalid")

    @classmethod
    def issue(
        cls,
        *,
        check: ResearchMemoryApprovalCheck,
        approval_id: str,
        action_hash: str,
        operator_id: str,
        approved_at: datetime,
        expires_at: datetime,
        approved: bool,
    ) -> VerifiedResearchMemoryApproval:
        """Issue one integrity-bound verifier result."""
        proof = cls(
            approval_id=approval_id,
            action_hash=action_hash,
            operator_id=operator_id,
            approved_at=approved_at,
            expires_at=expires_at,
            approved=approved,
            run_id=check.run_id,
            episode_id=check.episode_id,
            call_id=check.call_id,
            tool_name=check.tool_name,
            arguments_hash=check.arguments_hash,
            verification_hash="0" * _SHA256_HEX_LENGTH,
        )
        return replace(
            proof,
            verification_hash=canonical_request_hash(proof.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every field covered by the verifier receipt hash."""
        return {
            "schema_version": 1,
            "kind": "verified_research_memory_approval",
            "approval_id": self.approval_id,
            "action_hash": self.action_hash,
            "operator_id": self.operator_id,
            "approved_at": _utc_text(self.approved_at),
            "expires_at": _utc_text(self.expires_at),
            "approved": self.approved,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
        }

    def verify_integrity(self) -> bool:
        """Detect proof mutation after verifier issuance."""
        return (
            canonical_request_hash(self.canonical_payload()) == self.verification_hash
        )

    def matches(self, check: ResearchMemoryApprovalCheck) -> bool:
        """Bind the proof to the current exact tool call."""
        return (
            self.run_id == check.run_id
            and self.episode_id == check.episode_id
            and self.call_id == check.call_id
            and self.tool_name == check.tool_name
            and self.arguments_hash == check.arguments_hash
        )


class ResearchMemoryApprovalVerifier(Protocol):
    """Port implemented by a durable operator-approval authority."""

    def verify(
        self,
        check: ResearchMemoryApprovalCheck,
    ) -> VerifiedResearchMemoryApproval:
        """Resolve the current exact approval decision."""
        ...


class DisabledResearchMemoryApprovalVerifier:
    """Reject memory mutations until an enabled host profile overrides it."""

    def verify(
        self,
        check: ResearchMemoryApprovalCheck,
    ) -> VerifiedResearchMemoryApproval:
        """Fail closed without constructing a synthetic approval receipt."""
        raise AppCommandError(
            f"research memory approval is unavailable for {check.tool_name}",
            details={
                "code": "RESEARCH_MEMORY_APPROVAL_UNAVAILABLE",
                "reason": "agent_feature_disabled",
            },
        )


__all__ = [
    "CAMPAIGN_RECORD_RESEARCH_MEMORY",
    "RESEARCH_MEMORY_PROMOTE",
    "RESEARCH_MEMORY_REVOKE",
    "DisabledResearchMemoryApprovalVerifier",
    "ResearchMemoryApprovalCheck",
    "ResearchMemoryApprovalVerifier",
    "VerifiedResearchMemoryApproval",
]
