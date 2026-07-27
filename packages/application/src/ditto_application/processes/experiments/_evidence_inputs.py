# pyright: reportPrivateUsage=false
"""
Assembly helpers projecting persisted preflight detail and fold views into R3 evidence.

These helpers are pure orchestration seams used by the R3 review-packet collector
(Task 3). :func:`project_snapshot_manifest` reads the three persisted identity
fields (snapshot hash, node-registry hash, PIT policy) from one ``preflight_passed``
status-event detail mapping. :func:`assemble_candidate_fold_evidence` binds a
``FoldView``/``AttemptView`` pair with its optional verified report artifact
into one :class:`CandidateFoldEvidence` ready to feed
:func:`build_candidate_comparison`.

No helper here performs storage or execution I/O; callers are responsible for
loading the persisted views and materializing any backtest report.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ditto_analysis.experiments import (
    AttemptView,
    ContentHash,
    FoldView,
    SnapshotId,
)

from ditto_application.processes.experiments._evidence_values import comparison_error
from ditto_application.processes.experiments._persisted_execution_evidence import (
    _bind_persisted_fold_execution,
)
from ditto_application.processes.experiments._report_evidence import (
    LoadedBacktestReportArtifact,
)
from ditto_application.processes.experiments.comparison import CandidateFoldEvidence
from ditto_application.research_certification_contracts import (
    is_canonical_content_hash,
)

__all__ = [
    "FoldEvidenceInput",
    "SnapshotManifestProjection",
    "assemble_candidate_fold_evidence",
    "project_snapshot_manifest",
]


@dataclass(frozen=True, slots=True)
class SnapshotManifestProjection:
    """The three persisted identity fields drawn from one preflight detail."""

    snapshot_hash: ContentHash
    registry_hash: ContentHash
    pit_policy: str

    def __post_init__(self) -> None:
        """Reject any non-canonical hash or empty policy text."""
        if (
            type(self.snapshot_hash) is not ContentHash
            or type(self.registry_hash) is not ContentHash
            or type(self.pit_policy) is not str
            or not self.pit_policy
        ):
            comparison_error("invalid_snapshot_manifest_projection")


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        comparison_error("invalid_snapshot_manifest_projection")
    return cast("Mapping[str, object]", value)


def _required_field(mapping: Mapping[str, object], key: str) -> object:
    if key not in mapping:
        comparison_error("invalid_snapshot_manifest_projection")
    return mapping[key]


def _required_hash_text(value: object) -> ContentHash:
    if type(value) is not str or not is_canonical_content_hash(value):
        comparison_error("invalid_snapshot_manifest_projection")
    return ContentHash(value)


def _required_policy_text(value: object) -> str:
    if type(value) is not str or not value:
        comparison_error("invalid_snapshot_manifest_projection")
    return value


def project_snapshot_manifest(
    detail: Mapping[str, object],
) -> SnapshotManifestProjection:
    """Project the three persisted identity fields from one preflight detail mapping."""
    preflight = _required_mapping(_required_field(detail, "preflight"))
    executor = _required_mapping(_required_field(preflight, "executor"))
    registry_hash = _required_hash_text(
        _required_field(executor, "node_registry_manifest_hash")
    )
    authority = _required_mapping(_required_field(preflight, "authority"))
    authority_snapshot = _required_mapping(
        _required_field(authority, "snapshot_identity")
    )
    snapshot_hash = _required_hash_text(
        _required_field(authority_snapshot, "manifest_hash")
    )
    identities = _required_mapping(_required_field(preflight, "identities"))
    certification = _required_mapping(_required_field(identities, "certification"))
    snapshot_evidence = _required_mapping(
        _required_field(certification, "snapshot_evidence")
    )
    pit_policy = _required_policy_text(
        _required_field(snapshot_evidence, "known_at_policy")
    )
    return SnapshotManifestProjection(
        snapshot_hash=snapshot_hash,
        registry_hash=registry_hash,
        pit_policy=pit_policy,
    )


@dataclass(frozen=True, slots=True)
class FoldEvidenceInput:
    """Frozen persisted views and identity fields for one fold of evidence."""

    fold_view: FoldView
    attempt_view: AttemptView
    candidate_ordinal: int
    snapshot_id: SnapshotId
    snapshot_hash: ContentHash
    parameter_hash: ContentHash
    resolved_spec_hash: ContentHash
    report_artifact: LoadedBacktestReportArtifact | None = None
    failure_reason: str | None = None


def assemble_candidate_fold_evidence(
    fold_input: FoldEvidenceInput,
) -> CandidateFoldEvidence:
    """Assemble one CandidateFoldEvidence from persisted fold and attempt views."""
    execution_binding = _bind_persisted_fold_execution(
        fold_input.fold_view,
        fold_input.attempt_view,
    )
    return CandidateFoldEvidence(
        execution_binding=execution_binding,
        candidate_ordinal=fold_input.candidate_ordinal,
        snapshot_id=fold_input.snapshot_id,
        snapshot_hash=fold_input.snapshot_hash,
        parameter_hash=fold_input.parameter_hash,
        resolved_spec_hash=fold_input.resolved_spec_hash,
        report_artifact=fold_input.report_artifact,
        failure_reason=fold_input.failure_reason,
    )
