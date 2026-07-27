"""Unit tests for the application-owned holdout claim workflow."""

from __future__ import annotations

from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldProtocolSpec,
    FoldRole,
    FoldView,
    LogicalTrialIdentity,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SchedulerLease,
    SnapshotId,
    StrategyVersion,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    MetricEvidenceLineage,
    ObjectiveMetric,
    PromotionObjective,
    TrialLedger,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.experiments._selection_evidence_artifact import (
    PublishedSelectionEvidence,
)
from ditto_application.processes.experiments.scheduler_store import FirstAttempt

NOW = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)


def _api() -> SimpleNamespace:
    """Import Task 12 application contracts inside each test for true RED."""
    from ditto_application.commands.experiments import (
        ClaimHoldoutCandidateCommand,
        ClaimHoldoutCandidateHandler,
    )
    from ditto_application.processes.experiments.holdout import (
        ClaimHoldoutCandidateRequest,
        HoldoutClaimProcess,
        HoldoutClaimReceipt,
        HoldoutSelectionReason,
    )

    return SimpleNamespace(
        ClaimHoldoutCandidateCommand=ClaimHoldoutCandidateCommand,
        ClaimHoldoutCandidateHandler=ClaimHoldoutCandidateHandler,
        ClaimHoldoutCandidateRequest=ClaimHoldoutCandidateRequest,
        HoldoutClaimProcess=HoldoutClaimProcess,
        HoldoutClaimReceipt=HoldoutClaimReceipt,
        HoldoutSelectionReason=HoldoutSelectionReason,
    )


def _reason(api: SimpleNamespace) -> Any:
    return api.HoldoutSelectionReason(
        code="objective_review",
        summary="Candidate two won the registered objective review.",
    )


def _request(api: SimpleNamespace) -> Any:
    return api.ClaimHoldoutCandidateRequest(
        experiment_id="experiment-1",
        candidate_id="candidate-2",
        expected_revision=7,
        expected_selection_evidence_hash="a" * 64,
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=_reason(api),
        occurred_at=NOW,
    )


def _fold() -> FoldView:
    key = FoldKey(
        ExperimentId("experiment-1"),
        CandidateId("candidate-2"),
        FoldId("holdout-candidate-2"),
    )
    spec = FoldPersistenceSpec.create(
        key,
        4,
        FoldRole.HOLDOUT,
        DateWindow(date(2020, 1, 1), date(2025, 12, 31)),
        DateWindow(date(2026, 1, 1), date(2026, 3, 31)),
        2,
        1,
    )
    return FoldView(
        spec,
        FoldProjection(
            key,
            ExperimentStatus.QUEUED,
            None,
            NOW,
            NOW,
            0,
        ),
    )


def _first_attempt(fold: FoldView) -> FirstAttempt:
    attempt_id = AttemptId("attempt-holdout-candidate-2")
    return FirstAttempt(
        AttemptPersistenceSpec(
            attempt_id,
            fold.spec.key,
            1,
            None,
            None,
            ContentHash("b" * 64),
            NOW,
        ),
        AttemptProjection(
            attempt_id,
            ExperimentStatus.QUEUED,
            None,
            None,
            None,
            NOW,
            NOW,
            0,
        ),
    )


def _persisted() -> SimpleNamespace:
    return SimpleNamespace(
        claim_id="holdout-claim-1",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-2"),
        fold_id=FoldId("holdout-candidate-2"),
        logical_run_id="holdout-logical-run-1",
        reproduction_fingerprint=ContentHash("b" * 64),
        claim_payload_hash=ContentHash("c" * 64),
        selection_evidence_hash=ContentHash("a" * 64),
        experiment_revision=8,
        event_id="status:claim-event",
        claimed_at=NOW,
    )


class _Factory:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        self.calls += 1
        assert occurred_at == NOW
        return _first_attempt(fold)


