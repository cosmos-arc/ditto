"""Pure consumer-owned contracts for Campaign-scoped Agent proposals."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol, cast

import orjson

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import canonical_request_hash

CAMPAIGN_PROPOSE_CANDIDATE = "campaign_propose_candidate"
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, *, field: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _utc(value: object, *, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        raw = cast("Mapping[object, object]", value)
        if not all(type(key) is str for key in raw):
            raise ValueError("proposal parameters must have string keys")
        return {cast("str", key): _plain_json(item) for key, item in raw.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_json(item) for item in cast("Sequence[object]", value)]
    return value


def _frozen_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("parameters must be a JSON object")
    raw_value = cast("Mapping[object, object]", value)
    try:
        decoded: object = orjson.loads(
            orjson.dumps(_plain_json(raw_value), option=orjson.OPT_SORT_KEYS)
        )
        canonical_request_hash(decoded)
    except (AppCommandError, orjson.JSONEncodeError) as exc:
        raise ValueError("parameters must be strict canonical JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("parameters must be a JSON object")
    raw = cast("dict[object, object]", decoded)
    if not all(type(key) is str for key in raw):
        raise ValueError("parameters must have string keys")
    return MappingProxyType(cast("dict[str, object]", raw))


def _hashes(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a sequence of sha256 digests")
    values = tuple(_hash(item, field=field) for item in cast("Sequence[object]", value))
    if not values or len(values) != len(set(values)):
        raise ValueError(f"{field} must contain unique sha256 digests")
    return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class CampaignCandidateProposalCommand:
    """One model proposal bound to host-only Campaign/run authority."""

    campaign_id: str
    authorization_id: str
    authorization_hash: str
    authority_hash: str
    run_id: str
    episode_id: str
    call_id: str
    parent_candidate_id: str
    parameters: Mapping[str, object]
    factor_code_hash: str | None
    model_code_hash: str | None
    data_requirement_hashes: Sequence[str]

    def __post_init__(self) -> None:
        """Freeze model content and validate host-injected identities."""
        for field_name in (
            "campaign_id",
            "authorization_id",
            "run_id",
            "episode_id",
            "call_id",
            "parent_candidate_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        if self.episode_id != f"episode-{self.run_id}":
            raise ValueError("episode_id must be bound to run_id")
        for field_name in ("authorization_hash", "authority_hash"):
            object.__setattr__(
                self,
                field_name,
                _hash(getattr(self, field_name), field=field_name),
            )
        for field_name in ("factor_code_hash", "model_code_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _hash(value, field=field_name))
        object.__setattr__(self, "parameters", _frozen_mapping(self.parameters))
        object.__setattr__(
            self,
            "data_requirement_hashes",
            _hashes(self.data_requirement_hashes, field="data_requirement_hashes"),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every proposal and host identity field for idempotency."""
        return {
            "schema_version": 1,
            "kind": "ditto_campaign_candidate_proposal",
            "campaign_id": self.campaign_id,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "authority_hash": self.authority_hash,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "parent_candidate_id": self.parent_candidate_id,
            "parameters": dict(self.parameters),
            "factor_code_hash": self.factor_code_hash,
            "model_code_hash": self.model_code_hash,
            "data_requirement_hashes": list(self.data_requirement_hashes),
        }

    @property
    def request_hash(self) -> str:
        """Return the stable exact-call identity used for replay."""
        return canonical_request_hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class CampaignCandidateReceipt:
    """Application-issued immutable receipt for one candidate proposal."""

    campaign_id: str
    authorization_hash: str
    request_hash: str
    candidate_id: str
    candidate_hash: str
    generation: int
    status: str
    event_id: str
    occurred_at: datetime
    receipt_hash: str

    def __post_init__(self) -> None:
        """Validate receipt fields without trusting the self-hash."""
        for field_name in ("campaign_id", "candidate_id", "status", "event_id"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "authorization_hash",
            "request_hash",
            "candidate_hash",
            "receipt_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                _hash(getattr(self, field_name), field=field_name),
            )
        if type(self.generation) is not int or self.generation <= 0:
            raise ValueError("generation must be a positive integer")
        object.__setattr__(
            self,
            "occurred_at",
            _utc(self.occurred_at, field="occurred_at"),
        )

    @classmethod
    def issue(
        cls,
        *,
        command: CampaignCandidateProposalCommand,
        candidate_id: str,
        candidate_hash: str,
        generation: int,
        status: str,
        event_id: str,
        occurred_at: datetime,
    ) -> CampaignCandidateReceipt:
        """Issue one receipt bound to the complete proposal request."""
        receipt = cls(
            campaign_id=command.campaign_id,
            authorization_hash=command.authorization_hash,
            request_hash=command.request_hash,
            candidate_id=candidate_id,
            candidate_hash=candidate_hash,
            generation=generation,
            status=status,
            event_id=event_id,
            occurred_at=occurred_at,
            receipt_hash="0" * 64,
        )
        return replace(
            receipt,
            receipt_hash=canonical_request_hash(receipt.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete receipt body covered by its digest."""
        return {
            "schema_version": 1,
            "kind": "ditto_campaign_candidate_receipt",
            "campaign_id": self.campaign_id,
            "authorization_hash": self.authorization_hash,
            "request_hash": self.request_hash,
            "candidate_id": self.candidate_id,
            "candidate_hash": self.candidate_hash,
            "generation": self.generation,
            "status": self.status,
            "event_id": self.event_id,
            "occurred_at": _utc_text(self.occurred_at),
        }

    def verify_integrity(self) -> bool:
        """Verify the application receipt after crossing the Agent boundary."""
        return canonical_request_hash(self.canonical_payload()) == self.receipt_hash


class AutonomousCampaignCommandPort(Protocol):
    """Narrow Campaign mutation port consumed by the Agent tool."""

    def propose_candidate(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        occurred_at: datetime,
    ) -> CampaignCandidateReceipt:
        """Commit or exactly replay one authorized candidate proposal."""
        ...


__all__ = [
    "CAMPAIGN_PROPOSE_CANDIDATE",
    "AutonomousCampaignCommandPort",
    "CampaignCandidateProposalCommand",
    "CampaignCandidateReceipt",
]
