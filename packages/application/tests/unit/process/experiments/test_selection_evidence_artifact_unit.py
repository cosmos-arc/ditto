"""Unit tests for durable pre-holdout selection evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import (
    ContentHash,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentStage,
    ExperimentStatus,
    LeaseFence,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.experiments.trial_ledger import (
    MAX_PBO_COMBINATIONS,
    TrialLedger,
    build_trial_ledger,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._selection_evidence_artifact import (
    DurableSelectionEvidenceService,
    PublishedSelectionEvidence,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)
from ditto_application.processes.experiments.trial_evidence_bridge import (
    project_walk_forward_trial_outcomes,
)

from .walk_forward_evidence_collection_fixtures import (
    EXPERIMENT_ID,
    NOW,
    NOW_US,
    EvidenceCase,
    MemoryArtifactIndex,
    Resolver,
    build_case,
)

SELECTION_AT = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
LEASE_FENCE = LeaseFence(
    EXPERIMENT_ID,
    "selection-owner",
    3,
    NOW_US + 60_000_000,
)


def _preflight_event() -> StatusEventRecord:
    detail = {
        "preflight": {
            "executor": {"node_registry_manifest_hash": "f" * 64},
            "authority": {
                "snapshot_identity": {
                    "snapshot_id": "snapshot-r3",
                    "manifest_hash": "a" * 64,
                },
            },
            "identities": {
                "certification": {
                    "ready": True,
                    "snapshot_evidence": {"known_at_policy": "sample_time"},
                },
            },
        },
    }
    return StatusEventRecord(
        event_id="status:preflight-1",
        experiment_id=EXPERIMENT_ID,
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        subject_type=StatusSubjectType.EXPERIMENT,
        subject_revision=1,
        previous_status=ExperimentStatus.DRAFT,
        status=ExperimentStatus.QUEUED,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.PREFLIGHT,
        failure_code=None,
        reason_code="preflight_passed",
        detail=detail,
        detail_hash=canonical_payload(detail).content_hash,
        occurred_at=NOW,
    )


def _selection_event() -> StatusEventRecord:
    detail = {"completed_stage": ExperimentStage.WALK_FORWARD.value}
    return StatusEventRecord(
        event_id="status:candidate-selection",
        experiment_id=EXPERIMENT_ID,
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        subject_type=StatusSubjectType.EXPERIMENT,
        subject_revision=4,
        previous_status=ExperimentStatus.RUNNING,
        status=ExperimentStatus.RUNNING,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.CANDIDATE_SELECTION,
        failure_code=None,
        reason_code="scheduler_stage_complete",
        detail=detail,
        detail_hash=canonical_payload(detail).content_hash,
        occurred_at=SELECTION_AT,
    )


def _selection_snapshot(case: EvidenceCase) -> ExperimentSchedulerSnapshot:
    snapshot = case.snapshot()
    return replace(
        snapshot,
        projection=replace(
            snapshot.projection,
            record=replace(
                snapshot.projection.record,
                stage=ExperimentStage.CANDIDATE_SELECTION,
            ),
            revision=4,
            updated_at=SELECTION_AT,
        ),
    )


class _Store:
    def __init__(self, snapshot: ExperimentSchedulerSnapshot) -> None:
        self.snapshot = snapshot

    def load_snapshot(self, experiment_id):
        assert experiment_id == EXPERIMENT_ID
        return self.snapshot


class _Reader:
    def __init__(
        self,
        index: MemoryArtifactIndex,
        events: tuple[StatusEventRecord, ...] = (
            _preflight_event(),
            _selection_event(),
        ),
    ) -> None:
        self._index = index
        self._events = events

    @property
    def artifact_root(self) -> Path:
        return self._index.artifact_root

    def list_status_events(self, experiment_id):
        assert experiment_id == EXPERIMENT_ID
        return self._events

    def get_artifact(self, artifact_id):
        return self._index.get_artifact(artifact_id)

    def get_artifact_by_relative_path(self, relative_path):
        return self._index.get_artifact_by_relative_path(relative_path)


def _service(
    tmp_path: Path,
    case: EvidenceCase,
    snapshot: ExperimentSchedulerSnapshot,
    *,
    events: tuple[StatusEventRecord, ...] | None = None,
) -> DurableSelectionEvidenceService:
    reader = _Reader(case.index) if events is None else _Reader(case.index, events)
    return DurableSelectionEvidenceService(
        scheduler_store=_Store(snapshot),
        reader=reader,
        artifact_service=ResearchArtifactService(
            artifact_root=tmp_path,
            artifact_reader=case.index,
            artifact_writer=case.index,
        ),
        walk_forward_assembler=WalkForwardEvidenceAssembler(
            report_reader=case.adapter,
            fold_selection_trace_reader=case.trace_adapter,
            semantics_resolver=Resolver(case.semantics),
        ),
    )


def test_publish_replay_and_restart_load_return_exact_typed_ledger(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)

    first = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    replay = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    restarted = _service(tmp_path, case, snapshot)
    ledger = restarted.load_selection_evidence(
        EXPERIMENT_ID,
        first.record.content_hash,
    )

    assert replay == first
    record = first.record
    assert record.artifact_id == f"selection-evidence-{ledger.content_hash}"
    assert record.artifact_kind == "selection_evidence"
    assert record.relative_path == (
        f"experiments/{EXPERIMENT_ID}/selection-evidence.json"
    )
    assert record.candidate_id is None
    assert record.fold_id is None
    assert record.attempt_id is None
    assert record.created_at == SELECTION_AT
    assert record.content_hash == ledger.content_hash
    assert type(ledger) is TrialLedger

    collected = case.assemble()
    expected_fingerprint = canonical_payload(
        {
            "schema_id": "ditto.r3.selection-evidence-reproduction",
            "schema_version": 1,
            "launch_spec_hash": str(
                encode_launch_spec(snapshot.launch_spec).content_hash
            ),
            "aggregation_hash": str(collected.aggregation.content_hash),
            "prior_evidence_policy": "missing-is-failed-v1",
            "prior_declaration_hashes": [],
            "pbo_combination_budget": MAX_PBO_COMBINATIONS,
        }
    ).content_hash
    assert record.reproduction_fingerprint == expected_fingerprint
    audit = record.manifest["audit"]
    assert audit["launch_spec_hash"] == str(
        encode_launch_spec(snapshot.launch_spec).content_hash
    )
    assert audit["aggregation_hash"] == str(collected.aggregation.content_hash)
    assert audit["declared_trial_count"] == ledger.declared_trial_count
    assert audit["observed_trial_count"] == ledger.observed_trial_count
    assert audit["failed_trial_count"] == ledger.failed_trial_count
    assert audit["prior_evidence_policy"] == "missing-is-failed-v1"
    assert audit["pbo_combination_budget"] == MAX_PBO_COMBINATIONS
    assert audit["selection_stage_event_id"] == _selection_event().event_id
    assert (
        audit["selection_stage_subject_revision"] == _selection_event().subject_revision
    )


def test_published_pair_rejects_detached_artifact_identity(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    published = _service(tmp_path, case, snapshot).publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )

    with pytest.raises(ExperimentIntegrityError) as captured:
        PublishedSelectionEvidence(
            replace(published.record, artifact_kind="other"),
            published.ledger,
        )

    assert (
        captured.value.details["reason"] == "selection_evidence_published_pair_mismatch"
    )


def test_publish_rejects_non_candidate_selection_snapshot(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    snapshot = case.snapshot()
    service = _service(tmp_path, case, snapshot)

    with pytest.raises(AppProcessError) as captured:
        service.publish_selection_evidence(
            snapshot,
            lease_fence=LEASE_FENCE,
            now_epoch_us=NOW_US,
        )

    assert captured.value.details["reason"] == "selection_evidence_stage_invalid"


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        (
            (_preflight_event(),),
            "selection_evidence_stage_event_not_found",
        ),
        (
            (
                _preflight_event(),
                _selection_event(),
                replace(_selection_event(), event_id="status:candidate-selection-2"),
            ),
            "selection_evidence_stage_event_not_unique",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    detail={"completed_stage": "exploration"},
                    detail_hash=canonical_payload(
                        {"completed_stage": "exploration"}
                    ).content_hash,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    previous_status=ExperimentStatus.QUEUED,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    status=ExperimentStatus.PAUSED,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    desired_state=ExperimentDesiredState.PAUSE,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    failure_code=ExperimentFailureCode.SYSTEM_ERROR,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
        (
            (
                _preflight_event(),
                replace(
                    _selection_event(),
                    subject_type=StatusSubjectType.FOLD,
                ),
            ),
            "selection_evidence_stage_event_drift",
        ),
    ],
)
def test_publish_requires_one_exact_candidate_selection_event(
    tmp_path: Path,
    events: tuple[StatusEventRecord, ...],
    reason: str,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot, events=events)

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.publish_selection_evidence(
            snapshot,
            lease_fence=LEASE_FENCE,
            now_epoch_us=NOW_US,
        )

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert captured.value.details["reason"] == reason


def test_publish_after_control_revision_reuses_stage_event_identity(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    snapshot = replace(
        snapshot,
        projection=replace(
            snapshot.projection,
            revision=7,
            updated_at=datetime(2026, 7, 27, 9, 31, tzinfo=UTC),
        ),
    )
    service = _service(tmp_path, case, snapshot)

    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )

    assert published.record.created_at == SELECTION_AT
    audit = published.record.manifest["audit"]
    assert (
        audit["selection_stage_subject_revision"] == _selection_event().subject_revision
    )


def test_publish_rejects_stage_event_from_future_projection_revision(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    future_event = replace(
        _selection_event(),
        event_id="status:candidate-selection-future",
        subject_revision=snapshot.projection.revision + 1,
    )
    service = _service(
        tmp_path,
        case,
        snapshot,
        events=(_preflight_event(), future_event),
    )

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.publish_selection_evidence(
            snapshot,
            lease_fence=LEASE_FENCE,
            now_epoch_us=NOW_US,
        )

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"]
        == "selection_evidence_stage_event_future_revision"
    )


def test_publish_rejects_typed_snapshot_not_equal_to_authoritative_reload(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    authoritative = _selection_snapshot(case)
    service = _service(tmp_path, case, authoritative)
    forged = replace(authoritative, folds=tuple(reversed(authoritative.folds)))

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.publish_selection_evidence(
            forged,
            lease_fence=LEASE_FENCE,
            now_epoch_us=NOW_US,
        )

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"] == "selection_evidence_publish_snapshot_drift"
    )


def test_load_rejects_expected_hash_drift_before_artifact_read(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )

    with pytest.raises(AppProcessError) as captured:
        service.load_selection_evidence(
            EXPERIMENT_ID,
            ContentHash("0" * 64),
        )

    assert (
        captured.value.details["reason"] == "selection_evidence_expected_hash_mismatch"
    )


def test_later_stage_claim_hash_drift_is_integrity_failure(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    selection_snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, selection_snapshot)
    service.publish_selection_evidence(
        selection_snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    holdout_snapshot = replace(
        selection_snapshot,
        projection=replace(
            selection_snapshot.projection,
            record=replace(
                selection_snapshot.projection.record,
                stage=ExperimentStage.HOLDOUT,
            ),
        ),
    )
    restarted = _service(tmp_path, case, holdout_snapshot)

    with pytest.raises(ExperimentIntegrityError) as captured:
        restarted.load_selection_evidence(
            EXPERIMENT_ID,
            ContentHash("0" * 64),
        )

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert captured.value.details["reason"] == "selection_evidence_claim_hash_mismatch"


@pytest.mark.parametrize(
    "later_stage",
    [ExperimentStage.HOLDOUT, ExperimentStage.EVIDENCE],
)
def test_later_stage_restart_reuses_candidate_selection_timestamp(
    tmp_path: Path,
    later_stage: ExperimentStage,
) -> None:
    case = build_case(tmp_path)
    selection_snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, selection_snapshot)
    published = service.publish_selection_evidence(
        selection_snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    later_snapshot = replace(
        selection_snapshot,
        projection=replace(
            selection_snapshot.projection,
            record=replace(
                selection_snapshot.projection.record,
                stage=later_stage,
            ),
            updated_at=datetime(2026, 7, 28, 9, tzinfo=UTC),
        ),
    )
    restarted = _service(tmp_path, case, later_snapshot)

    verified = restarted.read_selection_evidence(
        EXPERIMENT_ID,
        published.record.content_hash,
    )

    assert verified == published
    assert verified.record.created_at == SELECTION_AT
    assert type(verified.ledger) is TrialLedger


def test_load_reports_not_published_when_both_index_lookups_are_empty(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    ledger = case.assemble()
    expected = build_trial_ledger(
        snapshot.launch_spec.promotion_objective,
        project_walk_forward_trial_outcomes(
            snapshot.launch_spec,
            ledger.aggregation,
            prior_outcomes=(),
        ),
    ).content_hash

    with pytest.raises(AppProcessError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, expected)

    assert (
        captured.value.details["reason"] == "selection_evidence_artifact_not_published"
    )


@pytest.mark.parametrize(
    "later_stage",
    [ExperimentStage.HOLDOUT, ExperimentStage.EVIDENCE],
)
def test_later_stage_missing_selection_artifact_is_integrity_failure(
    tmp_path: Path,
    later_stage: ExperimentStage,
) -> None:
    case = build_case(tmp_path)
    selection_snapshot = _selection_snapshot(case)
    later_snapshot = replace(
        selection_snapshot,
        projection=replace(
            selection_snapshot.projection,
            record=replace(
                selection_snapshot.projection.record,
                stage=later_stage,
            ),
        ),
    )
    service = _service(tmp_path, case, later_snapshot)
    collected = case.assemble()
    expected = build_trial_ledger(
        later_snapshot.launch_spec.promotion_objective,
        project_walk_forward_trial_outcomes(
            later_snapshot.launch_spec,
            collected.aggregation,
            prior_outcomes=(),
        ),
    ).content_hash

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, expected)

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"]
        == "selection_evidence_artifact_missing_after_holdout"
    )


def test_id_and_path_lookup_conflict_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    record = published.record
    case.index.records[record.artifact_id] = replace(
        record,
        relative_path=f"experiments/{EXPERIMENT_ID}/other.json",
    )
    case.index.records["path-owner"] = record

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, record.content_hash)

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"] == "selection_evidence_index_identity_conflict"
    )


def test_corrupt_artifact_bytes_preserve_outer_integrity_reason(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    record = published.record
    (tmp_path / record.relative_path).write_bytes(b"{}")

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, record.content_hash)

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert captured.value.details["reason"] == "selection_evidence_verified_read_failed"
    assert captured.value.details["storage_reason"] == "artifact_content_mismatch"


class _DecodedPayloadDrift:
    def __init__(self, delegate: ResearchArtifactService) -> None:
        self._delegate = delegate

    def read_indexed_json(self, artifact_id: str) -> dict[str, object]:
        _ = artifact_id
        return {"schema_id": "tampered"}

    def read_indexed_artifact_bytes(self, artifact_id: str) -> bytes:
        return self._delegate.read_indexed_artifact_bytes(artifact_id)


def test_verified_decoder_payload_drift_fails_payload_parity(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    drifted = replace(
        service,
        artifact_service=cast(
            "ResearchArtifactService",
            _DecodedPayloadDrift(service.artifact_service),
        ),
    )

    with pytest.raises(ExperimentIntegrityError) as captured:
        drifted.load_selection_evidence(
            EXPERIMENT_ID,
            published.record.content_hash,
        )

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"] == "selection_evidence_payload_parity_mismatch"
    )


def test_corrupt_manifest_fails_record_spec_parity(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    record = published.record
    case.index.records[record.artifact_id] = replace(
        record,
        manifest={"schema_version": 1},
    )

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, record.content_hash)

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"] == "selection_evidence_record_parity_mismatch"
    )


def test_rehashed_manifest_audit_drift_fails_record_spec_parity(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _selection_snapshot(case)
    service = _service(tmp_path, case, snapshot)
    published = service.publish_selection_evidence(
        snapshot,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
    )
    record = published.record
    audit = dict(record.manifest["audit"])
    audit["tampered"] = True
    drifted_spec = ArtifactPublicationSpec(
        artifact_id=record.artifact_id,
        experiment_id=record.experiment_id,
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        artifact_kind=record.artifact_kind,
        relative_path=record.relative_path,
        reproduction_fingerprint=record.reproduction_fingerprint,
        audit=audit,
        created_at=record.created_at,
    )
    case.index.records[record.artifact_id] = ArtifactManifest.create(
        spec=drifted_spec,
        artifact_format=ArtifactFormat.JSON,
        content_hash=record.content_hash,
        schema_hash=record.schema_hash,
        row_count=record.row_count,
        byte_size=record.byte_size,
    ).to_record()

    with pytest.raises(ExperimentIntegrityError) as captured:
        service.load_selection_evidence(EXPERIMENT_ID, record.content_hash)

    assert (
        captured.value.details["reason_code"]
        == "selection_evidence_artifact_integrity_mismatch"
    )
    assert (
        captured.value.details["reason"] == "selection_evidence_record_parity_mismatch"
    )
