"""Execution-owned first attempt and fail-closed R3 research fold worker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, cast

from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CheckpointRef,
    ExperimentFailureCode,
    ExperimentStage,
    ExperimentStatus,
    FoldRole,
    FoldView,
    LeaseFence,
    canonical_payload,
)
from ditto_strategy.errors import StrategyError

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import BacktestService
from ditto_application.processes.experiments._execution_resolution_evidence import (
    ResearchExecutionInputError,
    build_successor_queued_attempt,
    rebuild_execution_audit_anchor,
)
from ditto_application.processes.experiments._fold_selection_trace_artifact_validation import (  # noqa: E501
    publish_verified_fold_selection_trace_artifacts,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FoldSelectionTraceArtifactIdentity,
    FoldSelectionTraceArtifactPublisher,
)
from ditto_application.processes.experiments._report_artifact_validation import (
    publish_verified_backtest_report_artifact,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportArtifactPublisher,
    BacktestReportEvidence,
)
from ditto_application.processes.experiments._worker_attestation import (
    ResearchBacktestBuildAttestation,
    ResearchBacktestBuildSource,
    VerifiedResearchBacktestBuild,
    require_verified_research_backtest_build_seal,
)
from ditto_application.processes.experiments._worker_contract import (
    ResearchFoldRunResult,
    ResearchFoldRunState,
    ResearchWorkerCoordinator,
    ResearchWorkerResult,
    ResearchWorkerState,
)
from ditto_application.processes.experiments._worker_heartbeat import (
    EXECUTION_HEARTBEAT_INTERVAL_SECONDS,
    ExecutionLeaseHeartbeat,
)
from ditto_application.processes.experiments.backtest_service_wiring import (
    ClosedBacktestServiceGraph,
    require_closed_backtest_service,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
    PersistedAttemptStart,
    deterministic_backtest_run_id,
)
from ditto_application.processes.experiments.execution_bundle import (
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
)
from ditto_application.processes.experiments.lease_authority import (
    ResearchExecutionControl,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentExecutionControlChanged,
    FirstAttempt,
    QueuedAttempt,
    ResearchExecutionDirective,
)

__all__ = [
    "ExecutionBundleFirstAttemptFactory",
    "ExistingBacktestResearchFoldRunner",
    "ResearchBacktestBuildAttestation",
    "ResearchBacktestBuildSource",
    "ResearchBacktestServiceFactory",
    "ResearchCandidateExecutionError",
    "ResearchExecutionControl",
    "ResearchExecutionSemanticsResolver",
    "ResearchExperimentWorker",
    "ResearchFoldRunResult",
    "ResearchFoldRunState",
    "ResearchFoldRunner",
    "ResearchWorkerResult",
    "ResearchWorkerState",
    "VerifiedResearchBacktestBuild",
]

_HASH_DRIFT_REASON_SUFFIXES = (
    "_hash_drift",
    "_hash_mismatch",
    "_fingerprint_drift",
)
_EXECUTABLE_STAGE_ROLES = {
    ExperimentStage.EXPLORATION: FoldRole.EXPLORATION,
    ExperimentStage.HOLDOUT: FoldRole.HOLDOUT,
    ExperimentStage.WALK_FORWARD: FoldRole.WALK_FORWARD,
}


def _worker_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "research experiment worker contract is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _worker_integrity_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "research experiment persisted dispatch is invalid",
        details={
            "code": "EXPERIMENT_INTEGRITY_FAILED",
            "reason": reason,
            **details,
        },
    )


class ResearchExecutionSemanticsResolver(Protocol):
    """Rebuild exact result-determining semantics from durable frozen facts."""

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        """Resolve one fold without active/latest/provider fallback."""
        ...


class ResearchFoldRunner(Protocol):
    """Run one existing deterministic backtest path from an exact audit bundle."""

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        """Execute one audit-bound fold through the existing backtest path."""
        ...


class ResearchBacktestServiceFactory(Protocol):
    """Build an existing BacktestService from one immutable attempt bundle."""

    def build(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> VerifiedResearchBacktestBuild:
        """Build without catalog latest, active pointer, or provider fallback."""
        ...


class ExistingBacktestResearchFoldRunner:
    """Thin adapter that keeps numerical execution in BacktestService."""

    def __init__(self, factory: ResearchBacktestServiceFactory) -> None:
        self._factory = factory

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunResult:
        """Build and run the existing single-backtest application service."""
        if external_should_stop():
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        audit_anchor = rebuild_execution_audit_anchor(audit)
        build = self._factory.build(
            audit,
            external_should_stop=external_should_stop,
        )
        if type(cast("object", build)) is not VerifiedResearchBacktestBuild:
            raise _worker_error("invalid_research_backtest_build")
        attestation = build.attestation
        expected = ResearchBacktestBuildAttestation.from_audit(audit)
        if (
            type(cast("object", attestation)) is not ResearchBacktestBuildAttestation
            or attestation != expected
        ):
            raise _worker_error("research_backtest_attestation_drift")
        if rebuild_execution_audit_anchor(audit) != audit_anchor:
            raise _worker_error("research_execution_audit_drift")
        if external_should_stop():
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        service = build.service
        if type(cast("object", service)) is not BacktestService:
            raise _worker_error("invalid_research_backtest_service")
        graph = build.graph
        if (
            type(cast("object", graph)) is not ClosedBacktestServiceGraph
            or graph.service is not service
        ):
            raise _worker_error("invalid_research_backtest_service_graph")
        require_closed_backtest_service(
            graph,
            expected_audit=audit,
            expected_should_stop=external_should_stop,
        )
        require_verified_research_backtest_build_seal(build)
        try:
            report = BacktestService.run(service)
        except StrategyError as error:
            raise ResearchCandidateExecutionError(
                "research candidate strategy execution failed"
            ) from error
        if service.last_run_cancelled:
            return ResearchFoldRunResult(ResearchFoldRunState.STOPPED, None)
        # Checkpoint V2 restores numerical runtime state, but not the collector's
        # pre-checkpoint events. Withhold the suffix-only log until that evidence
        # has its own exact resume contract.
        return ResearchFoldRunResult(
            ResearchFoldRunState.COMPLETED,
            BacktestReportEvidence.from_report(report),
            (
                None
                if audit.resume_from_run_id is not None
                else graph.selection_evidence_collector.snapshot()
            ),
        )


_TERMINAL_AUTHORITY_LOSS_CODES = frozenset(
    {"LEASE_LOST", "EXPERIMENT_INTEGRITY_FAILED"}
)


class ResearchCandidateExecutionError(RuntimeError):
    """Explicit candidate-local numerical or strategy execution failure."""


class _ResearchCooperativeStopError(RuntimeError):
    """Internal marker preventing a stopped engine from becoming completed."""


def _require_execution_authority(control: ResearchExecutionControl) -> None:
    if not control.should_stop():
        return
    failure = control.failure
    if failure is not None:
        raise failure
    raise _ResearchCooperativeStopError(
        "research execution stopped before numerical work"
    )


def _lost_terminal_authority(error: Exception) -> bool:
    if not isinstance(error, AppProcessError):
        return False
    return error.details.get("code") in _TERMINAL_AUTHORITY_LOSS_CODES


def _require_fold_semantics(
    fold: FoldView,
    semantics: ResearchExecutionSemantics,
) -> None:
    if type(cast("object", fold)) is not FoldView:
        raise _worker_error("invalid_execution_fold")
    if type(cast("object", semantics)) is not ResearchExecutionSemantics:
        raise _worker_error("invalid_execution_semantics")
    spec = fold.spec
    train_window = spec.train_window
    if (
        semantics.experiment_id != str(spec.key.experiment_id)
        or semantics.candidate_id != str(spec.key.candidate_id)
        or semantics.fold_id != str(spec.key.fold_id)
        or semantics.fold_role != spec.fold_role.value
        or semantics.fold_spec_hash != str(spec.payload_hash)
        or semantics.train_start
        != (None if train_window is None else train_window.start)
        or semantics.train_end != (None if train_window is None else train_window.end)
        or semantics.test_start != spec.test_window.start
        or semantics.test_end != spec.test_window.end
        or semantics.purge_sessions != spec.purge_sessions
        or semantics.embargo_sessions != spec.embargo_sessions
    ):
        raise _worker_error(
            "execution_fold_lineage_mismatch",
            experiment_id=str(spec.key.experiment_id),
            candidate_id=str(spec.key.candidate_id),
            fold_id=str(spec.key.fold_id),
        )


class ExecutionBundleFirstAttemptFactory:
    """Freeze stable first and successor attempt identities before claim."""

    def __init__(self, resolver: ResearchExecutionSemanticsResolver) -> None:
        self._resolver = resolver

    def create(self, fold: FoldView, occurred_at: datetime) -> FirstAttempt:
        """Create one queued attempt without writes or moving-state lookup."""
        if (
            type(cast("object", fold)) is not FoldView
            or fold.projection.status is not ExperimentStatus.QUEUED
            or fold.projection.claim_owner_token is not None
        ):
            raise _worker_error("first_attempt_fold_not_claimable")
        semantics = self._resolver.resolve(fold)
        _require_fold_semantics(fold, semantics)
        identity = canonical_payload(
            {
                "kind": "r3_research_first_attempt",
                "fold_payload_hash": str(fold.spec.payload_hash),
                "reproduction_fingerprint": str(semantics.reproduction_fingerprint),
                "ordinal": 1,
            }
        ).content_hash
        attempt_id = AttemptId(f"attempt-{identity}")
        spec = AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=fold.spec.key,
            ordinal=1,
            parent_attempt_id=None,
            resume_from_run_id=None,
            reproduction_fingerprint=semantics.reproduction_fingerprint,
            created_at=occurred_at,
        )
        projection = AttemptProjection(
            attempt_id=attempt_id,
            status=ExperimentStatus.QUEUED,
            backtest_run_id=None,
            checkpoint_ref=None,
            failure_code=None,
            created_at=occurred_at,
            updated_at=occurred_at,
            revision=0,
        )
        return FirstAttempt(spec, projection)

    def create_successor(
        self,
        fold: FoldView,
        parent: AttemptView,
        *,
        resume_from_run_id: BacktestRunId | None,
        occurred_at: datetime,
    ) -> QueuedAttempt:
        """Create the next immutable attempt without resolving moving semantics."""
        return build_successor_queued_attempt(
            fold,
            parent,
            resume_from_run_id=resume_from_run_id,
            occurred_at=occurred_at,
        )


def _failure(error: Exception) -> tuple[ResearchWorkerState, ExperimentFailureCode]:
    if isinstance(error, ResearchCandidateExecutionError):
        return (
            ResearchWorkerState.CANDIDATE_FAILED,
            ExperimentFailureCode.CANDIDATE_FAILED,
        )
    if isinstance(error, ResearchExecutionInputError):
        return (
            ResearchWorkerState.INPUT_FAILED,
            ExperimentFailureCode.INPUT_HASH_MISMATCH,
        )
    if isinstance(error, AppProcessError):
        code = error.details.get("code")
        reason = error.details.get("reason")
        if code == "INPUT_HASH_MISMATCH" or (
            type(reason) is str and reason.endswith(_HASH_DRIFT_REASON_SUFFIXES)
        ):
            return (
                ResearchWorkerState.INPUT_FAILED,
                ExperimentFailureCode.INPUT_HASH_MISMATCH,
            )
    return ResearchWorkerState.SYSTEM_FAILED, ExperimentFailureCode.SYSTEM_ERROR


def _require_persisted_start(
    dispatch: ExperimentDispatch,
    persisted: PersistedAttemptStart,
) -> None:
    if type(cast("object", persisted)) is not PersistedAttemptStart:
        raise _worker_integrity_error("invalid_persisted_attempt_start")
    expected_role = _EXECUTABLE_STAGE_ROLES.get(dispatch.stage)
    if (
        expected_role is None
        or dispatch.fold.spec.fold_role is not expected_role
        or persisted.fold.spec.fold_role is not expected_role
    ):
        raise _worker_integrity_error("persisted_stage_role_mismatch")
    if persisted.attempt.spec != dispatch.attempt.spec:
        raise _worker_integrity_error("persisted_attempt_identity_drift")
    if persisted.fold.spec != dispatch.fold.spec:
        raise _worker_integrity_error("persisted_fold_identity_drift")
    if (
        not persisted.started_now
        and persisted.attempt.projection.status is ExperimentStatus.RUNNING
    ):
        raise _worker_integrity_error("duplicate_attempt_delivery")


def _terminal_replay_result(
    persisted: PersistedAttemptStart,
) -> ResearchWorkerResult | None:
    status = persisted.attempt.projection.status
    if status not in {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}:
        return None
    run_id = persisted.attempt.projection.backtest_run_id
    if run_id is None:
        raise _worker_integrity_error("persisted_run_identity_missing")
    failure_code = persisted.attempt.projection.failure_code
    if status is ExperimentStatus.COMPLETED:
        state = ResearchWorkerState.COMPLETED
    elif failure_code is ExperimentFailureCode.CANDIDATE_FAILED:
        state = ResearchWorkerState.CANDIDATE_FAILED
    elif failure_code is ExperimentFailureCode.INPUT_HASH_MISMATCH:
        state = ResearchWorkerState.INPUT_FAILED
    elif failure_code is ExperimentFailureCode.SYSTEM_ERROR:
        state = ResearchWorkerState.SYSTEM_FAILED
    else:  # PersistedAttemptStart already rejects this state/code pair.
        raise _worker_integrity_error("persisted_terminal_failure_code_invalid")
    return ResearchWorkerResult(
        attempt_id=persisted.attempt.spec.attempt_id,
        backtest_run_id=run_id,
        reproduction_fingerprint=(persisted.attempt.spec.reproduction_fingerprint),
        state=state,
        failure_code=failure_code,
        error_type=None,
    )


def _require_dispatch(dispatch: ExperimentDispatch) -> None:
    if (
        type(cast("object", dispatch)) is not ExperimentDispatch
        or dispatch.attempt.projection.status is not ExperimentStatus.QUEUED
        or dispatch.fold.projection.status is not ExperimentStatus.RUNNING
        or dispatch.attempt.spec.fold_key != dispatch.fold.spec.key
        or _EXECUTABLE_STAGE_ROLES.get(dispatch.stage)
        is not dispatch.fold.spec.fold_role
    ):
        raise _worker_error("invalid_experiment_dispatch")


def _controlled_worker_state(
    directive: ResearchExecutionDirective,
) -> ResearchWorkerState:
    if directive is ResearchExecutionDirective.PAUSE:
        return ResearchWorkerState.PAUSED
    if directive is ResearchExecutionDirective.CANCEL:
        return ResearchWorkerState.CANCELLED
    raise _worker_error("cooperative_stop_without_durable_control")


def _require_fold_selection_trace_contract(
    attempt: AttemptPersistenceSpec,
    run_result: ResearchFoldRunResult,
    publisher: FoldSelectionTraceArtifactPublisher | None,
) -> None:
    """Keep fresh/resumed trace truth explicit before any artifact write."""
    selection_evidence = run_result.selection_evidence
    if selection_evidence is None and attempt.resume_from_run_id is None:
        raise _worker_error("fresh_fold_selection_trace_missing")
    if selection_evidence is not None and attempt.resume_from_run_id is not None:
        raise _worker_error("resumed_fold_selection_trace_continuity_unproven")
    if selection_evidence is not None and publisher is None:
        raise _worker_error("fold_selection_trace_publisher_missing")


def _require_completed_report_evidence(
    run_result: ResearchFoldRunResult,
) -> BacktestReportEvidence:
    evidence = run_result.report_evidence
    if type(evidence) is not BacktestReportEvidence:
        raise _worker_error("invalid_research_fold_run_result")
    return evidence


class ResearchExperimentWorker:
    """Execute a claimed fold and persist one typed terminal outcome."""

    def __init__(
        self,
        *,
        coordinator: ResearchWorkerCoordinator,
        semantics_resolver: ResearchExecutionSemanticsResolver,
        runner: ResearchFoldRunner,
        report_publisher: BacktestReportArtifactPublisher,
        fold_selection_trace_publisher: (
            FoldSelectionTraceArtifactPublisher | None
        ) = None,
        checkpoint_available: Callable[[str], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._resolver = semantics_resolver
        self._runner = runner
        self._report_publisher = report_publisher
        self._fold_selection_trace_publisher = fold_selection_trace_publisher
        self._checkpoint_available: Callable[[str], bool] = checkpoint_available or (
            lambda _run_id: False
        )
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def execute(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> ResearchWorkerResult:
        """Run one dispatch; all failures after start become durable outcomes."""
        _require_dispatch(dispatch)
        self._coordinator.renew_lease(occurred_at=occurred_at)
        initial_directive = self._coordinator.poll_execution_directive(
            dispatch.attempt.spec.attempt_id,
            occurred_at=occurred_at,
        )
        if initial_directive is not ResearchExecutionDirective.RUN:
            run_id = deterministic_backtest_run_id(
                dispatch.attempt.spec.attempt_id,
                dispatch.attempt.spec.reproduction_fingerprint,
            )
            return self._finish_controlled_attempt(
                dispatch.attempt.spec,
                run_id,
                initial_directive,
            )
        try:
            persisted = self._coordinator.start_attempt(
                dispatch,
                occurred_at=occurred_at,
            )
        except ExperimentExecutionControlChanged:
            directive = self._coordinator.poll_execution_directive(
                dispatch.attempt.spec.attempt_id,
                occurred_at=self._clock(),
            )
            if directive is ResearchExecutionDirective.RUN:
                raise _worker_integrity_error(
                    "execution_control_change_without_stop_intent"
                ) from None
            run_id = deterministic_backtest_run_id(
                dispatch.attempt.spec.attempt_id,
                dispatch.attempt.spec.reproduction_fingerprint,
            )
            return self._finish_controlled_attempt(
                dispatch.attempt.spec,
                run_id,
                directive,
            )
        _require_persisted_start(dispatch, persisted)
        terminal_replay = _terminal_replay_result(persisted)
        if terminal_replay is not None:
            return terminal_replay
        attempt = persisted.attempt.spec
        run_id = persisted.attempt.projection.backtest_run_id
        if run_id is None:  # PersistedAttemptStart already guarantees this.
            raise _worker_integrity_error("persisted_run_identity_missing")
        execution_control = ResearchExecutionControl(
            coordinator=self._coordinator,
            attempt_id=attempt.attempt_id,
            clock=self._clock,
        )
        try:
            with ExecutionLeaseHeartbeat(
                execution_control,
                EXECUTION_HEARTBEAT_INTERVAL_SECONDS,
            ):
                run_result = self._run_fold(
                    persisted,
                    attempt,
                    run_id,
                    execution_control,
                )
            report_evidence = _require_completed_report_evidence(run_result)
            _require_fold_selection_trace_contract(
                attempt,
                run_result,
                self._fold_selection_trace_publisher,
            )
            self._publish_completed_evidence(
                persisted,
                attempt,
                run_id,
                report_evidence,
                run_result,
            )
        except Exception as error:
            effective_error = execution_control.failure or error
            if _lost_terminal_authority(effective_error):
                if effective_error is error:
                    raise
                raise effective_error from error
            if isinstance(effective_error, _ResearchCooperativeStopError):
                return self._finish_controlled_attempt(
                    attempt,
                    run_id,
                    execution_control.directive,
                )
            state, failure_code = _failure(effective_error)
            finished_at = self._clock()
            self._coordinator.renew_lease(occurred_at=finished_at)
            self._coordinator.fail_attempt(
                attempt.attempt_id,
                failure_code,
                occurred_at=finished_at,
            )
            return ResearchWorkerResult(
                attempt_id=attempt.attempt_id,
                backtest_run_id=run_id,
                reproduction_fingerprint=attempt.reproduction_fingerprint,
                state=state,
                failure_code=failure_code,
                error_type=type(effective_error).__name__,
            )
        finished_at = self._clock()
        self._coordinator.renew_lease(occurred_at=finished_at)
        self._coordinator.complete_attempt(
            attempt.attempt_id,
            occurred_at=finished_at,
        )
        return ResearchWorkerResult(
            attempt_id=attempt.attempt_id,
            backtest_run_id=run_id,
            reproduction_fingerprint=attempt.reproduction_fingerprint,
            state=ResearchWorkerState.COMPLETED,
            failure_code=None,
            error_type=None,
        )

    def _publish_completed_evidence(
        self,
        persisted: PersistedAttemptStart,
        attempt: AttemptPersistenceSpec,
        run_id: BacktestRunId,
        report_evidence: BacktestReportEvidence,
        run_result: ResearchFoldRunResult,
    ) -> None:
        key = persisted.fold.spec.key
        test_window = persisted.fold.spec.test_window
        report_identity = BacktestReportArtifactIdentity(
            experiment_id=key.experiment_id,
            candidate_id=key.candidate_id,
            fold_id=key.fold_id,
            attempt_id=attempt.attempt_id,
            attempt_created_at=attempt.created_at,
            run_id=run_id,
            test_window=test_window,
            reproduction_fingerprint=attempt.reproduction_fingerprint,
        )
        trace_identity = FoldSelectionTraceArtifactIdentity(
            experiment_id=key.experiment_id,
            candidate_id=key.candidate_id,
            fold_id=key.fold_id,
            attempt_id=attempt.attempt_id,
            attempt_created_at=attempt.created_at,
            run_id=run_id,
            test_window=test_window,
            reproduction_fingerprint=attempt.reproduction_fingerprint,
        )

        def _publish_attempt_evidence(
            lease_fence: LeaseFence,
            now_epoch_us: int,
        ) -> ArtifactRecord:
            report_record = publish_verified_backtest_report_artifact(
                self._report_publisher,
                report_identity,
                report_evidence,
                lease_fence=lease_fence,
                now_epoch_us=now_epoch_us,
            )
            selection_evidence = run_result.selection_evidence
            if selection_evidence is not None:
                publish_verified_fold_selection_trace_artifacts(
                    self._fold_selection_trace_publisher,
                    trace_identity,
                    selection_evidence,
                    lease_fence=lease_fence,
                    now_epoch_us=now_epoch_us,
                )
            return report_record

        self._coordinator.publish_attempt_artifact(_publish_attempt_evidence)

    def _run_fold(
        self,
        persisted: PersistedAttemptStart,
        attempt: AttemptPersistenceSpec,
        run_id: BacktestRunId,
        execution_control: ResearchExecutionControl,
    ) -> ResearchFoldRunResult:
        _require_execution_authority(execution_control)
        semantics = self._resolver.resolve(persisted.fold)
        _require_execution_authority(execution_control)
        _require_fold_semantics(persisted.fold, semantics)
        if semantics.reproduction_fingerprint != attempt.reproduction_fingerprint:
            raise _worker_error("post_claim_reproduction_fingerprint_drift")
        audit = ResearchExecutionAudit.create(
            semantics=semantics,
            attempt_id=str(attempt.attempt_id),
            attempt_ordinal=attempt.ordinal,
            backtest_run_id=str(run_id),
            parent_attempt_id=(
                None
                if attempt.parent_attempt_id is None
                else str(attempt.parent_attempt_id)
            ),
            resume_from_run_id=(
                None
                if attempt.resume_from_run_id is None
                else str(attempt.resume_from_run_id)
            ),
            created_at=attempt.created_at,
        )
        run_result = self._runner.run(
            audit,
            external_should_stop=execution_control.should_stop,
        )
        if type(cast("object", run_result)) is not ResearchFoldRunResult:
            raise _worker_error("invalid_research_fold_run_result")
        if run_result.state is ResearchFoldRunState.STOPPED:
            failure = execution_control.failure
            if failure is not None:
                raise failure
            if execution_control.directive is ResearchExecutionDirective.RUN:
                raise _worker_error("stop_without_durable_control")
            raise _ResearchCooperativeStopError(
                "research backtest stopped cooperatively"
            )
        _require_execution_authority(execution_control)
        if (
            run_result.state is not ResearchFoldRunState.COMPLETED
            or type(run_result.report_evidence) is not BacktestReportEvidence
        ):
            raise _worker_error("invalid_research_fold_run_result")
        return run_result

    def _finish_controlled_attempt(
        self,
        attempt: AttemptPersistenceSpec,
        run_id: BacktestRunId,
        directive: ResearchExecutionDirective,
    ) -> ResearchWorkerResult:
        state = _controlled_worker_state(directive)
        finished_at = self._clock()
        self._coordinator.renew_lease(occurred_at=finished_at)
        if self._checkpoint_available(str(run_id)):
            self._coordinator.record_checkpoint(
                attempt.attempt_id,
                CheckpointRef(str(run_id)),
                occurred_at=finished_at,
            )
        self._coordinator.cooperative_stop_attempt(
            attempt.attempt_id,
            directive,
            occurred_at=finished_at,
        )
        return ResearchWorkerResult(
            attempt_id=attempt.attempt_id,
            backtest_run_id=run_id,
            reproduction_fingerprint=attempt.reproduction_fingerprint,
            state=state,
            failure_code=None,
            error_type=None,
        )
