"""Unit tests for the R3 ExperimentEvidenceCollector hard-gate closure."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ConstraintOperator,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentProjection,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldProtocolSpec,
    FoldRole,
    FoldView,
    GateLayer,
    GateOutcome,
    LeaseFence,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StatusEventRecord,
    StatusSubjectType,
    StrategyVersion,
    canonical_payload,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    promotion_objective_content_hash,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._holdout_contract import (
    PersistedHoldoutClaim,
)
from ditto_application.processes.experiments.evidence_collector import (
    ExperimentEvidenceCollector,
    _months_in_window,
    _reproduction_fingerprints,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)

EXPERIMENT_ID = ExperimentId("experiment-r3")
BASELINE_ID = CandidateId("candidate-baseline")
SELECTED_ID = CandidateId("candidate-selected")
FOLD_ID_A = FoldId("wf-a")
FOLD_ID_B = FoldId("wf-b")
ATTEMPT_ID_A = AttemptId("attempt-wf-a")
ATTEMPT_ID_B = AttemptId("attempt-wf-b")
SNAPSHOT_ID = SnapshotId("snapshot-r3")
SNAPSHOT_HASH = ContentHash("a" * 64)
REGISTRY_HASH = ContentHash("f" * 64)
BASELINE_PARAMETER_HASH = ContentHash("b" * 64)
SELECTED_PARAMETER_HASH = ContentHash("c" * 64)
BASELINE_RESOLVED_HASH = ContentHash("1" * 64)
SELECTED_RESOLVED_HASH = ContentHash("2" * 64)
REPRO_FINGERPRINT_A = ContentHash("d" * 64)
REPRO_FINGERPRINT_B = ContentHash("e" * 64)
ARTIFACT_HASH = ContentHash("9" * 64)
SCHEMA_HASH = ContentHash("0" * 64)
NOW = datetime(2024, 3, 1, tzinfo=UTC)
CREATED_AT = datetime(2024, 3, 2, tzinfo=UTC)
NOW_EPOCH_US = 1_709_337_600_000_000
LEASE_FENCE = LeaseFence(
    experiment_id=EXPERIMENT_ID,
    owner_token="coordinator-owner",
    revision=7,
    lease_until_epoch_us=NOW_EPOCH_US + 60_000_000,
)


def _objective(*, selected_parameter_hash: ContentHash) -> PromotionObjective:
    family = TrialFamilyDeclaration(
        "evidence-collector-family",
        (
            LogicalTrialIdentity(
                EXPERIMENT_ID,
                BASELINE_ID,
                1,
                _baseline_parameter_hash(),
                TrialKind.CURRENT,
            ),
            LogicalTrialIdentity(
                EXPERIMENT_ID,
                SELECTED_ID,
                2,
                selected_parameter_hash,
                TrialKind.CURRENT,
            ),
        ),
    )
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(),
        baseline_candidate_id=BASELINE_ID,
        economic_rationale="Capture durable returns after costs.",
        trial_family=family,
    )


def _baseline_parameter_hash() -> ContentHash:
    baseline = CandidateSpec(
        candidate_id=BASELINE_ID,
        ordinal=1,
        is_baseline=True,
        parameters={"lookback": 0},
    )
    return baseline.parameter_hash


def _launch_spec(
    *,
    selected_parameters: dict[str, int] | None = None,
) -> ExperimentLaunchSpec:
    baseline = CandidateSpec(
        candidate_id=BASELINE_ID,
        ordinal=1,
        is_baseline=True,
        parameters={"lookback": 0},
    )
    selected = CandidateSpec(
        candidate_id=SELECTED_ID,
        ordinal=2,
        is_baseline=False,
        parameters=selected_parameters or {"lookback": 20},
    )
    candidates = (baseline, selected)
    return ExperimentLaunchSpec(
        experiment_id=EXPERIMENT_ID,
        strategy_version=StrategyVersion("strategy@1"),
        strategy_spec_hash=ContentHash("3" * 64),
        snapshot_id=SNAPSHOT_ID,
        candidates=candidates,
        execution_bindings=(
            CandidateExecutionBinding(
                BASELINE_ID,
                1,
                baseline.parameter_hash,
                BASELINE_RESOLVED_HASH,
            ),
            CandidateExecutionBinding(
                SELECTED_ID,
                2,
                selected.parameter_hash,
                SELECTED_RESOLVED_HASH,
            ),
        ),
        promotion_objective=_objective(selected_parameter_hash=selected.parameter_hash),
        fold_protocol=FoldProtocolSpec(
            "evidence-collector-fold-protocol",
            1,
            ContentHash("4" * 64),
        ),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


def _fold_view(
    fold_id: FoldId,
    candidate_id: CandidateId,
    *,
    test_window: DateWindow,
    purge_sessions: int,
    embargo_sessions: int,
) -> FoldView:
    key = FoldKey(EXPERIMENT_ID, candidate_id, fold_id)
    spec = FoldPersistenceSpec.create(
        key,
        1,
        FoldRole.WALK_FORWARD,
        None,
        test_window,
        purge_sessions,
        embargo_sessions,
    )
    return FoldView(
        spec,
        FoldProjection(
            key=key,
            status=ExperimentStatus.COMPLETED,
            claim_owner_token=None,
            created_at=NOW,
            updated_at=NOW,
            revision=1,
        ),
    )


def _attempt_view(
    attempt_id: AttemptId,
    fold_id: FoldId,
    candidate_id: CandidateId,
    *,
    fingerprint: ContentHash,
) -> AttemptView:
    fold_key = FoldKey(EXPERIMENT_ID, candidate_id, fold_id)
    return AttemptView(
        AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=fold_key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=fingerprint,
            created_at=NOW,
        ),
        AttemptProjection(
            attempt_id=attempt_id,
            status=ExperimentStatus.COMPLETED,
            backtest_run_id=BacktestRunId(f"run-{attempt_id.value}"),
            checkpoint_ref=None,
            failure_code=None,
            created_at=NOW,
            updated_at=NOW,
            revision=1,
        ),
    )


def _holdout_claim() -> PersistedHoldoutClaim:
    return PersistedHoldoutClaim(
        claim_id="holdout-claim-1",
        experiment_id=str(EXPERIMENT_ID),
        candidate_id=str(SELECTED_ID),
        fold_id="holdout-fold",
        logical_run_id="holdout-logical-run",
        reproduction_fingerprint=str(REPRO_FINGERPRINT_A),
        claim_payload_hash=str(ContentHash("5" * 64)),
        selection_evidence_hash=str(ContentHash("6" * 64)),
        resolved_spec_hash=str(SELECTED_RESOLVED_HASH),
        parameters_hash=str(SELECTED_PARAMETER_HASH),
        snapshot_id=str(SNAPSHOT_ID),
        window_start="2024-01-01",
        window_end="2024-01-31",
        experiment_revision=6,
        event_id="status:holdout-claim",
        claimed_at=NOW,
    )


def _fold_a() -> FoldView:
    return _fold_view(
        FOLD_ID_A,
        SELECTED_ID,
        test_window=DateWindow(
            start=date(2016, 1, 1),
            end=date(2017, 1, 1),
        ),
        purge_sessions=1,
        embargo_sessions=1,
    )


def _fold_b() -> FoldView:
    return _fold_view(
        FOLD_ID_B,
        SELECTED_ID,
        test_window=DateWindow(
            start=date(2017, 1, 2),
            end=date(2024, 1, 1),
        ),
        purge_sessions=1,
        embargo_sessions=0,
    )


def _baseline_fold() -> FoldView:
    """A walk-forward fold for the baseline candidate to exercise the
    artifact-complete proxy across all candidates."""
    return _fold_view(
        FoldId("wf-baseline"),
        BASELINE_ID,
        test_window=DateWindow(
            start=date(2016, 1, 1),
            end=date(2017, 1, 1),
        ),
        purge_sessions=1,
        embargo_sessions=0,
    )


def _baseline_attempt() -> AttemptView:
    return _attempt_view(
        AttemptId("attempt-baseline-wf"),
        FoldId("wf-baseline"),
        BASELINE_ID,
        fingerprint=ContentHash("bb" * 32),
    )


def _snapshot(
    *, holdout_claim: PersistedHoldoutClaim | None
) -> ExperimentSchedulerSnapshot:

    launch_spec = _launch_spec()
    return ExperimentSchedulerSnapshot(
        projection=ExperimentProjection(
            record=ExperimentRecord(
                experiment_id=EXPERIMENT_ID,
                status=ExperimentStatus.RUNNING,
                desired_state=ExperimentDesiredState.RUN,
                stage=ExperimentStage.EVIDENCE,
                created_at=NOW,
            ),
            queue_ordinal=1,
            revision=7,
            updated_at=NOW,
        ),
        launch_spec=launch_spec,
        folds=(
            _fold_a(),
            _fold_b(),
            _baseline_fold(),
        ),
        attempts=(
            _attempt_view(
                ATTEMPT_ID_A,
                FOLD_ID_A,
                SELECTED_ID,
                fingerprint=REPRO_FINGERPRINT_A,
            ),
            _attempt_view(
                ATTEMPT_ID_B,
                FOLD_ID_B,
                SELECTED_ID,
                fingerprint=REPRO_FINGERPRINT_B,
            ),
            _baseline_attempt(),
        ),
        holdout_claim=holdout_claim,
    )


def _preflight_detail() -> dict[str, object]:
    return {
        "preflight": {
            "executor": {
                "node_registry_manifest_hash": str(REGISTRY_HASH),
            },
            "authority": {
                "snapshot_identity": {
                    "snapshot_id": str(SNAPSHOT_ID),
                    "manifest_hash": str(SNAPSHOT_HASH),
                },
            },
            "identities": {
                "certification": {
                    "ready": True,
                    "profile": "r3-research-certification",
                    "required_from": "2016-01-01",
                    "required_to": "2024-01-01",
                    "dataset_ids": ["dataset-1"],
                    "report_ids": ["report-1"],
                    "reason_codes": [],
                    "snapshot_evidence": {
                        "snapshot_id": str(SNAPSHOT_ID),
                        "dataset_id": "dataset-1",
                        "manifest_hash": str(SNAPSHOT_HASH),
                        "source_snapshot_ids": [],
                        "snapshot_start": "2016-01-01",
                        "snapshot_end": "2024-01-01",
                        "known_at_policy": "sample_time",
                        "builder_version": "v1",
                    },
                },
            },
        },
    }


def _preflight_event() -> StatusEventRecord:
    detail = _preflight_detail()
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


def _artifact_record() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id="review-packet-1",
        experiment_id=EXPERIMENT_ID,
        candidate_id=SELECTED_ID,
        fold_id=None,
        attempt_id=None,
        artifact_kind="review_packet",
        relative_path="artifacts/review/packet.json",
        content_hash=ContentHash("7" * 64),
        schema_hash=SCHEMA_HASH,
        row_count=0,
        byte_size=0,
        reproduction_fingerprint=ContentHash("8" * 64),
        manifest={},
        is_pinned=False,
        pinned_at=None,
        created_at=CREATED_AT,
        revision=1,
    )


class _StubSchedulerStore:
    def __init__(self, snapshot: ExperimentSchedulerSnapshot) -> None:
        self._snapshot = snapshot
        self.calls: list[ExperimentId] = []

    def load_snapshot(self, experiment_id: ExperimentId) -> ExperimentSchedulerSnapshot:
        self.calls.append(experiment_id)
        return self._snapshot


class _StubReader:
    def __init__(self, events: tuple[StatusEventRecord, ...]) -> None:
        self._events = events
        self.calls: list[ExperimentId] = []

    def list_status_events(
        self, experiment_id: ExperimentId
    ) -> tuple[StatusEventRecord, ...]:
        self.calls.append(experiment_id)
        return self._events


class _StubWriter:
    def __init__(self, artifact: ArtifactRecord) -> None:
        self._artifact = artifact
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
        return self._artifact


def _collector(
    *,
    snapshot: ExperimentSchedulerSnapshot | None = None,
    events: tuple[StatusEventRecord, ...] | None = None,
    artifact: ArtifactRecord | None = None,
) -> tuple[
    ExperimentEvidenceCollector,
    _StubSchedulerStore,
    _StubReader,
    _StubWriter,
]:
    store = _StubSchedulerStore(snapshot or _snapshot(holdout_claim=_holdout_claim()))
    reader = _StubReader(events or (_preflight_event(),))
    writer = _StubWriter(artifact or _artifact_record())
    collector = ExperimentEvidenceCollector(
        scheduler_store=store,
        reader=reader,
        writer=writer,
    )
    return collector, store, reader, writer


def _hard_gate_evaluations(packet: Any) -> tuple[Any, ...]:
    return tuple(
        evaluation
        for evaluation in packet.gate_evaluations
        if evaluation.layer is GateLayer.HARD
    )


def test_collect_assembles_review_packet_hard_gate_only() -> None:
    collector, _, _, _ = _collector()

    packet = collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    assert packet.lineage.experiment_id == str(EXPERIMENT_ID)
    assert packet.lineage.candidate_id == str(SELECTED_ID)
    assert packet.lineage.fold_ids == (str(FOLD_ID_A), str(FOLD_ID_B))
    assert packet.holdout_claim_id == "holdout-claim-1"
    assert packet.comparison_payload_hash is None
    assert packet.r1_impact_payload_hash is None
    assert packet.selection_evidence_artifact_id is None

    hard_evaluations = _hard_gate_evaluations(packet)
    assert len(hard_evaluations) == 11
    r2_live = next(
        evaluation
        for evaluation in hard_evaluations
        if evaluation.rule_id == "r2_live_gate"
    )
    assert r2_live.outcome is GateOutcome.NOT_EVALUATED
    satisfied = [
        evaluation
        for evaluation in hard_evaluations
        if evaluation.outcome is GateOutcome.PASS
    ]
    assert len(satisfied) == 10
    assert {evaluation.rule_id for evaluation in satisfied} == {
        "certified_snapshot",
        "ninety_six_month_protocol",
        "pit_known_at",
        "split_purge_embargo",
        "reproduction_fingerprint",
        "cost_assumptions",
        "baseline_declared",
        "trial_declaration",
        "holdout_claim",
        "artifact_completeness",
    }
    evidence_evaluations = tuple(
        evaluation
        for evaluation in packet.gate_evaluations
        if evaluation.layer is GateLayer.EVIDENCE
    )
    assert all(
        evaluation.outcome is GateOutcome.NOT_EVALUATED
        for evaluation in evidence_evaluations
    )


def test_collect_publishes_via_writer() -> None:
    collector, _, _, writer = _collector()

    collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    assert len(writer.calls) == 1
    call = writer.calls[0]
    assert call["lease_fence"] is LEASE_FENCE
    assert call["now_epoch_us"] == NOW_EPOCH_US
    assert call["created_at"] is CREATED_AT


def test_collect_objective_payload_hash() -> None:
    collector, _, _, _ = _collector()

    packet = collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    expected = promotion_objective_content_hash(_launch_spec().promotion_objective)
    assert packet.objective_payload_hash == expected


def test_collect_candidate_rationale_from_parameter_delta() -> None:
    collector, _, _, _ = _collector(
        snapshot=replace(
            _snapshot(holdout_claim=_holdout_claim()),
            launch_spec=_launch_spec(selected_parameters={"lookback": 20, "depth": 4}),
        ),
    )

    packet = collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    rationale = packet.candidate_rationale
    assert str(SELECTED_ID) in rationale
    assert str(BASELINE_ID) in rationale
    assert "depth" in rationale
    assert "lookback" in rationale


def test_collect_skips_when_no_holdout_claim() -> None:
    collector, _, _, _ = _collector(
        snapshot=_snapshot(holdout_claim=None),
    )

    with pytest.raises(AppProcessError) as exc_info:
        collector.collect(
            EXPERIMENT_ID,
            lease_fence=LEASE_FENCE,
            now_epoch_us=NOW_EPOCH_US,
            created_at=CREATED_AT,
        )

    assert exc_info.value.details["reason"] == "evidence_requires_holdout_claim"


def _non_terminal_attempt(
    attempt_id: AttemptId,
    fold_id: FoldId,
    candidate_id: CandidateId,
    *,
    fingerprint: ContentHash,
    status: ExperimentStatus,
) -> AttemptView:
    """Build an attempt whose projection uses a caller-supplied status."""
    base = _attempt_view(attempt_id, fold_id, candidate_id, fingerprint=fingerprint)
    return replace(
        base,
        projection=AttemptProjection(
            attempt_id=attempt_id,
            status=status,
            backtest_run_id=BacktestRunId(f"run-{attempt_id.value}"),
            checkpoint_ref=None,
            failure_code=None,
            created_at=NOW,
            updated_at=NOW,
            revision=1,
        ),
    )


def _hard_evaluation(packet: Any, rule_id: str) -> Any:
    return next(
        evaluation
        for evaluation in packet.gate_evaluations
        if evaluation.layer is GateLayer.HARD and evaluation.rule_id == rule_id
    )


def test_reproduction_fingerprints_returns_empty_when_no_attempts_match() -> None:
    """Design §9: missing fingerprints return ``()`` instead of raising.

    The integration path through ``collect`` always pairs this helper with
    ``_attempt_ids``, which uses the same fold-key filter; once Task 3b's
    trial-ledger work or a schema relaxation lets the two diverge, an empty
    fingerprint tuple must let the ``reproduction`` gate evaluate to FAIL
    rather than aborting the tick. The unit-level contract is the only way
    to exercise the empty branch while ``ReviewPacketLineage`` still rejects
    empty ``attempt_ids`` tuples.
    """
    selected_folds = (_fold_a(),)
    result = _reproduction_fingerprints(selected_folds, attempts=())
    assert result == ()


def test_attempt_ids_exclude_non_terminal_attempts() -> None:
    """Design §8.4: only COMPLETED attempts bind to the packet lineage."""
    running_id = AttemptId("attempt-running-wf-a")
    running = _non_terminal_attempt(
        running_id,
        FOLD_ID_A,
        SELECTED_ID,
        fingerprint=ContentHash("ab" * 32),
        status=ExperimentStatus.RUNNING,
    )
    snapshot = replace(
        _snapshot(holdout_claim=_holdout_claim()),
        attempts=(
            _attempt_view(
                ATTEMPT_ID_A,
                FOLD_ID_A,
                SELECTED_ID,
                fingerprint=REPRO_FINGERPRINT_A,
            ),
            running,
            _attempt_view(
                ATTEMPT_ID_B,
                FOLD_ID_B,
                SELECTED_ID,
                fingerprint=REPRO_FINGERPRINT_B,
            ),
            _baseline_attempt(),
        ),
    )
    collector, _, _, _ = _collector(snapshot=snapshot)

    packet = collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    lineage_ids = packet.lineage.attempt_ids
    assert str(running_id) not in lineage_ids
    assert str(ATTEMPT_ID_A) in lineage_ids
    assert str(ATTEMPT_ID_B) in lineage_ids


def test_collect_trial_declaration_reads_both_typed_sources() -> None:
    """Design §6: trial_count from candidates, expected from trial_family.

    LaunchSpec invariant (specs.py) keeps ``current_members`` equal to the
    candidate tuple at construction time, so the V1 gate is structurally
    tautological; the test still proves the wiring reads from both typed
    sources so Task 3b's trial-ledger closure can diverge them.
    """
    collector, _, _, _ = _collector()
    launch_spec = _launch_spec()

    packet = collector.collect(
        EXPERIMENT_ID,
        lease_fence=LEASE_FENCE,
        now_epoch_us=NOW_EPOCH_US,
        created_at=CREATED_AT,
    )

    trial_declaration = _hard_evaluation(packet, "trial_declaration")
    observed = trial_declaration.observed
    assert isinstance(observed, dict)
    assert observed["trial_count"] == len(launch_spec.candidates)
    assert observed["expected"] == len(
        launch_spec.promotion_objective.trial_family.current_members
    )
    assert trial_declaration.outcome is GateOutcome.PASS


def test_months_in_window_single_month_window() -> None:
    """Same year/month endpoints span exactly one inclusive month."""
    assert _months_in_window(2016, 1, 2016, 1) == 1


def test_months_in_window_within_year_window() -> None:
    """Inclusive span within one calendar year counts both endpoints."""
    assert _months_in_window(2016, 1, 2016, 6) == 6


def test_months_in_window_cross_year_window() -> None:
    """Cross-year span includes the wrap-around months inclusively."""
    assert _months_in_window(2016, 1, 2017, 1) == 13


def test_months_in_window_cross_multiple_years() -> None:
    """Eight-year span mirrors the ninety-six-month gate threshold."""
    assert _months_in_window(2016, 1, 2024, 1) == 97
