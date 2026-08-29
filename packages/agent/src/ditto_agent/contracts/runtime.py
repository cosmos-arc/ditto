"""Core immutable Agent runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    enum_value,
    nonnegative_decimal,
    normalized_text,
    positive_int,
    sha256_hex,
    utc_datetime,
)


class RunStatus(StrEnum):
    """Host-controlled lifecycle states for one Agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelProfile(StrEnum):
    """Approved model-quality profiles; concrete model IDs stay in manifests."""

    BALANCED = "balanced"
    QUALITY = "quality"


class RetentionClass(StrEnum):
    """Local retention policy class for a short-lived Agent session."""

    EPHEMERAL = "ephemeral"
    STANDARD = "standard"
    AUDIT = "audit"


@dataclass(frozen=True, slots=True)
class AgentManifest:
    """Versioned prompt, tool schema, and model identity for replay."""

    manifest_id: str
    agent_version: str
    prompt_version: str
    prompt_hash: str
    tool_schema_version: str
    tool_schema_hash: str
    model_profile: ModelProfile
    model_snapshot: str
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Normalize manifest fields and validate all supplied digests."""
        object.__setattr__(
            self, "manifest_id", normalized_text(self.manifest_id, field="manifest_id")
        )
        object.__setattr__(
            self,
            "agent_version",
            normalized_text(self.agent_version, field="agent_version"),
        )
        object.__setattr__(
            self,
            "prompt_version",
            normalized_text(self.prompt_version, field="prompt_version"),
        )
        object.__setattr__(
            self, "prompt_hash", sha256_hex(self.prompt_hash, field="prompt_hash")
        )
        object.__setattr__(
            self,
            "tool_schema_version",
            normalized_text(self.tool_schema_version, field="tool_schema_version"),
        )
        object.__setattr__(
            self,
            "tool_schema_hash",
            sha256_hex(self.tool_schema_hash, field="tool_schema_hash"),
        )
        enum_value(self.model_profile, ModelProfile, field="model_profile")
        object.__setattr__(
            self,
            "model_snapshot",
            normalized_text(self.model_snapshot, field="model_snapshot"),
        )
        object.__setattr__(
            self, "manifest_hash", canonical_sha256(self.identity_payload())
        )

    def identity_payload(self) -> dict[str, object]:
        """Return normalized manifest fields authenticated by its hash."""
        return {
            "manifest_id": self.manifest_id,
            "agent_version": self.agent_version,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "tool_schema_version": self.tool_schema_version,
            "tool_schema_hash": self.tool_schema_hash,
            "model_profile": self.model_profile,
            "model_snapshot": self.model_snapshot,
        }

    def verify_manifest_hash(self) -> bool:
        """Verify the manifest hash against normalized replay fields."""
        return canonical_sha256(self.identity_payload()) == self.manifest_hash


@dataclass(frozen=True, slots=True)
class AgentSession:
    """Local conversation identity with an explicit retention policy."""

    session_id: str
    created_at: datetime
    retention_class: RetentionClass

    def __post_init__(self) -> None:
        """Validate the session identity and normalize creation time to UTC."""
        object.__setattr__(
            self, "session_id", normalized_text(self.session_id, field="session_id")
        )
        object.__setattr__(
            self, "created_at", utc_datetime(self.created_at, field="created_at")
        )
        enum_value(self.retention_class, RetentionClass, field="retention_class")


@dataclass(frozen=True, slots=True)
class AgentRun:
    """Immutable snapshot of one governed Agent run."""

    run_id: str
    session_id: str
    status: RunStatus
    objective: str
    authority_hash: str
    max_model_tokens: int
    max_model_spend_usd: Decimal
    model_profile: ModelProfile
    manifest_hash: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate authority, budgets, enum values, and monotonic timestamps."""
        object.__setattr__(self, "run_id", normalized_text(self.run_id, field="run_id"))
        object.__setattr__(
            self, "session_id", normalized_text(self.session_id, field="session_id")
        )
        enum_value(self.status, RunStatus, field="status")
        object.__setattr__(
            self,
            "objective",
            normalized_text(self.objective, field="objective", maximum=4096),
        )
        object.__setattr__(
            self,
            "authority_hash",
            sha256_hex(self.authority_hash, field="authority_hash"),
        )
        positive_int(self.max_model_tokens, field="max_model_tokens")
        nonnegative_decimal(self.max_model_spend_usd, field="max_model_spend_usd")
        enum_value(self.model_profile, ModelProfile, field="model_profile")
        object.__setattr__(
            self,
            "manifest_hash",
            sha256_hex(self.manifest_hash, field="manifest_hash"),
        )
        created = utc_datetime(self.created_at, field="created_at")
        started = (
            utc_datetime(self.started_at, field="started_at")
            if self.started_at is not None
            else None
        )
        finished = (
            utc_datetime(self.finished_at, field="finished_at")
            if self.finished_at is not None
            else None
        )
        if started is not None and started < created:
            raise ValueError("started_at must not precede created_at")
        if finished is not None and (started is None or finished < started):
            raise ValueError("finished_at requires started_at and must not precede it")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One monotonic hash-chain event emitted by a governed run."""

    event_id: int
    run_id: str
    event_type: str
    payload_hash: str
    occurred_at: datetime
    prev_hash: str | None

    def __post_init__(self) -> None:
        """Validate event sequence, identities, hashes, and UTC occurrence time."""
        positive_int(self.event_id, field="event_id")
        object.__setattr__(self, "run_id", normalized_text(self.run_id, field="run_id"))
        object.__setattr__(
            self, "event_type", normalized_text(self.event_type, field="event_type")
        )
        object.__setattr__(
            self,
            "payload_hash",
            sha256_hex(self.payload_hash, field="payload_hash"),
        )
        object.__setattr__(
            self, "occurred_at", utc_datetime(self.occurred_at, field="occurred_at")
        )
        if self.prev_hash is not None:
            object.__setattr__(
                self, "prev_hash", sha256_hex(self.prev_hash, field="prev_hash")
            )


__all__ = [
    "AgentEvent",
    "AgentManifest",
    "AgentRun",
    "AgentSession",
    "ModelProfile",
    "RetentionClass",
    "RunStatus",
]
