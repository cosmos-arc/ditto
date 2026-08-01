"""Durable, restart-safe publication of pre-holdout trial-ledger evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import (
    ArtifactRecord,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    LeaseFence,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.experiments.trial_ledger import (
    MAX_PBO_COMBINATIONS,
    TrialLedger,
    build_trial_ledger,
)
from ditto_analysis.research.artifact_measurement import measure_json_bytes
from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
    read_unique_preflight_detail,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    CollectedWalkForwardEvidence,
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CANDIDATE_EVIDENCE_ARTIFACT_KIND,
    CANDIDATE_EVIDENCE_SCHEMA_ID,
    CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    build_candidate_evidence_bundle,
    candidate_evidence_bundle_relative_path,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)
from ditto_application.processes.experiments.trial_evidence_bridge import (
    project_walk_forward_trial_outcomes,
)

__all__ = [
    "DurableSelectionEvidenceService",
    "PublishedSelectionEvidence",
    "SelectionEvidencePublisher",
]

_ARTIFACT_KIND = "selection_evidence"
_PRIOR_EVIDENCE_POLICY = "missing-is-failed-v1"
_READABLE_STAGES = frozenset(
    {
        ExperimentStage.CANDIDATE_SELECTION,
        ExperimentStage.HOLDOUT,
        ExperimentStage.EVIDENCE,
    }
)


def _selection_error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "durable selection evidence is invalid",
        details={"code": "SPEC_INVALID", "reason": reason, **details},
    )


def _selection_integrity(reason: str, **details: object) -> NoReturn:
    raise ExperimentIntegrityError(
        "selection evidence artifact integrity verification failed",
        details={
            "reason_code": "selection_evidence_artifact_integrity_mismatch",
            "reason": reason,
            **details,
        },
    )


def _selection_stage_event(
    events: tuple[StatusEventRecord, ...],
    experiment_id: ExperimentId,
) -> StatusEventRecord:
    """Return the immutable transition event owning publication time and revision."""
    matches = tuple(
        event
        for event in events
        if (
            event.experiment_id == experiment_id
            and event.reason_code == "scheduler_stage_complete"
            and event.stage is ExperimentStage.CANDIDATE_SELECTION
        )
    )
    if not matches:
        _selection_integrity("selection_evidence_stage_event_not_found")
    if len(matches) != 1:
        _selection_integrity("selection_evidence_stage_event_not_unique")
    event = matches[0]
    if (
        type(event.event_id) is not str
        or not event.event_id
        or event.subject_type is not StatusSubjectType.EXPERIMENT
        or event.candidate_id is not None
        or event.fold_id is not None
        or event.attempt_id is not None
        or type(event.subject_revision) is not int
        or event.subject_revision <= 0
        or event.previous_status is not ExperimentStatus.RUNNING
        or event.status is not ExperimentStatus.RUNNING
        or event.desired_state is not ExperimentDesiredState.RUN
        or event.failure_code is not None
        or event.detail != {"completed_stage": ExperimentStage.WALK_FORWARD.value}
        or event.detail_hash != canonical_payload(event.detail).content_hash
    ):
        _selection_integrity("selection_evidence_stage_event_drift")
    return event


class _SelectionEvidenceStore(Protocol):
    def load_snapshot(
        self,
        experiment_id: ExperimentId,
    ) -> ExperimentSchedulerSnapshot: ...


class _SelectionEvidenceReader(Protocol):
    def list_status_events(
        self,
        experiment_id: ExperimentId,
    ) -> tuple[StatusEventRecord, ...]: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None: ...


class SelectionEvidencePublisher(Protocol):
    """Coordinator write boundary for immutable candidate-selection evidence."""

    def publish_selection_evidence(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> PublishedSelectionEvidence:
        """Publish or exactly replay one experiment-family trial ledger."""
        ...


@dataclass(frozen=True, slots=True)
class _RebuiltSelectionEvidence:
    snapshot: ExperimentSchedulerSnapshot
    ledger: TrialLedger
    reproduction_fingerprint: ContentHash
    launch_spec_hash: ContentHash
    aggregation_hash: ContentHash
    created_at: datetime
    selection_stage_event_id: str
    selection_stage_subject_revision: int
    collected: CollectedWalkForwardEvidence

    @property
    def artifact_id(self) -> str:
        return f"selection-evidence-{self.ledger.content_hash}"

    @property
    def relative_path(self) -> str:
        return (
            f"experiments/{self.snapshot.projection.record.experiment_id}"
            "/selection-evidence.json"
        )

    @property
    def publication_spec(self) -> ArtifactPublicationSpec:
        experiment_id = self.snapshot.projection.record.experiment_id
        return ArtifactPublicationSpec(
            artifact_id=self.artifact_id,
            experiment_id=experiment_id,
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            artifact_kind=_ARTIFACT_KIND,
            relative_path=self.relative_path,
            reproduction_fingerprint=self.reproduction_fingerprint,
            audit={
                "created_at": self.created_at.isoformat(),
                "experiment_id": str(experiment_id),
                "candidate_id": None,
                "fold_id": None,
                "attempt_id": None,
                "reproduction_fingerprint": str(self.reproduction_fingerprint),
                "ledger_content_hash": str(self.ledger.content_hash),
                "launch_spec_hash": str(self.launch_spec_hash),
                "aggregation_hash": str(self.aggregation_hash),
                "declared_trial_count": self.ledger.declared_trial_count,
                "observed_trial_count": self.ledger.observed_trial_count,
                "failed_trial_count": self.ledger.failed_trial_count,
                "prior_evidence_policy": _PRIOR_EVIDENCE_POLICY,
                "pbo_combination_budget": MAX_PBO_COMBINATIONS,
                "selection_stage_event_id": self.selection_stage_event_id,
                "selection_stage_subject_revision": (
                    self.selection_stage_subject_revision
                ),
            },
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class PublishedSelectionEvidence:
    """One verified index fact paired with its rebuilt typed trial ledger."""

    record: ArtifactRecord
    ledger: TrialLedger

    def __post_init__(self) -> None:
        """Reject detached records at the public read boundary."""
        if type(self.ledger) is not TrialLedger:
            _selection_integrity("selection_evidence_published_pair_mismatch")
        current_experiment_ids = {
            trial.origin_experiment_id
            for trial in self.ledger.objective.trial_family.current_members
        }
        experiment_id = (
            next(iter(current_experiment_ids))
            if len(current_experiment_ids) == 1
            else None
        )
        if (
            type(self.record) is not ArtifactRecord
            or experiment_id is None
            or self.record.experiment_id != experiment_id
            or self.record.candidate_id is not None
            or self.record.fold_id is not None
            or self.record.attempt_id is not None
            or self.record.artifact_kind != _ARTIFACT_KIND
            or self.record.relative_path
            != f"experiments/{experiment_id}/selection-evidence.json"
            or self.record.content_hash != self.ledger.content_hash
            or self.record.artifact_id
            != f"selection-evidence-{self.ledger.content_hash}"
        ):
            _selection_integrity("selection_evidence_published_pair_mismatch")


@dataclass(frozen=True, slots=True)
class _CandidateEvidenceBundlePublisher:
    """Publish every candidate bundle through the existing generic envelope."""

    artifact_service: ResearchArtifactService
    artifact_reader: _SelectionEvidenceReader

    def publish(
        self,
        collected: CollectedWalkForwardEvidence,
        snapshot: ExperimentSchedulerSnapshot,
        *,
        comparison_revision: int,
        created_at: datetime,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> tuple[ArtifactRecord, ...]:
        records: list[ArtifactRecord] = []
        for candidate in snapshot.launch_spec.candidates:
            bundle = build_candidate_evidence_bundle(
                collected,
                candidate_id=str(candidate.candidate_id),
                comparison_revision=comparison_revision,
            )
            fingerprint = canonical_payload(
                {
                    "fold_sources": list(bundle.fold_sources),
                    "manifest": dict(bundle.manifest),
                    "schema_id": CANDIDATE_EVIDENCE_SCHEMA_ID,
                    "schema_version": CANDIDATE_EVIDENCE_SCHEMA_VERSION,
                }
            ).content_hash
            spec = ArtifactPublicationSpec(
                artifact_id=bundle.artifact_id,
                experiment_id=snapshot.projection.record.experiment_id,
                candidate_id=candidate.candidate_id,
                fold_id=None,
                attempt_id=None,
                artifact_kind=CANDIDATE_EVIDENCE_ARTIFACT_KIND,
                relative_path=candidate_evidence_bundle_relative_path(bundle),
                reproduction_fingerprint=fingerprint,
                audit={
                    **dict(bundle.manifest),
                    "artifact_kind": CANDIDATE_EVIDENCE_ARTIFACT_KIND,
                    "created_at": created_at.isoformat(),
                    "reproduction_fingerprint": str(fingerprint),
                    "schema_id": CANDIDATE_EVIDENCE_SCHEMA_ID,
                    "schema_version": CANDIDATE_EVIDENCE_SCHEMA_VERSION,
                },
                created_at=created_at,
            )
            record = self.artifact_service.publish_indexed_json(
                spec,
                bundle.payload,
                lease_fence=lease_fence,
                now_epoch_us=now_epoch_us,
            )
            if self.artifact_reader.get_artifact(record.artifact_id) != record:
                _selection_integrity("candidate_evidence_artifact_index_drift")
            records.append(record)
        return tuple(records)


@dataclass(frozen=True, slots=True)
class DurableSelectionEvidenceService:
    """Rebuild, publish, and verify one content-addressed selection ledger."""

    scheduler_store: _SelectionEvidenceStore
    reader: _SelectionEvidenceReader
    artifact_service: ResearchArtifactService
    walk_forward_assembler: WalkForwardEvidenceAssembler

    def publish_selection_evidence(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> PublishedSelectionEvidence:
        """Publish the candidate-selection ledger and verify its exact replay."""
        if type(snapshot) is not ExperimentSchedulerSnapshot:
            _selection_error("selection_evidence_stage_invalid")
        authoritative = self.scheduler_store.load_snapshot(
            snapshot.projection.record.experiment_id
        )
        if (
            type(authoritative) is not ExperimentSchedulerSnapshot
            or authoritative != snapshot
        ):
            _selection_integrity("selection_evidence_publish_snapshot_drift")
        rebuilt = self._rebuild(authoritative, require_publish_stage=True)
        _CandidateEvidenceBundlePublisher(
            artifact_service=self.artifact_service,
            artifact_reader=self.reader,
        ).publish(
            rebuilt.collected,
            authoritative,
            comparison_revision=rebuilt.selection_stage_subject_revision,
            created_at=rebuilt.created_at,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )
        record = self.artifact_service.publish_indexed_json(
            rebuilt.publication_spec,
            rebuilt.ledger.canonical_payload(),
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )
        verified = self._read_rebuilt(
            rebuilt,
            expected_content_hash=rebuilt.ledger.content_hash,
        )
        indexed = self.reader.get_artifact(record.artifact_id)
        if indexed != record or verified.ledger != rebuilt.ledger:
            _selection_integrity("selection_evidence_publication_replay_mismatch")
        return verified

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        """Rebuild and read one exact typed ledger from immutable evidence."""
        return self._read_rebuilt(
            self._rebuild(
                self.scheduler_store.load_snapshot(experiment_id),
                require_publish_stage=False,
            ),
            expected_content_hash=expected_content_hash,
        )

    def load_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> TrialLedger:
        """Load a snapshot after restart and return its verified typed ledger."""
        return self.read_selection_evidence(
            experiment_id,
            expected_content_hash,
        ).ledger

    def _rebuild(
        self,
        snapshot: ExperimentSchedulerSnapshot,
        *,
        require_publish_stage: bool,
    ) -> _RebuiltSelectionEvidence:
        if type(snapshot) is not ExperimentSchedulerSnapshot:
            _selection_error("selection_evidence_stage_invalid")
        stage = snapshot.projection.record.stage
        if (
            require_publish_stage and stage is not ExperimentStage.CANDIDATE_SELECTION
        ) or (not require_publish_stage and stage not in _READABLE_STAGES):
            _selection_error("selection_evidence_stage_invalid")
        experiment_id = snapshot.projection.record.experiment_id
        events = self.reader.list_status_events(experiment_id)
        selection_event = _selection_stage_event(
            events,
            experiment_id,
        )
        if selection_event.subject_revision > snapshot.projection.revision:
            _selection_integrity(
                "selection_evidence_stage_event_future_revision",
                selection_stage_subject_revision=selection_event.subject_revision,
                projection_revision=snapshot.projection.revision,
            )
        detail = read_unique_preflight_detail(events, experiment_id)
        collected = self.walk_forward_assembler.assemble(
            snapshot,
            project_snapshot_manifest(detail),
        )
        outcomes = project_walk_forward_trial_outcomes(
            snapshot.launch_spec,
            collected.aggregation,
            prior_outcomes=(),
        )
        ledger = build_trial_ledger(
            snapshot.launch_spec.promotion_objective,
            outcomes,
            pbo_combination_budget=MAX_PBO_COMBINATIONS,
        )
        launch_hash = encode_launch_spec(snapshot.launch_spec).content_hash
        objective = snapshot.launch_spec.promotion_objective
        reproduction_fingerprint = canonical_payload(
            {
                "schema_id": "ditto.r3.selection-evidence-reproduction",
                "schema_version": 1,
                "launch_spec_hash": str(launch_hash),
                "aggregation_hash": str(collected.aggregation.content_hash),
                "prior_evidence_policy": _PRIOR_EVIDENCE_POLICY,
                "prior_declaration_hashes": [
                    str(item.outcome_content_hash)
                    for item in objective.prior_trial_evidence
                ],
                "pbo_combination_budget": MAX_PBO_COMBINATIONS,
            }
        ).content_hash
        return _RebuiltSelectionEvidence(
            snapshot,
            ledger,
            reproduction_fingerprint,
            launch_hash,
            collected.aggregation.content_hash,
            selection_event.occurred_at,
            selection_event.event_id,
            selection_event.subject_revision,
            collected,
        )

    def _read_rebuilt(
        self,
        rebuilt: _RebuiltSelectionEvidence,
        *,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        if (
            type(expected_content_hash) is not ContentHash
            or expected_content_hash != rebuilt.ledger.content_hash
        ):
            if (
                rebuilt.snapshot.projection.record.stage
                is not ExperimentStage.CANDIDATE_SELECTION
            ):
                _selection_integrity(
                    "selection_evidence_claim_hash_mismatch",
                    expected_content_hash=str(expected_content_hash),
                    rebuilt_content_hash=str(rebuilt.ledger.content_hash),
                )
            _selection_error(
                "selection_evidence_expected_hash_mismatch",
                expected_content_hash=str(expected_content_hash),
                rebuilt_content_hash=str(rebuilt.ledger.content_hash),
            )
        record_by_id = self.reader.get_artifact(rebuilt.artifact_id)
        record_by_path = self.reader.get_artifact_by_relative_path(
            rebuilt.relative_path
        )
        if record_by_id is None and record_by_path is None:
            if (
                rebuilt.snapshot.projection.record.stage
                is not ExperimentStage.CANDIDATE_SELECTION
            ):
                _selection_integrity(
                    "selection_evidence_artifact_missing_after_holdout"
                )
            _selection_error("selection_evidence_artifact_not_published")
        if (
            record_by_id is None
            or record_by_path is None
            or record_by_id != record_by_path
        ):
            _selection_integrity("selection_evidence_index_identity_conflict")
        record = record_by_id
        self._verify_record(rebuilt, record)
        try:
            decoded = self.artifact_service.read_indexed_json(record.artifact_id)
            verified_bytes = self.artifact_service.read_indexed_artifact_bytes(
                record.artifact_id
            )
        except ExperimentIntegrityError as exc:
            integrity_reason = exc.details.get("reason_code", "unknown")
            _selection_integrity(
                "selection_evidence_verified_read_failed",
                storage_reason=integrity_reason,
            )
        payload = rebuilt.ledger.canonical_payload()
        canonical = canonical_payload(payload)
        if decoded != payload or verified_bytes != canonical.json_bytes:
            _selection_integrity("selection_evidence_payload_parity_mismatch")
        return PublishedSelectionEvidence(record, rebuilt.ledger)

    @staticmethod
    def _verify_record(
        rebuilt: _RebuiltSelectionEvidence,
        record: ArtifactRecord,
    ) -> None:
        expected_spec = rebuilt.publication_spec
        canonical = canonical_payload(rebuilt.ledger.canonical_payload())
        measurement = measure_json_bytes(canonical.json_bytes)
        try:
            observed_spec = ArtifactManifest.from_record(record).spec
        except ExperimentIntegrityError:
            _selection_integrity("selection_evidence_record_parity_mismatch")
        if (
            type(record) is not ArtifactRecord
            or observed_spec != expected_spec
            or record.artifact_id != expected_spec.artifact_id
            or record.experiment_id != expected_spec.experiment_id
            or record.candidate_id is not None
            or record.fold_id is not None
            or record.attempt_id is not None
            or record.artifact_kind != expected_spec.artifact_kind
            or record.relative_path != expected_spec.relative_path
            or record.reproduction_fingerprint != expected_spec.reproduction_fingerprint
            or record.created_at != expected_spec.created_at
            or record.content_hash != rebuilt.ledger.content_hash
            or record.content_hash != measurement.content_hash
            or record.schema_hash != measurement.schema_hash
            or record.row_count != measurement.row_count
            or record.byte_size != measurement.byte_size
        ):
            _selection_integrity("selection_evidence_record_parity_mismatch")
