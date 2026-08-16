"""Immutable, hash-bound Agent episode manifests and strict codecs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import cast

import orjson

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import (
    enum_value,
    normalized_text,
    positive_int,
    sha256_hex,
    utc_datetime,
)
from ditto_agent.contracts.runtime import AgentManifest, ModelProfile, RunStatus


class EpisodeToolEffect(StrEnum):
    """Whether replay must suppress a recorded tool invocation."""

    READ_ONLY = "read_only"
    SIDE_EFFECT = "side_effect"


def episode_event_hash(
    *,
    event_id: int,
    run_id: str,
    run_sequence: int,
    event_type: str,
    payload_hash: str,
    occurred_at: datetime,
    prev_hash: str | None,
) -> str:
    """Return the canonical identity shared by live storage and replay."""
    return canonical_sha256(
        {
            "event_id": event_id,
            "run_id": run_id,
            "run_sequence": run_sequence,
            "event_type": event_type,
            "payload_hash": payload_hash,
            "occurred_at": occurred_at,
            "prev_hash": prev_hash,
        }
    )


@dataclass(frozen=True, slots=True)
class EpisodeEventRecord:
    """One persisted run event including its sequence and chain proof."""

    event_id: int
    run_id: str
    run_sequence: int
    event_type: str
    payload_hash: str
    occurred_at: datetime
    prev_hash: str | None
    event_hash: str

    def __post_init__(self) -> None:
        """Normalize event fields while preserving its supplied chain hash."""
        positive_int(self.event_id, field="event_id")
        positive_int(self.run_sequence, field="run_sequence")
        object.__setattr__(self, "run_id", normalized_text(self.run_id, field="run_id"))
        object.__setattr__(
            self, "event_type", normalized_text(self.event_type, field="event_type")
        )
        object.__setattr__(
            self, "payload_hash", sha256_hex(self.payload_hash, field="payload_hash")
        )
        object.__setattr__(
            self, "occurred_at", utc_datetime(self.occurred_at, field="occurred_at")
        )
        if self.prev_hash is not None:
            object.__setattr__(
                self, "prev_hash", sha256_hex(self.prev_hash, field="prev_hash")
            )
        object.__setattr__(
            self, "event_hash", sha256_hex(self.event_hash, field="event_hash")
        )

    @classmethod
    def create(
        cls,
        *,
        event_id: int,
        run_id: str,
        run_sequence: int,
        event_type: str,
        payload_hash: str,
        occurred_at: datetime,
        prev_hash: str | None,
    ) -> EpisodeEventRecord:
        """Create an event only after normalizing all hash inputs."""
        provisional = cls(
            event_id=event_id,
            run_id=run_id,
            run_sequence=run_sequence,
            event_type=event_type,
            payload_hash=payload_hash,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            event_hash="0" * 64,
        )
        return cls(
            event_id=provisional.event_id,
            run_id=provisional.run_id,
            run_sequence=provisional.run_sequence,
            event_type=provisional.event_type,
            payload_hash=provisional.payload_hash,
            occurred_at=provisional.occurred_at,
            prev_hash=provisional.prev_hash,
            event_hash=episode_event_hash(
                event_id=provisional.event_id,
                run_id=provisional.run_id,
                run_sequence=provisional.run_sequence,
                event_type=provisional.event_type,
                payload_hash=provisional.payload_hash,
                occurred_at=provisional.occurred_at,
                prev_hash=provisional.prev_hash,
            ),
        )

    def identity_payload(self) -> dict[str, object]:
        """Return all fields authenticated by the event hash."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "run_sequence": self.run_sequence,
            "event_type": self.event_type,
            "payload_hash": self.payload_hash,
            "occurred_at": self.occurred_at,
            "prev_hash": self.prev_hash,
            "event_hash": self.event_hash,
        }

    def verify_event_hash(self) -> bool:
        """Verify the event content and predecessor against its durable hash."""
        return self.event_hash == episode_event_hash(
            event_id=self.event_id,
            run_id=self.run_id,
            run_sequence=self.run_sequence,
            event_type=self.event_type,
            payload_hash=self.payload_hash,
            occurred_at=self.occurred_at,
            prev_hash=self.prev_hash,
        )