def _selection_ledger() -> TrialLedger:
    candidates = (
        CandidateSpec(CandidateId("candidate-1"), 1, True, {"lookback": 0}),
        CandidateSpec(CandidateId("candidate-2"), 2, False, {"lookback": 20}),
    )
    trials = tuple(
        LogicalTrialIdentity(
            ExperimentId("experiment-1"),
            candidate.candidate_id,
            candidate.ordinal,
            candidate.parameter_hash,
            TrialKind.CURRENT,
        )
        for candidate in candidates
    )
    family = TrialFamilyDeclaration("holdout-unit-family", trials)
    objective = PromotionObjective(
        ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        (),
        (),
        CandidateId("candidate-1"),
        "Review the registered objective before holdout.",
        family,
    )
    lineage = MetricEvidenceLineage(("comparison://ledger",), (ContentHash("d" * 64),))
    outcomes = tuple(
        TrialOutcome(
            trial=trial,
            status=TrialStatus.COMPLETED,
            metrics={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN,
                    float(trial.ordinal),
                )
            },
            holdout_metrics={},
            source_projection_hash=ContentHash("e" * 64),
            metric_evidence={ResearchMetricId.NET_RETURN: lineage},
        )
        for trial in trials
    )
    return build_trial_ledger(objective, outcomes)


def _published_selection_evidence(ledger: TrialLedger) -> PublishedSelectionEvidence:
    return PublishedSelectionEvidence(
        ArtifactRecord(
            artifact_id=f"selection-evidence-{ledger.content_hash}",
            experiment_id=ExperimentId("experiment-1"),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            artifact_kind="selection_evidence",
            relative_path="experiments/experiment-1/selection-evidence.json",
            content_hash=ledger.content_hash,
            schema_hash=ContentHash("f" * 64),
            row_count=1,
            byte_size=1,
            reproduction_fingerprint=ContentHash("0" * 64),
            manifest={},
            is_pinned=False,
            pinned_at=None,
            created_at=NOW,
            revision=0,
        ),
        ledger,
    )


def _launch_spec() -> ExperimentLaunchSpec:
    ledger = _selection_ledger()
    candidates = (
        CandidateSpec(CandidateId("candidate-1"), 1, True, {"lookback": 0}),
        CandidateSpec(CandidateId("candidate-2"), 2, False, {"lookback": 20}),
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId("experiment-1"),
        strategy_version=StrategyVersion("strategy@1"),
        strategy_spec_hash=ContentHash("1" * 64),
        snapshot_id=SnapshotId("snapshot-holdout-unit"),
        candidates=candidates,
        execution_bindings=tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(f"{candidate.ordinal + 32:064x}"),
            )
            for candidate in candidates
        ),
        promotion_objective=ledger.objective,
        fold_protocol=FoldProtocolSpec("holdout-unit", 1, ContentHash("2" * 64)),
        seed=17,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(128, 512),
        desired_state=ExperimentDesiredState.RUN,
        created_at=NOW,
    )


class _SelectionProvider:
    def __init__(self) -> None:
        self.ledger = _selection_ledger()
        self.published = _published_selection_evidence(self.ledger)
        self.calls: list[tuple[ExperimentId, ContentHash]] = []

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        self.calls.append((experiment_id, expected_content_hash))
        return self.published


class _UnavailableSelectionProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[ExperimentId, ContentHash]] = []
        self.error = AppProcessError(
            "selection evidence is unavailable",
            details={
                "code": "SPEC_INVALID",
                "reason": "selection_evidence_not_published",
            },
        )

    def read_selection_evidence(
        self,
        experiment_id: ExperimentId,
        expected_content_hash: ContentHash,
    ) -> PublishedSelectionEvidence:
        self.calls.append((experiment_id, expected_content_hash))
        raise self.error


