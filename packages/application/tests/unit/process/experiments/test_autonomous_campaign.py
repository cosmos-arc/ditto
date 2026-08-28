"""Lease-fenced autonomous Campaign coordination and recovery tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments.campaign import (
    CampaignBudget,
    EvaluationResult,
    ExperimentPlan,
    HypothesisSpec,
    ResearchCampaignManifest,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignReaderProtocol,
    CampaignWriterProtocol,
)
from ditto_analysis.experiments.candidate_novelty import (
    CandidateNoveltyPolicy,
    CandidateOutputProfile,
    evaluate_candidate_novelty,
)
from ditto_analysis.experiments.generated_code import SandboxResourceLimits
from ditto_analysis.experiments.metric_schema import ResearchMetricId
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
    SnapshotId,
)
from ditto_analysis.experiments.persistence import (
    FoldKey,
    LeaseFence,
    SchedulerLease,
    SchedulerSlot,
)
from ditto_analysis.experiments.search_ledger import OperationalAttempt
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    FoldProtocolSpec,
)
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
)
from ditto_application.agent_campaign_contracts import (
    CampaignCandidateProposalCommand,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    decode_campaign_detail,
)
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
    CampaignAuthorizationProof,
    CampaignCoordinatorStatus,
    CampaignEvaluationObservation,
    CampaignScheduledTrial,
    CampaignTrialSchedulerPort,
)
from ditto_application.processes.experiments.campaign_scheduler import (
    ExistingExperimentCampaignScheduler,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

NOW = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _manifest(
    *,
    candidate_limit: int = 8,
    fold_run_limit: int = 16,
    generation_limit: int = 6,
) -> ResearchCampaignManifest:
    axis = SearchAxis.FACTOR_CODE
    baseline = ResearchCandidateSpec(
        candidate=CandidateSpec(
            candidate_id=CandidateId("candidate-baseline"),
            ordinal=1,
            is_baseline=True,
            parameters={"lookback": 20},
        ),
        search_axis=axis,
        parent_candidate_id=None,
        factor_code_hash=_hash("a"),
        model_code_hash=None,
        data_requirement_hashes=(_hash("b"),),
    )
    return ResearchCampaignManifest(
        campaign_id=ExperimentId("campaign-autonomous"),
        objective="Improve a preregistered ETF timing signal.",
        primary_metric_id=ResearchMetricId.SHARPE_RATIO,
        hypothesis=HypothesisSpec(
            statement="Short-term reversal persists after costs.",
            mechanism="Liquidity provision earns a reversal premium.",
            universe_hash=_hash("c"),
            expected_signal="Validation Sharpe improves.",
            failure_condition="Validation Sharpe does not improve.",
        ),
        baseline_candidate=baseline,
        experiment_plan=ExperimentPlan(
            fold_protocol=FoldProtocolSpec(
                protocol_id="walk-forward-v1",
                protocol_version=1,
                protocol_hash=_hash("d"),
            ),
            snapshot_id=SnapshotId("snapshot-2026-08-12"),
            validation_objective_hash=_hash("e"),
            cost_model_hash=_hash("f"),
            seed=42,
            purge_sessions=5,
            embargo_sessions=2,
        ),
        budget=CampaignBudget(
            experiment_budget=ExperimentBudget(
                candidate_limit=candidate_limit,
                fold_run_limit=fold_run_limit,
            ),
            sandbox_resource_limits=SandboxResourceLimits(),
            generation_limit=generation_limit,
        ),
        search_axis=axis,
        search_space_hash=_hash("1"),
        lineage_root=_hash("2"),
        stopping_rule="Stop after two completed generations without improvement.",
        allowed_tools=("campaign_propose_candidate",),
        prohibited_actions=(
            "holdout.evaluate",
            "strategy.publish",
            "broker.submit_order",
        ),
    )


def _authorization(
    manifest: ResearchCampaignManifest,
    *,
    candidate_limit: int | None = None,
) -> CampaignAuthorizationProof:
    return CampaignAuthorizationProof.issue(
        authorization_id="campaign-auth-001",
        authorization_hash="3" * 64,
        authority_hash="4" * 64,
        authorized_by="operator-001",
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        campaign_manifest_hash=str(manifest.manifest_hash),
        search_axis=manifest.search_axis.value,
        allowed_tools=manifest.allowed_tools,
        source_snapshot_id=str(manifest.experiment_plan.snapshot_id),
        candidate_limit=(
            manifest.budget.experiment_budget.candidate_limit
            if candidate_limit is None
            else candidate_limit
        ),
        fold_run_limit=manifest.budget.experiment_budget.fold_run_limit,
        generation_limit=manifest.budget.generation_limit,
        concurrent_sandbox_limit=manifest.budget.concurrent_sandbox_limit,
        wall_time_limit_seconds=manifest.budget.wall_time_limit_seconds,
        temporary_storage_limit_bytes=manifest.budget.temporary_storage_limit_bytes,
        model_spend_limit_usd_micros=(manifest.budget.model_spend_limit_usd_micros),
    )


class _Scheduler:
    def __init__(self, *, fold_run_count: int = 2) -> None:
        self.fold_run_count = fold_run_count
        self.lost = False
        self.schedule_calls = 0
        self.retry_calls = 0
        self.cancel_calls = 0

    def _lease(self, campaign_id: ExperimentId, now_epoch_us: int) -> LeaseFence:
        if self.lost:
            raise AppProcessError(
                "campaign lease was lost",
                details={"code": "LEASE_LOST", "reason": "campaign_lease_lost"},
            )
        return LeaseFence(
            experiment_id=campaign_id,
            owner_token="campaign-test-owner",
            revision=1,
            lease_until_epoch_us=now_epoch_us + 60_000_000,
        )

    def required_fold_run_count(self, campaign_id: ExperimentId) -> int:
        assert campaign_id == ExperimentId("campaign-autonomous")
        return self.fold_run_count

    def schedule_trial(self, request, *, now_epoch_us: int) -> CampaignScheduledTrial:
        self.schedule_calls += 1
        return CampaignScheduledTrial(
            lease=self._lease(request.campaign_id, now_epoch_us),
            fold_run_count=self.fold_run_count,
        )

    def schedule_retry(self, request, *, now_epoch_us: int) -> LeaseFence:
        self.retry_calls += 1
        return self._lease(request.campaign_id, now_epoch_us)

    def cancel_campaign(self, campaign_id: ExperimentId, *, now_epoch_us: int) -> None:
        self.cancel_calls += 1
        self._lease(campaign_id, now_epoch_us)


class _FailingCancelScheduler(_Scheduler):
    def cancel_campaign(self, campaign_id: ExperimentId, *, now_epoch_us: int) -> None:
        self.cancel_calls += 1
        raise AppProcessError(
            "campaign cancel transport failed",
            details={"code": "CAMPAIGN_CANCEL_FAILED", "reason": "cancel_failed"},
        )


class _ConcurrentScheduler(_Scheduler):
    def __init__(self) -> None:
        super().__init__(fold_run_count=2)
        self._barrier = Barrier(2)
        self.first_arrived = Event()
        self._lock = Lock()
        self.required_calls = 0

    def required_fold_run_count(self, campaign_id: ExperimentId) -> int:
        assert campaign_id == ExperimentId("campaign-autonomous")
        with self._lock:
            self.required_calls += 1
        self.first_arrived.set()
        self._barrier.wait(timeout=5)
        return self.fold_run_count

    def schedule_trial(self, request, *, now_epoch_us: int) -> CampaignScheduledTrial:
        with self._lock:
            uses_reservation_protocol = self.required_calls > 0
        if not uses_reservation_protocol:
            self._barrier.wait(timeout=5)
        return super().schedule_trial(request, now_epoch_us=now_epoch_us)


class _ExistingExperimentStore:
    def __init__(self) -> None:
        self.claim_calls = 0
        self.slot = SchedulerSlot(
            slot_id="global",
            experiment_id=None,
            owner_token=None,
            lease_until_epoch_us=None,
            acquired_at_epoch_us=None,
            renewed_at_epoch_us=None,
            revision=0,
        )
        self.folds = tuple(
            SimpleNamespace(
                spec=SimpleNamespace(
                    key=FoldKey(
                        experiment_id=ExperimentId("campaign-autonomous"),
                        candidate_id=CandidateId("candidate-baseline"),
                        fold_id=FoldId(f"fold-{ordinal}"),
                    )
                )
            )
            for ordinal in (1, 2)
        )

    def load_snapshot(self, campaign_id: ExperimentId) -> SimpleNamespace:
        assert campaign_id == ExperimentId("campaign-autonomous")
        return SimpleNamespace(folds=self.folds)

    def get_scheduler_slot(self) -> SchedulerSlot:
        return self.slot

    def try_claim_lease(
        self,
        campaign_id: ExperimentId,
        owner_token: str,
        *,
        expected_revision: int,
        now_epoch_us: int,
        lease_until_epoch_us: int,
    ) -> SchedulerLease:
        self.claim_calls += 1
        lease = SchedulerLease(
            experiment_id=campaign_id,
            owner_token=owner_token,
            lease_until_epoch_us=lease_until_epoch_us,
            acquired_at_epoch_us=now_epoch_us,
            renewed_at_epoch_us=now_epoch_us,
            revision=expected_revision + 1,
        )
        self.slot = SchedulerSlot(
            slot_id="global",
            experiment_id=campaign_id,
            owner_token=owner_token,
            lease_until_epoch_us=lease_until_epoch_us,
            acquired_at_epoch_us=now_epoch_us,
            renewed_at_epoch_us=now_epoch_us,
            revision=lease.revision,
        )
        return lease


class _CrashAfterRetryWriter:
    def __init__(self, delegate: SQLiteCampaignWriter) -> None:
        self._delegate = delegate

    def add_operational_attempt(
        self,
        campaign_id: ExperimentId,
        attempt: OperationalAttempt,
        *,
        created_at_epoch_us: int,
    ) -> None:
        self._delegate.add_operational_attempt(
            campaign_id,
            attempt,
            created_at_epoch_us=created_at_epoch_us,
        )

    def append_campaign_event(self, record: CampaignEventRecord) -> None:
        if record.event_type == "candidate_retried":
            raise RuntimeError("simulated crash after retry attempt commit")
        self._delegate.append_campaign_event(record)


class _MissingSearchLedgerReader:
    def __init__(self, delegate: SQLiteCampaignReader) -> None:
        self._delegate = delegate

    def get_search_ledger(self, campaign_id: ExperimentId) -> None:
        assert campaign_id == ExperimentId("campaign-autonomous")

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


def _coordinator(
    tmp_path: Path,
    scheduler: CampaignTrialSchedulerPort,
) -> tuple[AutonomousCampaignCoordinator, SQLiteCampaignReader]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteCampaignReader(database)
    coordinator = AutonomousCampaignCoordinator(
        reader=reader,
        writer=SQLiteCampaignWriter(database),
        scheduler=scheduler,
    )
    return coordinator, reader


def _proposal(
    *,
    parent: str = "candidate-baseline",
    lookback: int = 10,
) -> CampaignCandidateProposalCommand:
    return CampaignCandidateProposalCommand(
        campaign_id="campaign-autonomous",
        authorization_id="campaign-auth-001",
        authorization_hash="3" * 64,
        authority_hash="4" * 64,
        run_id="run-campaign-001",
        episode_id="episode-run-campaign-001",
        call_id=f"call-proposal-{parent}-{lookback}",
        parent_candidate_id=parent,
        parameters={"lookback": lookback},
        factor_code_hash="5" * 64,
        model_code_hash=None,
        data_requirement_hashes=("6" * 64,),
    )


def _evaluation(
    candidate: ResearchCandidateSpec,
    manifest: ResearchCampaignManifest,
    score: float,
    *,
    outputs: tuple[float, ...] | None = None,
    references: tuple[ResearchCandidateSpec, ...] = (),
) -> CampaignEvaluationObservation:
    profile = _output_profile(candidate, manifest, outputs=outputs)
    return CampaignEvaluationObservation(
        result=EvaluationResult(
            candidate_id=candidate.candidate.candidate_id,
            candidate_hash=candidate.candidate_hash,
            validation_protocol_hash=(
                manifest.experiment_plan.validation_protocol_hash
            ),
            evaluation_input_hash=_hash("9"),
            metrics_artifact_hash=ContentHash(f"{candidate.candidate.ordinal:064x}"),
            constraints_passed=True,
            significance_evidence_hash=_hash("7"),
            failure_classification=None,
            evidence_refs=(_hash("8"),),
        ),
        primary_metric_value=score,
        generation_complete=True,
        novelty_evidence=evaluate_candidate_novelty(
            profile,
            references=tuple(
                _output_profile(reference, manifest) for reference in references
            ),
            policy=CandidateNoveltyPolicy(),
        ),
    )


def _output_profile(
    candidate: ResearchCandidateSpec,
    manifest: ResearchCampaignManifest,
    *,
    outputs: tuple[float, ...] | None = None,
) -> CandidateOutputProfile:
    patterns = {
        1: (1.0, 1.0, -1.0, -1.0),
        2: (1.0, -1.0, -1.0, 1.0),
        3: (1.0, -1.0, 1.0, -1.0),
    }
    ast_hash = (
        candidate.factor_code_hash
        or candidate.model_code_hash
        or candidate.candidate.parameter_hash
    )
    return CandidateOutputProfile(
        candidate_hash=candidate.candidate_hash,
        canonical_ast_hash=ast_hash,
        validation_protocol_hash=manifest.experiment_plan.validation_protocol_hash,
        lineage_root=manifest.lineage_root,
        observation_grid_hash=_hash("9"),
        outputs=outputs
        or patterns.get(
            candidate.candidate.ordinal,
            (1.0, 0.5, -0.5, -1.0),
        ),
    )


def test_authorization_hash_budget_and_search_axis_are_immutable(
    tmp_path: Path,
) -> None:
    coordinator, _ = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest()
    proof = _authorization(manifest)

    with pytest.raises(AppProcessError) as tampered:
        coordinator.authorize(
            manifest,
            replace(proof, campaign_manifest_hash="9" * 64),
            occurred_at=NOW + timedelta(seconds=1),
        )
    assert tampered.value.details["reason"] == (
        "campaign_authorization_integrity_invalid"
    )

    expanded = _authorization(manifest, candidate_limit=9)
    with pytest.raises(AppProcessError) as mismatch:
        coordinator.authorize(
            manifest,
            expanded,
            occurred_at=NOW + timedelta(seconds=1),
        )
    assert mismatch.value.details["reason"] == "campaign_authority_mismatch"

    state = coordinator.authorize(
        manifest,
        proof,
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert state.status is CampaignCoordinatorStatus.AUTHORIZED
    assert state.authorization_hash == proof.authorization_hash


def test_campaign_is_durable_draft_before_exact_manifest_approval(
    tmp_path: Path,
) -> None:
    coordinator, reader = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest()

    draft = coordinator.create(manifest, occurred_at=NOW)
    replay = coordinator.create(
        manifest,
        occurred_at=NOW + timedelta(seconds=1),
    )

    assert draft == replay
    assert draft.status is CampaignCoordinatorStatus.DRAFT
    assert draft.authorization_hash is None
    assert tuple(
        event.event_type for event in reader.list_campaign_events(manifest.campaign_id)
    ) == ("campaign_created",)

    approved = coordinator.approve(
        manifest.campaign_id,
        _authorization(manifest),
        expected_manifest_hash=str(manifest.manifest_hash),
        occurred_at=NOW + timedelta(seconds=2),
    )

    assert approved.status is CampaignCoordinatorStatus.AUTHORIZED
    assert approved.authorization_hash == "3" * 64
    assert tuple(
        event.event_type for event in reader.list_campaign_events(manifest.campaign_id)
    ) == ("campaign_created", "campaign_authorized")


def test_campaign_approval_rejects_manifest_drift_without_patching_budget(
    tmp_path: Path,
) -> None:
    coordinator, _ = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest()
    coordinator.create(manifest, occurred_at=NOW)

    with pytest.raises(AppProcessError) as drifted_manifest:
        coordinator.approve(
            manifest.campaign_id,
            _authorization(manifest),
            expected_manifest_hash="9" * 64,
            occurred_at=NOW + timedelta(seconds=1),
        )
    with pytest.raises(AppProcessError) as expanded_budget:
        coordinator.approve(
            manifest.campaign_id,
            _authorization(manifest, candidate_limit=9),
            expected_manifest_hash=str(manifest.manifest_hash),
            occurred_at=NOW + timedelta(seconds=1),
        )

    assert drifted_manifest.value.details["reason"] == "campaign_manifest_hash_drift"
    assert expanded_budget.value.details["reason"] == "campaign_authority_mismatch"
    assert coordinator.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.DRAFT
    )


def test_authorization_replay_after_restart_is_idempotent(tmp_path: Path) -> None:
    manifest = _manifest()
    proof = _authorization(manifest)
    coordinator, _ = _coordinator(tmp_path, _Scheduler())
    first = coordinator.authorize(
        manifest,
        proof,
        occurred_at=NOW + timedelta(seconds=1),
    )
    restarted, _ = _coordinator(tmp_path, _Scheduler())

    replay = restarted.authorize(
        manifest,
        proof,
        occurred_at=NOW + timedelta(seconds=2),
    )

    assert replay == first


def test_campaign_authorization_cannot_grant_forbidden_tools(tmp_path: Path) -> None:
    coordinator, _ = _coordinator(tmp_path, _Scheduler())
    manifest = replace(_manifest(), allowed_tools=("strategy.publish",))

    with pytest.raises(AppProcessError) as forbidden:
        coordinator.authorize(
            manifest,
            _authorization(manifest),
            occurred_at=NOW + timedelta(seconds=1),
        )

    assert forbidden.value.details["reason"] == "campaign_authority_forbidden"


def test_candidate_budget_exhaustion_pauses_without_expanding_authority(
    tmp_path: Path,
) -> None:
    scheduler = _Scheduler()
    coordinator, _ = _coordinator(tmp_path, scheduler)
    manifest = _manifest(candidate_limit=2)
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )

    coordinator.propose_candidate(_proposal(), occurred_at=NOW + timedelta(seconds=2))
    with pytest.raises(AppProcessError) as exhausted:
        coordinator.propose_candidate(
            _proposal(lookback=11),
            occurred_at=NOW + timedelta(seconds=3),
        )

    assert exhausted.value.details["reason"] == "campaign_candidate_budget_exhausted"
    assert coordinator.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.PAUSED_BUDGET
    )
    assert scheduler.schedule_calls == 1


def test_concurrent_candidates_cannot_reserve_fold_work_beyond_budget(
    tmp_path: Path,
) -> None:
    scheduler = _ConcurrentScheduler()
    first, reader = _coordinator(tmp_path, scheduler)
    manifest = _manifest(candidate_limit=3, fold_run_limit=2)
    first.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    second, _ = _coordinator(tmp_path, scheduler)

    def _propose(coordinator, lookback: int):
        try:
            return coordinator.propose_candidate(
                _proposal(lookback=lookback),
                occurred_at=NOW + timedelta(seconds=2),
            )
        except (AnalysisError, AppProcessError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(_propose, first, 10)
        assert scheduler.first_arrived.wait(timeout=5)
        second_future = pool.submit(_propose, second, 11)
        outcomes = (
            first_future.result(),
            second_future.result(),
        )

    assert scheduler.schedule_calls == 1
    reservations = [
        decode_campaign_detail(event.detail_payload)
        for event in reader.list_campaign_events(manifest.campaign_id)
        if event.event_type == "candidate_fold_reserved"
    ]
    assert sum(cast("int", item["fold_run_count"]) for item in reservations) == 2
    assert any(
        isinstance(outcome, AppProcessError)
        and outcome.details.get("reason") == "campaign_fold_budget_exhausted"
        for outcome in outcomes
    )
    assert first.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.PAUSED_BUDGET
    )


def test_two_completed_generations_without_improvement_stop_campaign(
    tmp_path: Path,
) -> None:
    coordinator, reader = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest(candidate_limit=4, generation_limit=3)
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(manifest.baseline_candidate, manifest, 1.0),
        occurred_at=NOW + timedelta(seconds=2),
    )

    first_receipt = coordinator.propose_candidate(
        _proposal(lookback=10), occurred_at=NOW + timedelta(seconds=3)
    )
    first = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == first_receipt.candidate_id
    )
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(first, manifest, 0.9),
        occurred_at=NOW + timedelta(seconds=4),
    )
    second_receipt = coordinator.propose_candidate(
        _proposal(parent=first_receipt.candidate_id, lookback=5),
        occurred_at=NOW + timedelta(seconds=5),
    )
    second = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == second_receipt.candidate_id
    )
    state = coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(second, manifest, 0.8),
        occurred_at=NOW + timedelta(seconds=6),
    )

    assert state.status is CampaignCoordinatorStatus.COMPLETED
    assert state.no_improvement_generations == 2
    assert state.best_primary_metric_value == 1.0


def test_two_candidates_in_one_generation_count_as_one_completed_generation(
    tmp_path: Path,
) -> None:
    coordinator, reader = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest(candidate_limit=4)
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(manifest.baseline_candidate, manifest, 1.0),
        occurred_at=NOW + timedelta(seconds=2),
    )
    receipts = (
        coordinator.propose_candidate(
            _proposal(lookback=10), occurred_at=NOW + timedelta(seconds=3)
        ),
        coordinator.propose_candidate(
            _proposal(lookback=11), occurred_at=NOW + timedelta(seconds=4)
        ),
    )
    candidates = {
        str(item.candidate.candidate.candidate_id): item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
    }
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(candidates[receipts[0].candidate_id], manifest, 0.9),
        occurred_at=NOW + timedelta(seconds=5),
    )
    state = coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(candidates[receipts[1].candidate_id], manifest, 0.8),
        occurred_at=NOW + timedelta(seconds=6),
    )

    assert state.status is CampaignCoordinatorStatus.RUNNING
    assert state.no_improvement_generations == 1


def test_correlated_candidate_cannot_improve_or_parent_next_generation(
    tmp_path: Path,
) -> None:
    coordinator, reader = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest(candidate_limit=4)
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    baseline = manifest.baseline_candidate
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(baseline, manifest, 1.0),
        occurred_at=NOW + timedelta(seconds=2),
    )
    receipt = coordinator.propose_candidate(
        _proposal(lookback=10), occurred_at=NOW + timedelta(seconds=3)
    )
    candidate = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == receipt.candidate_id
    )

    state = coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(
            candidate,
            manifest,
            2.0,
            outputs=(2.0, 2.0, -2.0, -2.0),
            references=(baseline,),
        ),
        occurred_at=NOW + timedelta(seconds=4),
    )

    assert state.best_primary_metric_value == 1.0
    evaluation_event = next(
        event
        for event in reader.list_campaign_events(manifest.campaign_id)
        if event.event_type == "candidate_evaluated"
        and decode_campaign_detail(event.detail_payload).get("candidate_id")
        == receipt.candidate_id
    )
    detail = decode_campaign_detail(evaluation_event.detail_payload)
    assert "outputs" not in detail
    assert "candidate_outputs" not in detail
    assert detail["novelty_accepted"] is False
    with pytest.raises(AppProcessError) as exc_info:
        coordinator.propose_candidate(
            _proposal(parent=receipt.candidate_id, lookback=5),
            occurred_at=NOW + timedelta(seconds=5),
        )
    assert exc_info.value.details["reason"] == "campaign_parent_not_novel"


def test_evaluation_replay_rejects_novelty_evidence_drift(tmp_path: Path) -> None:
    coordinator, _ = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    first = _evaluation(manifest.baseline_candidate, manifest, 1.0)
    coordinator.record_evaluation(
        manifest.campaign_id,
        first,
        occurred_at=NOW + timedelta(seconds=2),
    )
    changed_policy_evidence = evaluate_candidate_novelty(
        _output_profile(manifest.baseline_candidate, manifest),
        references=(),
        policy=CandidateNoveltyPolicy(max_abs_output_correlation=0.9),
    )

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.record_evaluation(
            manifest.campaign_id,
            replace(first, novelty_evidence=changed_policy_evidence),
            occurred_at=NOW + timedelta(seconds=3),
        )

    assert exc_info.value.details["reason"] == "campaign_novelty_evidence_drift"


def test_nonbaseline_evaluation_requires_registered_statistical_trial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator, reader = _coordinator(tmp_path, _Scheduler())
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    receipt = coordinator.propose_candidate(
        _proposal(), occurred_at=NOW + timedelta(seconds=2)
    )
    candidate = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == receipt.candidate_id
    )
    monkeypatch.setattr(
        coordinator,
        "_reader",
        cast(CampaignReaderProtocol, _MissingSearchLedgerReader(reader)),
    )

    with pytest.raises(AppProcessError) as exc_info:
        coordinator.record_evaluation(
            manifest.campaign_id,
            _evaluation(candidate, manifest, 2.0),
            occurred_at=NOW + timedelta(seconds=3),
        )

    assert exc_info.value.details["reason"] == ("campaign_evaluation_identity_mismatch")


def test_lease_loss_pauses_and_restart_replays_one_statistical_trial(
    tmp_path: Path,
) -> None:
    lost_scheduler = _Scheduler()
    coordinator, _ = _coordinator(tmp_path, lost_scheduler)
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    lost_scheduler.lost = True

    with pytest.raises(AppProcessError) as lost:
        coordinator.propose_candidate(
            _proposal(), occurred_at=NOW + timedelta(seconds=2)
        )
    assert lost.value.details["reason"] == "campaign_lease_lost"
    assert coordinator.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.PAUSED
    )

    recovered_scheduler = _Scheduler()
    restarted, _ = _coordinator(tmp_path, recovered_scheduler)
    restarted.propose_candidate(_proposal(), occurred_at=NOW + timedelta(seconds=3))
    ledger = restarted.get_state(manifest.campaign_id)
    assert ledger.statistical_trial_count == 1
    assert ledger.operational_attempt_count == 1
    restarted.propose_candidate(_proposal(), occurred_at=NOW + timedelta(seconds=4))
    assert restarted.get_state(manifest.campaign_id).statistical_trial_count == 1


def test_retry_does_not_recount_trial_and_fork_keeps_family_lineage(
    tmp_path: Path,
) -> None:
    scheduler = _Scheduler()
    coordinator, reader = _coordinator(tmp_path, scheduler)
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    first = coordinator.propose_candidate(
        _proposal(), occurred_at=NOW + timedelta(seconds=2)
    )
    coordinator.retry_candidate(
        manifest.campaign_id,
        CandidateId(first.candidate_id),
        authorization_hash="3" * 64,
        retry_id="retry-001",
        occurred_at=NOW + timedelta(seconds=3),
    )
    first_candidate = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == first.candidate_id
    )
    coordinator.record_evaluation(
        manifest.campaign_id,
        _evaluation(first_candidate, manifest, 1.0),
        occurred_at=NOW + timedelta(seconds=4),
    )
    fork = coordinator.propose_candidate(
        _proposal(parent=first.candidate_id, lookback=5),
        occurred_at=NOW + timedelta(seconds=5),
    )

    state = coordinator.get_state(manifest.campaign_id)
    ledger = reader.get_search_ledger(manifest.campaign_id)
    assert ledger is not None
    assert state.statistical_trial_count == 2
    assert state.operational_attempt_count == 3
    assert scheduler.retry_calls == 1
    assert len({trial.family_id for trial in ledger.statistical_trials}) == 1
    assert len({trial.lineage_root for trial in ledger.statistical_trials}) == 1
    assert fork.generation == 2


def test_retry_recovers_when_attempt_committed_before_event(tmp_path: Path) -> None:
    scheduler = _Scheduler()
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteCampaignReader(database)
    writer = SQLiteCampaignWriter(database)
    coordinator = AutonomousCampaignCoordinator(
        reader=reader,
        writer=writer,
        scheduler=scheduler,
    )
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    candidate = coordinator.propose_candidate(
        _proposal(), occurred_at=NOW + timedelta(seconds=2)
    )
    crashing = AutonomousCampaignCoordinator(
        reader=reader,
        writer=cast(CampaignWriterProtocol, _CrashAfterRetryWriter(writer)),
        scheduler=scheduler,
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        crashing.retry_candidate(
            manifest.campaign_id,
            CandidateId(candidate.candidate_id),
            authorization_hash="3" * 64,
            retry_id="retry-crash-001",
            occurred_at=NOW + timedelta(seconds=3),
        )

    restarted = AutonomousCampaignCoordinator(
        reader=reader,
        writer=writer,
        scheduler=scheduler,
    )
    state = restarted.retry_candidate(
        manifest.campaign_id,
        CandidateId(candidate.candidate_id),
        authorization_hash="3" * 64,
        retry_id="retry-crash-001",
        occurred_at=NOW + timedelta(seconds=4),
    )

    assert state.statistical_trial_count == 1
    assert state.operational_attempt_count == 2
    assert scheduler.retry_calls == 1


def test_cancel_is_idempotent_and_reconstructs_after_restart(tmp_path: Path) -> None:
    scheduler = _Scheduler()
    coordinator, _ = _coordinator(tmp_path, scheduler)
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    coordinator.propose_candidate(_proposal(), occurred_at=NOW + timedelta(seconds=2))

    first = coordinator.cancel(
        manifest.campaign_id,
        authorization_hash="3" * 64,
        occurred_at=NOW + timedelta(seconds=3),
    )
    replay = coordinator.cancel(
        manifest.campaign_id,
        authorization_hash="3" * 64,
        occurred_at=NOW + timedelta(seconds=4),
    )
    expired_replay = coordinator.cancel(
        manifest.campaign_id,
        authorization_hash="3" * 64,
        occurred_at=NOW + timedelta(hours=5),
    )
    with pytest.raises(AppProcessError) as mismatched_replay:
        coordinator.cancel(
            manifest.campaign_id,
            authorization_hash="9" * 64,
            occurred_at=NOW + timedelta(hours=6),
        )
    restarted, _ = _coordinator(tmp_path, scheduler)

    assert first == replay == expired_replay
    assert mismatched_replay.value.details["reason"] == "campaign_authority_mismatch"
    assert scheduler.cancel_calls == 1
    assert restarted.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.CANCELLED
    )
    with pytest.raises(AppProcessError) as terminal:
        restarted.propose_candidate(
            _proposal(lookback=11),
            occurred_at=NOW + timedelta(seconds=5),
        )
    assert terminal.value.details["reason"] == "campaign_terminal"


def test_cancel_transport_failure_closes_campaign_to_new_work(tmp_path: Path) -> None:
    scheduler = _FailingCancelScheduler()
    coordinator, reader = _coordinator(tmp_path, scheduler)
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )
    receipt = coordinator.propose_candidate(
        _proposal(), occurred_at=NOW + timedelta(seconds=2)
    )
    candidate = next(
        item.candidate
        for item in reader.list_candidates(manifest.campaign_id)
        if str(item.candidate.candidate.candidate_id) == receipt.candidate_id
    )

    with pytest.raises(AppProcessError) as cancel_failure:
        coordinator.cancel(
            manifest.campaign_id,
            authorization_hash="3" * 64,
            occurred_at=NOW + timedelta(seconds=3),
        )

    assert cancel_failure.value.details["reason"] == "cancel_failed"
    assert coordinator.get_state(manifest.campaign_id).status is (
        CampaignCoordinatorStatus.CANCEL_REQUESTED
    )
    blocked_actions = (
        lambda: coordinator.propose_candidate(
            _proposal(lookback=11), occurred_at=NOW + timedelta(seconds=4)
        ),
        lambda: coordinator.retry_candidate(
            manifest.campaign_id,
            CandidateId(receipt.candidate_id),
            authorization_hash="3" * 64,
            retry_id="retry-after-cancel",
            occurred_at=NOW + timedelta(seconds=4),
        ),
        lambda: coordinator.record_evaluation(
            manifest.campaign_id,
            _evaluation(candidate, manifest, 1.0),
            occurred_at=NOW + timedelta(seconds=4),
        ),
    )
    for action in blocked_actions:
        with pytest.raises(AppProcessError) as blocked:
            action()
        assert blocked.value.details["reason"] == "campaign_cancel_pending"


def test_scheduler_port_remains_structural() -> None:
    scheduler: CampaignTrialSchedulerPort = _Scheduler()

    assert scheduler.fold_run_count == 2


def test_campaign_scheduler_reuses_existing_lease_and_frozen_fold_matrix(
    tmp_path: Path,
) -> None:
    store = _ExistingExperimentStore()
    scheduler = ExistingExperimentCampaignScheduler(
        store=cast(ExperimentSchedulerStoreProtocol, store)
    )
    coordinator, _ = _coordinator(tmp_path, scheduler)
    manifest = _manifest()
    coordinator.authorize(
        manifest,
        _authorization(manifest),
        occurred_at=NOW + timedelta(seconds=1),
    )

    coordinator.propose_candidate(_proposal(), occurred_at=NOW + timedelta(seconds=2))
    coordinator.propose_candidate(
        _proposal(lookback=11), occurred_at=NOW + timedelta(seconds=3)
    )

    state = coordinator.get_state(manifest.campaign_id)
    assert state.statistical_trial_count == 2
    assert store.claim_calls == 1


def test_application_provider_wires_campaign_coordinator(tmp_path: Path) -> None:
    from ditto_application.providers_process import AppProcessProvider

    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    reader = SQLiteCampaignReader(database)
    writer = SQLiteCampaignWriter(database)
    provider = AppProcessProvider()

    coordinator = provider.autonomous_campaign_coordinator(
        reader,
        writer,
        _Scheduler(),
    )

    assert provider.autonomous_campaign_command_port(coordinator) is coordinator
