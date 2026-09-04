"""Opaque PIT context references consumed by the backtest replay boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

__all__ = [
    "ContextInputKind",
    "ReplayContextInputRef",
    "normalize_context_input_refs",
]

_SHA256_LENGTH = 64


class ContextInputKind(StrEnum):
    """Product evidence kinds that can influence a replayable backtest."""

    MARKET_CONTEXT = "market_context"
    TECHNICAL_ANALYSIS = "technical_analysis"


def _identity(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{field_name} must be a non-empty canonical identity")
    return value


def _hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("content_hash must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: object, *, field_name: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone aware")
    utc = parsed.astimezone(UTC)
    return utc.isoformat().replace("+00:00", "Z"), utc


@dataclass(frozen=True, slots=True)
class ReplayContextInputRef:
    """One immutable upstream market or technical evidence identity."""

    context_kind: ContextInputKind
    context_id: str
    content_hash: str
    as_of: str
    knowledge_cutoff: str
    publication_cutoff: str
    source_snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject ambiguous identity, future visibility, and erased snapshots."""
        if type(self.context_kind) is not ContextInputKind:
            raise ValueError("context_kind must be an exact ContextInputKind")
        object.__setattr__(
            self,
            "context_id",
            _identity(self.context_id, field_name="context_id"),
        )
        object.__setattr__(self, "content_hash", _hash(self.content_hash))
        timestamps = {
            field_name: _timestamp(getattr(self, field_name), field_name=field_name)
            for field_name in ("as_of", "knowledge_cutoff", "publication_cutoff")
        }
        for field_name, (canonical, _) in timestamps.items():
            object.__setattr__(self, field_name, canonical)
        if not (
            timestamps["publication_cutoff"][1]
            <= timestamps["knowledge_cutoff"][1]
            <= timestamps["as_of"][1]
        ):
            raise ValueError("context input PIT cutoffs exceed the decision timestamp")
        snapshots = tuple(
            sorted(
                (
                    _identity(value, field_name="source_snapshot_id")
                    for value in self.source_snapshot_ids
                ),
                key=str.encode,
            )
        )
        if not snapshots or len(set(snapshots)) != len(snapshots):
            raise ValueError("source_snapshot_ids must be non-empty and unique")
        object.__setattr__(self, "source_snapshot_ids", snapshots)

    @property
    def identity(self) -> tuple[str, str]:
        """Return the stable manifest ordering identity."""
        return self.context_kind.value, self.context_id


def normalize_context_input_refs(
    values: object,
) -> tuple[ReplayContextInputRef, ...]:
    """Validate and canonically order an exact context evidence set."""
    if not isinstance(values, tuple):
        raise ValueError("context_input_refs must be a tuple")
    raw = cast(tuple[object, ...], values)
    if any(type(item) is not ReplayContextInputRef for item in raw):
        raise ValueError("context_input_refs must contain ReplayContextInputRef values")
    typed = cast(tuple[ReplayContextInputRef, ...], raw)
    identities = tuple(item.identity for item in typed)
    if len(set(identities)) != len(identities):
        raise ValueError(
            "context_input_refs must have unique kind and context identity"
        )
    return tuple(sorted(typed, key=lambda item: item.identity))