class _Store:
    def __init__(self, *, existing: bool = False) -> None:
        self.persisted = _persisted()
        self.snapshot = SimpleNamespace(
            holdout_claim=self.persisted if existing else None,
            launch_spec=_launch_spec(),
            folds=(_fold(),),
        )
        self.calls: list[dict[str, Any]] = []

    def load_snapshot(self, _experiment_id: ExperimentId) -> SimpleNamespace:
        return self.snapshot

    def claim_holdout_candidate(
        self,
        request: Any,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> SimpleNamespace:
        self.calls.append(
            {"request": request, "lease": lease, "now_epoch_us": now_epoch_us}
        )
        return self.persisted


def _lease() -> SchedulerLease:
    return SchedulerLease(
        ExperimentId("experiment-1"),
        "scheduler-owner",
        100,
        1,
        1,
        4,
    )


def test_request_boundary_accepts_only_operator_selection_fields() -> None:
    api = _api()
    request = _request(api)

    assert {item.name for item in fields(request)} == {
        "experiment_id",
        "candidate_id",
        "expected_revision",
        "expected_selection_evidence_hash",
        "operator_confirmation",
        "selection_reason",
        "occurred_at",
    }
    for forbidden in (
        "cycle_id",
        "snapshot_id",
        "fold_id",
        "resolved_spec_hash",
        "parameters_hash",
        "reproduction_fingerprint",
        "logical_run_id",
        "claim_id",
    ):
        assert not hasattr(request, forbidden)


def test_process_resolves_real_fingerprint_before_atomic_store_command() -> None:
    api = _api()
    store = _Store()
    factory = _Factory()
    provider = _SelectionProvider()
    store.persisted.selection_evidence_hash = provider.ledger.content_hash
    request = _request(api)
    request = api.ClaimHoldoutCandidateRequest(
        request.experiment_id,
        request.candidate_id,
        request.expected_revision,
        str(provider.ledger.content_hash),
        request.operator_confirmation,
        request.selection_reason,
        request.occurred_at,
    )
    process = api.HoldoutClaimProcess(
        store=store,
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
    )

    receipt = process.claim_candidate(
        request,
        lease=_lease(),
        now_epoch_us=2,
    )

    assert factory.calls == 1
    assert asdict(store.calls[0]["request"]) == {
        "experiment_id": "experiment-1",
        "candidate_id": "candidate-2",
        "expected_revision": 7,
        "expected_selection_evidence_hash": str(provider.ledger.content_hash),
        "operator_confirmation": "operator reviewed immutable evidence",
        "selection_reason_code": "objective_review",
        "selection_reason_summary": (
            "Candidate two won the registered objective review."
        ),
        "resolved_reproduction_fingerprint": "b" * 64,
        "occurred_at": NOW,
    }
    assert store.calls[0]["lease"] == _lease()
    assert store.calls[0]["now_epoch_us"] == 2
    assert receipt.logical_run_id == "holdout-logical-run-1"
    assert receipt.experiment_revision == 8
    assert provider.calls == [
        (ExperimentId("experiment-1"), provider.ledger.content_hash)
    ]


def test_new_claim_cannot_precede_candidate_selection_evidence() -> None:
    api = _api()
    store = _Store()
    factory = _Factory()
    provider = _SelectionProvider()
    process = api.HoldoutClaimProcess(
        store=store,
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
    )

    with pytest.raises(AppProcessError) as exc_info:
        process.claim_candidate(
            replace(_request(api), occurred_at=NOW - timedelta(microseconds=1)),
            lease=_lease(),
            now_epoch_us=2,
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "holdout_claim_precedes_selection_evidence",
        "selection_evidence_created_at": NOW.isoformat(),
    }
    assert provider.calls == [(ExperimentId("experiment-1"), ContentHash("a" * 64))]
    assert factory.calls == 0
    assert store.calls == []


def test_restart_replay_uses_persisted_claim_without_selection_provider_read() -> None:
    api = _api()
    store = _Store(existing=True)
    factory = _Factory()
    provider = _UnavailableSelectionProvider()
    process = api.HoldoutClaimProcess(
        store=store,
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
    )

    process.claim_candidate(
        _request(api),
        lease=None,
        now_epoch_us=None,
    )

    assert factory.calls == 0
    assert provider.calls == []
    persistence_request = store.calls[0]["request"]
    assert persistence_request.resolved_reproduction_fingerprint is None
    assert store.calls[0]["lease"] is None
    assert store.calls[0]["now_epoch_us"] is None


def test_new_claim_rejects_selection_provider_hash_mismatch_before_fingerprint() -> (
    None
):
    api = _api()
    store = _Store()
    factory = _Factory()
    provider = _SelectionProvider()
    process = api.HoldoutClaimProcess(
        store=store,
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
    )

    with pytest.raises(AppProcessError) as exc_info:
        process.claim_candidate(
            _request(api),
            lease=_lease(),
            now_epoch_us=2,
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "selection_evidence_hash_mismatch",
        "expected_content_hash": "a" * 64,
        "observed_content_hash": str(provider.ledger.content_hash),
    }
    assert provider.calls == [(ExperimentId("experiment-1"), ContentHash("a" * 64))]
    assert factory.calls == 0
    assert store.calls == []


def test_new_claim_does_not_persist_when_selection_artifact_is_unpublished() -> None:
    api = _api()
    store = _Store()
    factory = _Factory()
    provider = _UnavailableSelectionProvider()
    process = api.HoldoutClaimProcess(
        store=store,
        first_attempt_factory=factory,
        selection_evidence_provider=provider,
    )

    with pytest.raises(AppProcessError) as exc_info:
        process.claim_candidate(
            _request(api),
            lease=_lease(),
            now_epoch_us=2,
        )

    assert exc_info.value is provider.error
    assert provider.calls == [(ExperimentId("experiment-1"), ContentHash("a" * 64))]
    assert factory.calls == 0
    assert store.calls == []


class _Process:
    def __init__(self, receipt: object) -> None:
        self.receipt = receipt
        self.committed = False

    def claim_holdout_candidate(self, request: object) -> object:
        assert request is not None
        self.committed = True
        return self.receipt


class _Notifier:
    def __init__(self, process: _Process, *, fail: bool = False) -> None:
        self.process = process
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def notify_scheduler(
        self,
        *,
        experiment_id: str,
        action: str,
        occurred_at: datetime,
    ) -> None:
        assert self.process.committed
        assert occurred_at == NOW
        self.calls.append((experiment_id, action))
        if self.fail:
            raise RuntimeError("wake failed")


def _receipt(api: SimpleNamespace) -> Any:
    return api.HoldoutClaimReceipt(
        claim_id="holdout-claim-1",
        experiment_id="experiment-1",
        candidate_id="candidate-2",
        fold_id="holdout-candidate-2",
        logical_run_id="holdout-logical-run-1",
        reproduction_fingerprint="b" * 64,
        claim_payload_hash="c" * 64,
        selection_evidence_hash="a" * 64,
        experiment_revision=8,
        event_id="status:claim-event",
        occurred_at=NOW,
    )


def test_command_notifies_only_after_committed_claim() -> None:
    api = _api()
    process = _Process(_receipt(api))
    notifier = _Notifier(process)
    handler = api.ClaimHoldoutCandidateHandler(process=process, notifier=notifier)

    receipt = handler.handle(api.ClaimHoldoutCandidateCommand(_request(api)))

    assert receipt == process.receipt
    assert notifier.calls == [("experiment-1", "holdout_claimed")]


def test_notification_failure_reports_that_claim_is_already_persisted() -> None:
    api = _api()
    process = _Process(_receipt(api))
    handler = api.ClaimHoldoutCandidateHandler(
        process=process,
        notifier=_Notifier(process, fail=True),
    )

    with pytest.raises(AppCommandError) as exc_info:
        handler.handle(api.ClaimHoldoutCandidateCommand(_request(api)))

    assert process.committed
    assert exc_info.value.details["claim_id"] == "holdout-claim-1"
    assert exc_info.value.details["revision"] == 8
    assert exc_info.value.details["notification"] == "scheduler_action"
