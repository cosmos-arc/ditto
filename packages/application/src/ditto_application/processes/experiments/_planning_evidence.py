"""Defensive validation and report serialization for planning probe evidence."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_application.processes.experiments.planning_probes import (
    CandidateExecutorEvidence,
    ResearchSnapshotEvidence,
    is_canonical_content_hash,
    is_canonical_identity,
)

__all__ = [
    "candidate_evidence_tuple",
    "canonical_text",
    "canonical_text_tuple",
    "snapshot_payload",
    "text_tuple_payload",
]


def canonical_text(value: object) -> bool:
    return is_canonical_identity(value)


def canonical_text_tuple(value: object, *, nonempty: bool = False) -> bool:
    if type(value) is not tuple:
        return False
    items = cast("tuple[object, ...]", value)
    if nonempty and not items:
        return False
    if not all(canonical_text(item) for item in items):
        return False
    return len(set(cast("tuple[str, ...]", items))) == len(items)


def candidate_evidence_tuple(
    value: object,
) -> tuple[CandidateExecutorEvidence, ...] | None:
    if type(value) is not tuple:
        return None
    items = cast("tuple[object, ...]", value)
    if not all(
        type(item) is CandidateExecutorEvidence
        and is_canonical_content_hash(item.candidate_hash)
        and is_canonical_content_hash(item.resolved_spec_hash)
        and is_canonical_content_hash(item.parameter_hash)
        for item in items
    ):
        return None
    return cast("tuple[CandidateExecutorEvidence, ...]", items)


def text_tuple_payload(value: object) -> list[str]:
    if not canonical_text_tuple(value):
        return []
    return list(cast("tuple[str, ...]", value))


def snapshot_payload(value: object) -> object:
    if type(value) is not ResearchSnapshotEvidence:
        return None
    snapshot_id = cast("object", value.snapshot_id)
    dataset_id = cast("object", value.dataset_id)
    manifest_hash = cast("object", value.manifest_hash)
    source_snapshot_ids = cast("object", value.source_snapshot_ids)
    snapshot_start = cast("object", value.snapshot_start)
    snapshot_end = cast("object", value.snapshot_end)
    known_at_policy = cast("object", value.known_at_policy)
    builder_version = cast("object", value.builder_version)
    return {
        "snapshot_id": snapshot_id if canonical_text(snapshot_id) else None,
        "dataset_id": dataset_id if canonical_text(dataset_id) else None,
        "manifest_hash": (
            manifest_hash if is_canonical_content_hash(manifest_hash) else None
        ),
        "source_snapshot_ids": (
            list(cast("tuple[str, ...]", source_snapshot_ids))
            if canonical_text_tuple(source_snapshot_ids)
            else []
        ),
        "snapshot_start": (
            snapshot_start.isoformat() if type(snapshot_start) is date else None
        ),
        "snapshot_end": (
            snapshot_end.isoformat() if type(snapshot_end) is date else None
        ),
        "known_at_policy": (
            known_at_policy if canonical_text(known_at_policy) else None
        ),
        "builder_version": (
            builder_version if canonical_text(builder_version) else None
        ),
    }
