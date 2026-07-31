"""Immutable contracts shared by experiment launch compilation and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_analysis.experiments import (
    ContentHash,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentRecord,
    FoldPersistenceSpec,
    GateEvaluationRecord,
    ResearchCycleIdentity,
)

from ditto_application.mutation_idempotency import MutationIdempotency


@dataclass(frozen=True, slots=True)
class PreparedExperimentLaunch:
    """All immutable values checked before the launch's first writer call."""

    cycle: ResearchCycleIdentity
    spec: ExperimentLaunchSpec
    initial_record: ExperimentRecord
    gates: tuple[GateEvaluationRecord, ...]
    folds: tuple[FoldPersistenceSpec, ...]
    launch_spec_json: bytes
    launch_spec_hash: ContentHash
    gate_payload_hashes: tuple[ContentHash, ...]
    fold_payload_hashes: tuple[ContentHash, ...]
    preflight_json: bytes
    preflight_hash: ContentHash
    plan_preimage_json: bytes
    plan_hash: str
    creation_detail: Mapping[str, object]
    creation_detail_json: bytes
    creation_detail_hash: ContentHash
    enqueue_detail: Mapping[str, object]
    enqueue_detail_json: bytes
    enqueue_detail_hash: ContentHash
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class DurableLaunchReplay:
    """Verified original enqueue receipt reconstructed without planning probes."""

    projection: ExperimentProjection
    candidate_count: int
    fold_count: int
    plan_hash: str


__all__ = ["DurableLaunchReplay", "PreparedExperimentLaunch"]