@dataclass(frozen=True, slots=True)
class EpisodeToolCallRecord:
    """Hash-only identity for one tool call and its effect classification."""

    call_id: str
    tool_name: str
    arguments_hash: str
    effect: EpisodeToolEffect
    action_hash: str | None

    def __post_init__(self) -> None:
        """Validate call identity and effect-specific action binding."""
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
        enum_value(self.effect, EpisodeToolEffect, field="effect")
        if self.action_hash is not None:
            object.__setattr__(
                self, "action_hash", sha256_hex(self.action_hash, field="action_hash")
            )
        if self.effect is EpisodeToolEffect.READ_ONLY and self.action_hash is not None:
            raise ValueError("read-only tool calls cannot carry an action hash")
        if self.effect is EpisodeToolEffect.SIDE_EFFECT and self.action_hash is None:
            raise ValueError("side-effect tool calls require an action hash")

    def identity_payload(self) -> dict[str, object]:
        """Return the version-independent call identity."""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
            "effect": self.effect,
            "action_hash": self.action_hash,
        }


def _references(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(
        normalized_text(value, field=f"{field_name} item") for value in values
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class EpisodeToolResultRecord:
    """Recorded result digest with evidence or durable artifact references."""

    call_id: str
    result_hash: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Normalize result identity and require a durable reference."""
        object.__setattr__(
            self, "call_id", normalized_text(self.call_id, field="call_id")
        )
        object.__setattr__(
            self, "result_hash", sha256_hex(self.result_hash, field="result_hash")
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _references(self.evidence_refs, field_name="evidence_refs"),
        )
        object.__setattr__(
            self,
            "artifact_refs",
            _references(self.artifact_refs, field_name="artifact_refs"),
        )
        if not self.evidence_refs and not self.artifact_refs:
            raise ValueError("tool results require evidence or artifact references")

    def identity_payload(self) -> dict[str, object]:
        """Return the replay-safe result identity without raw payloads."""
        return {
            "call_id": self.call_id,
            "result_hash": self.result_hash,
            "evidence_refs": self.evidence_refs,
            "artifact_refs": self.artifact_refs,
        }


_TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class AgentEpisodeManifest:
    """Sealed hash-only record sufficient for deterministic offline replay."""

    episode_id: str
    run_id: str
    input_hash: str
    authority_hash: str
    temporal_context_hash: str
    agent_manifest: AgentManifest
    final_status: RunStatus
    events: tuple[EpisodeEventRecord, ...]
    tool_calls: tuple[EpisodeToolCallRecord, ...]
    tool_results: tuple[EpisodeToolResultRecord, ...]
    final_output_hash: str | None
    sealed_at: datetime
    episode_schema_version: int = 1
    manifest_hash: str = field(init=False)
    replay_identity: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate the sealed episode and compute both stable identities."""
        self._normalize_header()
        self._validate_terminal_identity()
        self._normalize_records()
        self._normalize_seal_time()
        object.__setattr__(
            self, "manifest_hash", canonical_sha256(self.identity_payload())
        )
        object.__setattr__(
            self, "replay_identity", canonical_sha256(self.replay_identity_payload())
        )

    def _normalize_header(self) -> None:
        object.__setattr__(
            self, "episode_id", normalized_text(self.episode_id, field="episode_id")
        )
        object.__setattr__(self, "run_id", normalized_text(self.run_id, field="run_id"))
        object.__setattr__(
            self, "input_hash", sha256_hex(self.input_hash, field="input_hash")
        )
        object.__setattr__(
            self,
            "authority_hash",
            sha256_hex(self.authority_hash, field="authority_hash"),
        )
        object.__setattr__(
            self,
            "temporal_context_hash",
            sha256_hex(self.temporal_context_hash, field="temporal_context_hash"),
        )
        if not isinstance(cast(object, self.agent_manifest), AgentManifest):
            raise TypeError("agent_manifest must be an AgentManifest")
        if not self.agent_manifest.verify_manifest_hash():
            raise ValueError("agent manifest hash is invalid")

    def _validate_terminal_identity(self) -> None:
        enum_value(self.final_status, RunStatus, field="final_status")
        if self.final_status not in _TERMINAL_STATUSES:
            raise ValueError("episode final_status must be terminal")
        if self.final_output_hash is not None:
            object.__setattr__(
                self,
                "final_output_hash",
                sha256_hex(self.final_output_hash, field="final_output_hash"),
            )
        if self.final_status is RunStatus.COMPLETED and self.final_output_hash is None:
            raise ValueError("completed episodes require a final output hash")
        if self.episode_schema_version != 1:
            raise ValueError("episode_schema_version is not supported")

    def _normalize_records(self) -> None:
        events = tuple(self.events)
        object.__setattr__(self, "events", events)
        self._validate_event_chain()
        calls_list: list[EpisodeToolCallRecord] = []
        for item in cast(tuple[object, ...], tuple(self.tool_calls)):
            if not isinstance(item, EpisodeToolCallRecord):
                raise TypeError("tool_calls must contain EpisodeToolCallRecord values")
            calls_list.append(item)
        results_list: list[EpisodeToolResultRecord] = []
        for item in cast(tuple[object, ...], tuple(self.tool_results)):
            if not isinstance(item, EpisodeToolResultRecord):
                raise TypeError(
                    "tool_results must contain EpisodeToolResultRecord values"
                )
            results_list.append(item)
        calls = tuple(sorted(calls_list, key=lambda item: item.call_id))
        results = tuple(sorted(results_list, key=lambda item: item.call_id))
        if len({item.call_id for item in calls}) != len(calls):
            raise ValueError("episode tool calls must have unique call IDs")
        if tuple(item.call_id for item in calls) != tuple(
            item.call_id for item in results
        ):
            raise ValueError("episode tool results must exactly match tool calls")
        object.__setattr__(self, "tool_calls", calls)
        object.__setattr__(self, "tool_results", results)

    def _normalize_seal_time(self) -> None:
        sealed_at = utc_datetime(self.sealed_at, field="sealed_at")
        if self.events and sealed_at < self.events[-1].occurred_at:
            raise ValueError("sealed_at must not precede the final event")
        object.__setattr__(self, "sealed_at", sealed_at)

    def _validate_event_chain(self) -> None:
        previous_hash: str | None = None
        previous_event_id = 0
        previous_time: datetime | None = None
        raw_events = cast(tuple[object, ...], self.events)
        for expected_sequence, item in enumerate(raw_events, start=1):
            if not isinstance(item, EpisodeEventRecord):
                raise TypeError("events must contain EpisodeEventRecord values")
            event = item
            if event.run_id != self.run_id:
                raise ValueError("event hash chain contains a different run ID")
            if event.run_sequence != expected_sequence:
                raise ValueError("event hash chain has a non-contiguous run sequence")
            if event.event_id <= previous_event_id:
                raise ValueError("event hash chain has non-monotonic event IDs")
            if previous_time is not None and event.occurred_at < previous_time:
                raise ValueError("event hash chain has non-monotonic timestamps")
            if event.prev_hash != previous_hash or not event.verify_event_hash():
                raise ValueError("event hash chain is invalid")
            previous_hash = event.event_hash
            previous_event_id = event.event_id
            previous_time = event.occurred_at

    def identity_payload(self) -> dict[str, object]:
        """Return every immutable version, event, call, and result identity."""
        return {
            "episode_id": self.episode_id,
            "episode_schema_version": self.episode_schema_version,
            "run_id": self.run_id,
            "input_hash": self.input_hash,
            "authority_hash": self.authority_hash,
            "temporal_context_hash": self.temporal_context_hash,
            "agent_manifest": {
                **self.agent_manifest.identity_payload(),
                "manifest_hash": self.agent_manifest.manifest_hash,
            },
            "final_status": self.final_status,
            "events": tuple(item.identity_payload() for item in self.events),
            "tool_calls": tuple(item.identity_payload() for item in self.tool_calls),
            "tool_results": tuple(
                item.identity_payload() for item in self.tool_results
            ),
            "final_output_hash": self.final_output_hash,
            "sealed_at": self.sealed_at,
        }

    def replay_identity_payload(self) -> dict[str, object]:
        """Return the sealed identity replay verifies before yielding records."""
        return {
            "manifest_hash": self.manifest_hash,
            "event_head_hash": self.events[-1].event_hash if self.events else None,
            "tool_result_hashes": tuple(
                (item.call_id, item.result_hash) for item in self.tool_results
            ),
            "final_output_hash": self.final_output_hash,
        }

    def verify_manifest_hash(self) -> bool:
        """Recompute the full episode manifest hash."""
        return self.manifest_hash == canonical_sha256(self.identity_payload())

    def verify_replay_identity(self) -> bool:
        """Recompute the replay identity from the sealed chain and results."""
        return self.replay_identity == canonical_sha256(self.replay_identity_payload())


def encode_episode(episode: AgentEpisodeManifest) -> bytes:
    """Encode a fully verified episode as canonical JSON for durable storage."""
    if not episode.verify_manifest_hash() or not episode.verify_replay_identity():
        raise ValueError("episode identity is invalid")
    return canonical_bytes(
        {
            **episode.identity_payload(),
            "manifest_hash": episode.manifest_hash,
            "replay_identity": episode.replay_identity,
        }
    )


def _mapping(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    result: dict[str, object] = {}
    raw = cast(dict[object, object], value)
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        result[key] = item
    return result


def _exact(mapping: dict[str, object], keys: set[str], *, field_name: str) -> None:
    if set(mapping) != keys:
        raise ValueError(f"{field_name} has an invalid field set")


def _string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _optional_string(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name=field_name)


def _integer(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _items(value: object, *, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return tuple(cast(list[object], value))


def _timestamp(value: object, *, field_name: str) -> datetime:
    text = _string(value, field_name=field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    return utc_datetime(parsed, field=field_name)


def _decode_manifest(value: object) -> AgentManifest:
    raw = _mapping(value, field_name="agent_manifest")
    _exact(
        raw,
        {
            "manifest_id",
            "agent_version",
            "prompt_version",
            "prompt_hash",
            "tool_schema_version",
            "tool_schema_hash",
            "model_profile",
            "model_snapshot",
            "manifest_hash",
        },
        field_name="agent_manifest",
    )
    manifest = AgentManifest(
        manifest_id=_string(raw["manifest_id"], field_name="manifest_id"),
        agent_version=_string(raw["agent_version"], field_name="agent_version"),
        prompt_version=_string(raw["prompt_version"], field_name="prompt_version"),
        prompt_hash=_string(raw["prompt_hash"], field_name="prompt_hash"),
        tool_schema_version=_string(
            raw["tool_schema_version"], field_name="tool_schema_version"
        ),
        tool_schema_hash=_string(
            raw["tool_schema_hash"], field_name="tool_schema_hash"
        ),
        model_profile=ModelProfile(
            _string(raw["model_profile"], field_name="model_profile")
        ),
        model_snapshot=_string(raw["model_snapshot"], field_name="model_snapshot"),
    )
    if manifest.manifest_hash != _string(
        raw["manifest_hash"], field_name="agent manifest_hash"
    ):
        raise ValueError("agent manifest hash is invalid")
    return manifest


def _decode_event(value: object) -> EpisodeEventRecord:
    raw = _mapping(value, field_name="event")
    keys = {
        "event_id",
        "run_id",
        "run_sequence",
        "event_type",
        "payload_hash",
        "occurred_at",
        "prev_hash",
        "event_hash",
    }
    _exact(raw, keys, field_name="event")
    return EpisodeEventRecord(
        event_id=_integer(raw["event_id"], field_name="event_id"),
        run_id=_string(raw["run_id"], field_name="run_id"),
        run_sequence=_integer(raw["run_sequence"], field_name="run_sequence"),
        event_type=_string(raw["event_type"], field_name="event_type"),
        payload_hash=_string(raw["payload_hash"], field_name="payload_hash"),
        occurred_at=_timestamp(raw["occurred_at"], field_name="occurred_at"),
        prev_hash=_optional_string(raw["prev_hash"], field_name="prev_hash"),
        event_hash=_string(raw["event_hash"], field_name="event_hash"),
    )


def _decode_call(value: object) -> EpisodeToolCallRecord:
    raw = _mapping(value, field_name="tool_call")
    _exact(
        raw,
        {"call_id", "tool_name", "arguments_hash", "effect", "action_hash"},
        field_name="tool_call",
    )
    return EpisodeToolCallRecord(
        call_id=_string(raw["call_id"], field_name="call_id"),
        tool_name=_string(raw["tool_name"], field_name="tool_name"),
        arguments_hash=_string(raw["arguments_hash"], field_name="arguments_hash"),
        effect=EpisodeToolEffect(_string(raw["effect"], field_name="effect")),
        action_hash=_optional_string(raw["action_hash"], field_name="action_hash"),
    )


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    return tuple(
        _string(item, field_name=f"{field_name} item")
        for item in _items(value, field_name=field_name)
    )


def _decode_result(value: object) -> EpisodeToolResultRecord:
    raw = _mapping(value, field_name="tool_result")
    _exact(
        raw,
        {"call_id", "result_hash", "evidence_refs", "artifact_refs"},
        field_name="tool_result",
    )
    return EpisodeToolResultRecord(
        call_id=_string(raw["call_id"], field_name="call_id"),
        result_hash=_string(raw["result_hash"], field_name="result_hash"),
        evidence_refs=_string_tuple(raw["evidence_refs"], field_name="evidence_refs"),
        artifact_refs=_string_tuple(raw["artifact_refs"], field_name="artifact_refs"),
    )


def decode_episode(payload: bytes) -> AgentEpisodeManifest:
    """Strictly decode and re-authenticate one durable episode payload."""
    try:
        root = _mapping(cast(object, orjson.loads(payload)), field_name="episode")
    except orjson.JSONDecodeError as exc:
        raise ValueError("episode payload is not valid JSON") from exc
    keys = {
        "episode_id",
        "episode_schema_version",
        "run_id",
        "input_hash",
        "authority_hash",
        "temporal_context_hash",
        "agent_manifest",
        "final_status",
        "events",
        "tool_calls",
        "tool_results",
        "final_output_hash",
        "sealed_at",
        "manifest_hash",
        "replay_identity",
    }
    _exact(root, keys, field_name="episode")
    episode = AgentEpisodeManifest(
        episode_id=_string(root["episode_id"], field_name="episode_id"),
        run_id=_string(root["run_id"], field_name="run_id"),
        input_hash=_string(root["input_hash"], field_name="input_hash"),
        authority_hash=_string(root["authority_hash"], field_name="authority_hash"),
        temporal_context_hash=_string(
            root["temporal_context_hash"], field_name="temporal_context_hash"
        ),
        agent_manifest=_decode_manifest(root["agent_manifest"]),
        final_status=RunStatus(
            _string(root["final_status"], field_name="final_status")
        ),
        events=tuple(
            _decode_event(item) for item in _items(root["events"], field_name="events")
        ),
        tool_calls=tuple(
            _decode_call(item)
            for item in _items(root["tool_calls"], field_name="tool_calls")
        ),
        tool_results=tuple(
            _decode_result(item)
            for item in _items(root["tool_results"], field_name="tool_results")
        ),
        final_output_hash=_optional_string(
            root["final_output_hash"], field_name="final_output_hash"
        ),
        sealed_at=_timestamp(root["sealed_at"], field_name="sealed_at"),
        episode_schema_version=_integer(
            root["episode_schema_version"], field_name="episode_schema_version"
        ),
    )
    if episode.manifest_hash != _string(
        root["manifest_hash"], field_name="manifest_hash"
    ):
        raise ValueError("episode manifest hash is invalid")
    if episode.replay_identity != _string(
        root["replay_identity"], field_name="replay_identity"
    ):
        raise ValueError("episode replay identity is invalid")
    return episode


__all__ = [
    "AgentEpisodeManifest",
    "EpisodeEventRecord",
    "EpisodeToolCallRecord",
    "EpisodeToolEffect",
    "EpisodeToolResultRecord",
    "decode_episode",
    "encode_episode",
    "episode_event_hash",
]
