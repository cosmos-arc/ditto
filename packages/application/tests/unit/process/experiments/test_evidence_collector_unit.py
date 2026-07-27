# pyright: reportPrivateUsage=false
"""Unit tests for real R3 evidence collection and review-packet publication."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS,
    ArtifactRecord,
    ContentHash,
    DateWindow,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
    GateLayer,
    GateOutcome,
    HardGateEvidenceView,
    LeaseFence,
    ResearchMetricId,
    ResearchMetricValue,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    collect_hard_gate_evidence,
    evaluate_hard_gates,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    evidence_collector as collector_module,
)
from ditto_application.processes.experiments._holdout_contract import (
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
    _artifact_complete,
    _metric_values,
    _purge_embargo_configured,
    _validate_holdout_claim_lineage,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)

from .walk_forward_evidence_collection_fixtures import (
    CANDIDATE_ID,
    EXPERIMENT_ID,
    NOW,
    NOW_US,
    EvidenceCase,
    Resolver,
    artifact_identity,
    build_case,
)

CREATED_AT = datetime(2026, 7, 27, 10, tzinfo=UTC)
LEASE_FENCE = LeaseFence(
    EXPERIMENT_ID,
    "evidence-owner",
    7,
    NOW_US + 60_000_000,
)


def _claim(snapshot: ExperimentSchedulerSnapshot) -> PersistedHoldoutClaim:
    selected = next(
        item
        for item in snapshot.launch_spec.candidates
        if item.candidate_id == CANDIDATE_ID
    )
    binding = next(
        item
        for item in snapshot.launch_spec.execution_bindings
        if item.candidate_id == CANDIDATE_ID
    )
    return PersistedHoldoutClaim(
        claim_id="holdout-claim-1",
        experiment_id=str(EXPERIMENT_ID),
        candidate_id=str(CANDIDATE_ID),
        fold_id="holdout-fold",
        logical_run_id="holdout-logical-run",
        reproduction_fingerprint="5" * 64,
        claim_payload_hash="6" * 64,
        selection_evidence_hash="7" * 64,
        resolved_spec_hash=str(binding.resolved_spec_hash),
        parameters_hash=str(selected.parameter_hash),
        snapshot_id=str(snapshot.launch_spec.snapshot_id),
        window_start="2026-01-01",
        window_end="2026-12-31",
        experiment_revision=6,
        event_id="status:holdout-claim",
        claimed_at=NOW,
    )


def _snapshot(case: EvidenceCase) -> ExperimentSchedulerSnapshot:
    snapshot = case.snapshot()
    key = FoldKey(
        EXPERIMENT_ID,
        CANDIDATE_ID,
        FoldId("holdout-fold"),
    )
    holdout = FoldView(
        FoldPersistenceSpec.create(
            key,
            4,
            FoldRole.HOLDOUT,
            None,
            DateWindow(date(2026, 1, 1), date(2026, 12, 31)),
            1,
            1,
        ),
        FoldProjection(
            key,
            ExperimentStatus.QUEUED,
            None,
            NOW,
            NOW,
            1,
        ),
    )
    return replace(
        snapshot,
        folds=(*snapshot.folds, holdout),
        holdout_claim=_claim(snapshot),
    )


def _preflight_detail() -> dict[str, object]:
    return {
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
                    "snapshot_evidence": {
                        "known_at_policy": "sample_time",
                    },
                },
            },
        },
    }


def _preflight_event(*, event_id: str = "status:preflight-1") -> StatusEventRecord:
    detail = _preflight_detail()
    return StatusEventRecord(
        event_id=event_id,
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


def _review_artifact() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id="review-packet-1",
        experiment_id=EXPERIMENT_ID,
        candidate_id=CANDIDATE_ID,
        fold_id=None,
        attempt_id=None,
        artifact_kind="review_packet",
        relative_path="artifacts/review/packet.json",
        content_hash=ContentHash("8" * 64),
        schema_hash=ContentHash("9" * 64),
        row_count=0,
        byte_size=0,
        reproduction_fingerprint=ContentHash("0" * 64),
        manifest={},
        is_pinned=False,
        pinned_at=None,
        created_at=CREATED_AT,
        revision=1,
    )


class _Store:
    def __init__(self, snapshot: ExperimentSchedulerSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[ExperimentId] = []

    def load_snapshot(self, experiment_id: ExperimentId) -> ExperimentSchedulerSnapshot:
        self.calls.append(experiment_id)
        return self.snapshot


class _Reader:
    def __init__(self, events: tuple[StatusEventRecord, ...]) -> None:
        self.events = events
        self.calls: list[ExperimentId] = []

    def list_status_events(
        self,
        experiment_id: ExperimentId,
    ) -> tuple[StatusEventRecord, ...]:
        self.calls.append(experiment_id)
        return self.events


class _Writer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def publish_review_packet(
        self,
        packet: Any,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        created_at: datetime,
    ) -> ArtifactRecord:
        self.calls.append(
            {
                "packet": packet,
                "lease_fence": lease_fence,
                "now_epoch_us": now_epoch_us,
                "created_at": created_at,
            }
        )
        return _review_artifact()


def _collector(
    monkeypatch: pytest.MonkeyPatch,
    case: EvidenceCase,
    *,
    eligible_month_count: int = 96,
    snapshot: ExperimentSchedulerSnapshot | None = None,
    events: tuple[StatusEventRecord, ...] | None = None,
) -> tuple[ExperimentEvidenceCollector, _Writer, list[object]]:
    reconstructed: list[object] = []

    def _reconstruct(detail: object) -> object:
        reconstructed.append(detail)
        return SimpleNamespace(eligible_month_count=eligible_month_count)

    monkeypatch.setattr(
        collector_module,
        "reconstruct_preflight_report",
        _reconstruct,
    )
    writer = _Writer()
    collector = ExperimentEvidenceCollector(
        scheduler_store=_Store(_snapshot(case) if snapshot is None else snapshot),
        reader=_Reader((_preflight_event(),) if events is None else events),
        writer=writer,
        walk_forward_assembler=WalkForwardEvidenceAssembler(
            report_reader=case.adapter,
            semantics_resolver=Resolver(case.semantics),
        ),
    )
    return collector, writer, reconstructed


def _collect(collector: ExperimentEvidenceCollector) -> Any:
    return collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_US,
        created_at=CREATED_AT,
    )


def _gate(packet: Any, rule_id: str) -> Any:
    return next(item for item in packet.gate_evaluations if item.rule_id == rule_id)


def test_collect_publishes_real_selected_metrics_and_paired_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    expected = case.assemble()
    selected = next(
        item
        for item in expected.aggregation.candidates
        if item.candidate_id == CANDIDATE_ID
    )
    selected_rows = tuple(
        row for row in expected.source_rows if row.candidate_id == CANDIDATE_ID
    )
    collector, writer, reconstructed = _collector(monkeypatch, case)

    packet = _collect(collector)

    assert reconstructed == [_preflight_detail()]
    assert len(writer.calls) == 1
    assert packet.comparison_payload_hash == selected.content_hash
    assert packet.lineage.fold_ids == tuple(str(row.fold_id) for row in selected_rows)
    assert packet.lineage.attempt_ids == tuple(
        str(row.attempt_id) for row in selected_rows
    )
    assert packet.r1_impact_payload_hash is None
    assert packet.selection_evidence_artifact_id is None
    assert _gate(packet, "ninety_six_month_protocol").outcome is GateOutcome.PASS
    assert _gate(packet, "primary_objective_metric").outcome is GateOutcome.PASS
    assert _gate(packet, "primary_objective_metric").observed == pytest.approx(17.6)
    assert (
        _gate(packet, "objective_constraint:max_drawdown").layer is GateLayer.EVIDENCE
    )

    values = _metric_values(selected)
    assert tuple(values) == tuple(
        metric_id
        for metric_id in R3_COMPARISON_METRIC_IDS
        if selected.metrics[metric_id].metric_value is not None
    )
    assert all(type(value) is ResearchMetricValue for value in values.values())
    assert values[ResearchMetricId.NET_RETURN].value == pytest.approx(17.6)


def test_verified_eligible_month_count_drives_ninety_six_month_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        eligible_month_count=95,
    )

    packet = _collect(collector)

    evaluation = _gate(packet, "ninety_six_month_protocol")
    assert evaluation.outcome is GateOutcome.FAIL
    assert evaluation.observed == {"eligible_months": 95, "required": 96}
    assert len(reconstructed) == 1
    assert len(writer.calls) == 1


def test_split_purge_embargo_requires_isolation_on_every_fold(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    fold = case.folds[0]
    no_isolation = replace(
        fold,
        spec=FoldPersistenceSpec.create(
            fold.spec.key,
            fold.spec.ordinal,
            fold.spec.fold_role,
            fold.spec.train_window,
            fold.spec.test_window,
            0,
            0,
        ),
    )
    configured = _purge_embargo_configured((no_isolation, *case.folds[1:]))
    evidence = collect_hard_gate_evidence(
        HardGateEvidenceView(
            certified_snapshot=True,
            snapshot_id="snapshot-r3",
            eligible_month_count=96,
            pit_policy="sample_time",
            purge_embargo_configured=configured,
            reproduction_fingerprints=(ContentHash("a" * 64),),
            cost_config_hash=ContentHash("b" * 64),
            baseline_candidate_id="candidate-baseline",
            trial_count=2,
            expected_trial_count=2,
            holdout_claim_id="claim-1",
            artifact_complete=True,
            artifact_missing=(),
        )
    )

    evaluation = next(
        item
        for item in evaluate_hard_gates(evidence)
        if item.rule_id == "split_purge_embargo"
    )
    assert configured is False
    assert evaluation.outcome is GateOutcome.FAIL


def test_preflight_passed_event_must_be_unique(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        events=(
            _preflight_event(event_id="status:preflight-1"),
            _preflight_event(event_id="status:preflight-2"),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "preflight_passed_event_not_unique"
    assert reconstructed == []
    assert writer.calls == []


def test_preflight_passed_event_must_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        events=(),
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "preflight_passed_event_not_found"
    assert reconstructed == []
    assert writer.calls == []


@pytest.mark.parametrize(
    ("status", "failure_code"),
    [
        (ExperimentStatus.FAILED, ExperimentFailureCode.SYSTEM_ERROR),
        (ExperimentStatus.CANCELLED, None),
    ],
)
def test_selected_candidate_noncompleted_fold_fails_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
) -> None:
    case = build_case(tmp_path)
    selected_index = next(
        index
        for index, fold in enumerate(case.folds)
        if fold.spec.key.candidate_id == CANDIDATE_ID
    )
    fold = case.folds[selected_index]
    attempt = case.attempts[selected_index]
    folds = list(case.folds)
    attempts = list(case.attempts)
    folds[selected_index] = replace(
        fold,
        projection=replace(fold.projection, status=status),
    )
    attempts[selected_index] = replace(
        attempt,
        projection=replace(
            attempt.projection,
            status=status,
            failure_code=failure_code,
        ),
    )
    base = _snapshot(case)
    snapshot = replace(
        base,
        folds=(*folds, base.folds[-1]),
        attempts=tuple(attempts),
    )
    collector, writer, _ = _collector(
        monkeypatch,
        case,
        snapshot=snapshot,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "selected_walk_forward_incomplete"
    assert writer.calls == []


def test_missing_report_publishes_not_evaluated_metrics_and_all_family_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, publish_indices=(0, 1, 2))
    missing_fold = case.folds[3]
    missing_attempt = case.attempts[3]
    collector, writer, _ = _collector(monkeypatch, case)

    packet = _collect(collector)

    artifact_gate = _gate(packet, "artifact_completeness")
    assert artifact_gate.outcome is GateOutcome.FAIL
    assert artifact_gate.observed == {
        "missing": (artifact_identity(missing_fold, missing_attempt).relative_path,),
    }
    assert (
        _gate(packet, "primary_objective_metric").outcome is GateOutcome.NOT_EVALUATED
    )
    assert packet.comparison_payload_hash is not None
    assert len(writer.calls) == 1


def test_missing_baseline_report_is_included_in_all_family_missing_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, publish_indices=(1, 2, 3))
    collector, writer, _ = _collector(monkeypatch, case)

    packet = _collect(collector)

    artifact_gate = _gate(packet, "artifact_completeness")
    assert artifact_gate.outcome is GateOutcome.FAIL
    assert len(artifact_gate.observed["missing"]) == 1
    assert "candidate-baseline" in artifact_gate.observed["missing"][0]
    assert (
        _gate(packet, "primary_objective_metric").outcome is GateOutcome.NOT_EVALUATED
    )
    assert len(writer.calls) == 1


def test_artifact_completeness_requires_every_family_fold_completed(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    failed_baseline = replace(
        case.folds[0],
        projection=replace(
            case.folds[0].projection,
            status=ExperimentStatus.FAILED,
        ),
    )

    assert _artifact_complete(case.folds, ())
    assert not _artifact_complete((failed_baseline, *case.folds[1:]), ())


def test_corrupt_report_fails_closed_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    record = next(iter(case.index.records.values()))
    (tmp_path / record.relative_path).write_bytes(b"corrupt-report")
    collector, writer, _ = _collector(monkeypatch, case)

    with pytest.raises(ExperimentIntegrityError):
        _collect(collector)

    assert writer.calls == []


def test_collect_requires_holdout_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        snapshot=case.snapshot(),
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "evidence_requires_holdout_claim"
    assert reconstructed == []
    assert writer.calls == []


@pytest.mark.parametrize(
    "drift",
    [
        {"candidate_id": "candidate-unknown"},
        {"parameters_hash": "b" * 64},
        {"resolved_spec_hash": "a" * 64},
        {"snapshot_id": "another-snapshot"},
        {"fold_id": "another-holdout-fold"},
        {"window_start": "2025-12-31"},
        {"window_end": "2027-01-01"},
    ],
)
def test_holdout_claim_must_match_selected_launch_and_unique_holdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: dict[str, str],
) -> None:
    case = build_case(tmp_path)
    snapshot = _snapshot(case)
    claim = snapshot.holdout_claim
    assert claim is not None
    drifted = replace(
        snapshot,
        holdout_claim=replace(claim, **drift),
    )
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        snapshot=drifted,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "holdout_claim_evidence_lineage_drift"
    assert reconstructed == []
    assert writer.calls == []


def test_holdout_claim_requires_one_selected_holdout_fold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    snapshot = _snapshot(case)
    original = snapshot.folds[-1]
    duplicate_key = FoldKey(
        EXPERIMENT_ID,
        CANDIDATE_ID,
        FoldId("second-holdout-fold"),
    )
    duplicate = FoldView(
        replace(original.spec, key=duplicate_key),
        replace(original.projection, key=duplicate_key),
    )
    ambiguous = replace(snapshot, folds=(*snapshot.folds, duplicate))
    collector, writer, reconstructed = _collector(
        monkeypatch,
        case,
        snapshot=ambiguous,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _collect(collector)

    assert exc_info.value.details["reason"] == "holdout_claim_evidence_lineage_drift"
    assert reconstructed == []
    assert writer.calls == []


def test_holdout_claim_experiment_identity_is_revalidated(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    snapshot = _snapshot(case)
    claim = snapshot.holdout_claim
    assert claim is not None

    with pytest.raises(AppProcessError) as exc_info:
        _validate_holdout_claim_lineage(
            snapshot,
            replace(claim, experiment_id="another-experiment"),
        )

    assert exc_info.value.details["reason"] == "holdout_claim_evidence_lineage_drift"
