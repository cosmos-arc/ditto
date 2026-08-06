"""Verified canonical manifest boundary for one exact research snapshot."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)

__all__ = ["VerifiedResearchSnapshotManifest"]

_SHA256 = re.compile(r"[0-9a-f]{64}")
_SCHEMA_VERSION = 1
_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "snapshot_id",
        "dataset_id",
        "source_snapshot_ids",
        "known_at_policy",
        "builder_version",
        "inputs",
    }
)
_INPUT_KEYS = frozenset(
    {
        "input_id",
        "artifact_kind",
        "content_hash",
        "schema_hash",
    }
)
_REQUIRED_INPUT_KINDS = (
    "bars",
    "calendar",
    "membership",
    "instrument_rules",
)


def _error(reason: str) -> AppProcessError:
    return AppProcessError(
        "verified research snapshot manifest is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
        },
    )


def _identity(value: object) -> str:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise _error("invalid_snapshot_manifest_identity")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _error("invalid_snapshot_manifest_identity") from None
    return value


def _hash(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise _error("invalid_snapshot_manifest_hash")
    return value


def _decode_canonical(raw: bytes) -> dict[str, object]:
    try:
        decoded_value = orjson.loads(raw)
    except orjson.JSONDecodeError:
        raise _error("invalid_snapshot_manifest_json") from None
    if type(decoded_value) is not dict:
        raise _error("invalid_snapshot_manifest_json")
    decoded = cast("dict[str, object]", decoded_value)
    if orjson.dumps(decoded, option=orjson.OPT_SORT_KEYS) != raw:
        raise _error("noncanonical_snapshot_manifest")
    return decoded


def _sources(raw_value: object) -> tuple[str, ...]:
    if type(raw_value) is not list or not raw_value:
        raise _error("invalid_snapshot_manifest_sources")
    sources = tuple(_identity(item) for item in cast("list[object]", raw_value))
    if len(set(sources)) != len(sources):
        raise _error("duplicate_snapshot_manifest_source")
    if sources != tuple(sorted(sources, key=str.encode)):
        raise _error("noncanonical_snapshot_manifest_sources")
    return sources


def _input_payload(raw_value: object) -> ContentAddressedResearchInput:
    if type(raw_value) is not dict:
        raise _error("invalid_snapshot_manifest_input")
    payload = cast("dict[str, object]", raw_value)
    if frozenset(payload) != _INPUT_KEYS:
        raise _error("invalid_snapshot_manifest_input_keys")
    return ContentAddressedResearchInput(
        input_id=_identity(payload["input_id"]),
        artifact_kind=_identity(payload["artifact_kind"]),
        content_hash=_hash(payload["content_hash"]),
        schema_hash=_hash(payload["schema_hash"]),
    )


def _inputs(raw_value: object) -> tuple[ContentAddressedResearchInput, ...]:
    if type(raw_value) is not list or not raw_value:
        raise _error("invalid_snapshot_manifest_inputs")
    inputs = tuple(_input_payload(item) for item in cast("list[object]", raw_value))
    input_ids = tuple(item.input_id for item in inputs)
    if len(set(input_ids)) != len(input_ids):
        raise _error("duplicate_snapshot_manifest_input")
    if input_ids != tuple(sorted(input_ids, key=str.encode)):
        raise _error("noncanonical_snapshot_manifest_inputs")
    kind_counts = {
        kind: sum(item.artifact_kind == kind for item in inputs)
        for kind in _REQUIRED_INPUT_KINDS
    }
    if any(count != 1 for count in kind_counts.values()):
        raise _error("required_snapshot_input_missing_or_ambiguous")
    return inputs


@dataclass(frozen=True, slots=True)
class VerifiedResearchSnapshotManifest:
    """Derive one immutable snapshot binding solely from exact manifest bytes."""

    exact_snapshot: ExactResearchSnapshot
    manifest_bytes: bytes = field(repr=False)
    snapshot_binding: ResearchSnapshotBinding = field(init=False)

    def __post_init__(self) -> None:
        """Recompute the manifest identity and reject all caller-side drift."""
        if type(self.exact_snapshot) is not ExactResearchSnapshot:
            raise _error("invalid_exact_research_snapshot")
        raw_value: object = self.manifest_bytes
        if type(raw_value) is not bytes or not raw_value:
            raise _error("invalid_snapshot_manifest_bytes")
        raw = raw_value
        if hashlib.sha256(raw).hexdigest() != self.exact_snapshot.manifest_hash:
            raise _error("snapshot_manifest_hash_mismatch")

        payload = _decode_canonical(raw)
        if frozenset(payload) != _TOP_LEVEL_KEYS:
            raise _error("invalid_snapshot_manifest_keys")
        if type(payload["schema_version"]) is not int or (
            payload["schema_version"] != _SCHEMA_VERSION
        ):
            raise _error("unsupported_snapshot_manifest_schema")
        snapshot_id = _identity(payload["snapshot_id"])
        if snapshot_id != self.exact_snapshot.snapshot_id:
            raise _error("snapshot_manifest_identity_drift")
        dataset_id = _identity(payload["dataset_id"])
        source_snapshot_ids = _sources(payload["source_snapshot_ids"])
        known_at_policy = _identity(payload["known_at_policy"])
        if known_at_policy != "sample_time":
            raise _error("unsupported_known_at_policy")
        builder_version = _identity(payload["builder_version"])
        inputs = _inputs(payload["inputs"])

        object.__setattr__(
            self,
            "snapshot_binding",
            ResearchSnapshotBinding(
                exact_snapshot=self.exact_snapshot,
                dataset_id=dataset_id,
                source_snapshot_ids=source_snapshot_ids,
                known_at_policy=known_at_policy,
                builder_version=builder_version,
                inputs=inputs,
            ),
        )
