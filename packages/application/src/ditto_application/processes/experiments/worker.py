"""Execution-owned first attempt and fail-closed R3 research fold worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    BacktestRunId,
    ContentHash,
    ExperimentFailureCode,
    ExperimentStage,
    ExperimentStatus,
    FoldRole,
    FoldView,
    SchedulerLease,
    canonical_payload,
)
from ditto_strategy.errors import StrategyError

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import BacktestService
from ditto_application.processes.experiments._execution_resolution_evidence import (
    ResearchExecutionInputError,
)
from ditto_application.processes.experiments.backtest_service_wiring import (
    ClosedBacktestServiceGraph,
    require_closed_backtest_service,
)
from ditto_application.processes.experiments.coordinator import (
    ExperimentDispatch,
    PersistedAttemptStart,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ExactBenchmarkBinding,
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.scheduler_store import FirstAttempt

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


class ResearchBacktestBuildSource(StrEnum):
    """Declared resolution path for an attested research backtest build."""

    FROZEN_AUDIT_BUNDLE = "frozen_audit_bundle"
    PROVIDER_LATEST = "provider_latest"
    CATALOG_LATEST = "catalog_latest"


@dataclass(frozen=True, slots=True)
class ResearchBacktestBuildAttestation:
    """Typed evidence proving a BacktestService was built from one audit."""

    source: ResearchBacktestBuildSource
    audit_bundle_hash: ContentHash
    reproduction_fingerprint: ContentHash
    backtest_run_id: str
    strategy: StrategyExecutionBinding | BaselineExecutorBinding
    snapshot: ResearchSnapshotBinding
    execution_config: BacktestExecutionConfigBinding
    execution_config_hash: ContentHash
    feed_manifest_hash: str
    policy_hash: str
    model_evidence_hash: ContentHash
    benchmark_binding_hash: ContentHash | None
    environment: CodeEnvironmentLock

    @classmethod
    def from_audit(
        cls,
        audit: ResearchExecutionAudit,
    ) -> ResearchBacktestBuildAttestation:
        """Build the only attestation accepted by the fold runner."""
        semantics = audit.semantics
        backtest = semantics.backtest
        benchmark_hash = (
            None if backtest.benchmark is None else backtest.benchmark.canonical_hash
        )
        return cls(
            source=ResearchBacktestBuildSource.FROZEN_AUDIT_BUNDLE,
            audit_bundle_hash=audit.bundle_hash,
            reproduction_fingerprint=audit.reproduction_fingerprint,
            backtest_run_id=audit.backtest_run_id,
            strategy=semantics.strategy,
            snapshot=semantics.snapshot,
            execution_config=backtest,
            execution_config_hash=backtest.canonical_hash,
            feed_manifest_hash=backtest.data_feed_manifest_hash,
            policy_hash=semantics.policy.canonical_hash,
            model_evidence_hash=backtest.policy_model_evidence_hash,
            benchmark_binding_hash=benchmark_hash,
            environment=semantics.environment,
        )


@dataclass(frozen=True, slots=True)
class VerifiedResearchBacktestBuild:
    """Backtest service plus exact construction evidence for runner validation."""

    service: BacktestService
    attestation: ResearchBacktestBuildAttestation
    graph: ClosedBacktestServiceGraph
    construction_seal: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )


_RESEARCH_BACKTEST_BUILD_SEAL = object()


def seal_verified_research_backtest_build(
    *,
    service: BacktestService,
    attestation: ResearchBacktestBuildAttestation,
    graph: ClosedBacktestServiceGraph,
    audit: ResearchExecutionAudit,
    external_should_stop: Callable[[], bool],
) -> VerifiedResearchBacktestBuild:
    """Construct one official build only after full audit-bound verification."""
    if (
        type(attestation) is not ResearchBacktestBuildAttestation
        or attestation != ResearchBacktestBuildAttestation.from_audit(audit)
    ):
        raise _worker_error("research_backtest_attestation_drift")
    if type(service) is not BacktestService or graph.service is not service:
        raise _worker_error("invalid_research_backtest_service_graph")
    require_closed_backtest_service(
        graph,
        expected_audit=audit,
        expected_should_stop=external_should_stop,
    )
    build = VerifiedResearchBacktestBuild(service, attestation, graph)
    object.__setattr__(
        build,
        "construction_seal",
        _RESEARCH_BACKTEST_BUILD_SEAL,
    )
    return build


def _require_verified_research_backtest_build_seal(
    build: VerifiedResearchBacktestBuild,
) -> None:
    """Reject builds that did not pass the official construction boundary."""
    if build.construction_seal is not _RESEARCH_BACKTEST_BUILD_SEAL:
        raise _worker_error("unsealed_research_backtest_build")


@dataclass(frozen=True, slots=True)
class _ResearchExecutionAuditAnchor:
    """Immutable pre-factory identity rebuilt from authoritative audit fields."""

    audit_payload: bytes
    audit_bundle_hash: str
    semantics_payload: bytes
    reproduction_fingerprint: str


def _rebuild_execution_audit_anchor(
    audit: object,
) -> _ResearchExecutionAuditAnchor:
    """Validate derived audit identities and return detached immutable evidence."""
    if type(audit) is not ResearchExecutionAudit:
        raise _worker_error("research_execution_audit_drift")
    typed_audit = audit
    semantics = typed_audit.semantics
    if type(semantics) is not ResearchExecutionSemantics:
        raise _worker_error("research_execution_audit_drift")
    backtest = semantics.backtest
    if type(backtest) is not BacktestExecutionConfigBinding:
        raise _worker_error("research_execution_audit_drift")
    benchmark = backtest.benchmark
    if benchmark is None:
        rebuilt_benchmark = None
    else:
        if type(benchmark) is not ExactBenchmarkBinding:
            raise _worker_error("research_execution_audit_drift")
        rebuilt_benchmark = replace(benchmark)
        if (
            type(benchmark.canonical_hash) is not ContentHash
            or benchmark.canonical_hash != rebuilt_benchmark.canonical_hash
        ):
            raise _worker_error("research_execution_audit_drift")
    rebuilt_backtest = replace(backtest, benchmark=rebuilt_benchmark)
    if (
        type(backtest.canonical_hash) is not ContentHash
        or type(backtest.policy_model_evidence_hash) is not ContentHash
        or backtest.canonical_hash != rebuilt_backtest.canonical_hash
        or backtest.policy_model_evidence_hash
        != rebuilt_backtest.policy_model_evidence_hash
    ):
        raise _worker_error("research_execution_audit_drift")
    rebuilt_semantics = replace(semantics, backtest=rebuilt_backtest)
    rebuilt_audit = ResearchExecutionAudit.create(
        semantics=rebuilt_semantics,
        attempt_id=typed_audit.attempt_id,
        attempt_ordinal=typed_audit.attempt_ordinal,
        backtest_run_id=typed_audit.backtest_run_id,
        parent_attempt_id=typed_audit.parent_attempt_id,
        resume_from_run_id=typed_audit.resume_from_run_id,
        created_at=typed_audit.created_at,
    )
    if (
        type(semantics.canonical_payload) is not bytes
        or type(semantics.reproduction_fingerprint) is not ContentHash
        or type(typed_audit.canonical_payload) is not bytes
        or type(typed_audit.bundle_hash) is not ContentHash
        or semantics.canonical_payload != rebuilt_semantics.canonical_payload
        or semantics.reproduction_fingerprint
        != rebuilt_semantics.reproduction_fingerprint
        or typed_audit.canonical_payload != rebuilt_audit.canonical_payload
        or typed_audit.bundle_hash != rebuilt_audit.bundle_hash
    ):
        raise _worker_error("research_execution_audit_drift")
    return _ResearchExecutionAuditAnchor(
        audit_payload=bytes(rebuilt_audit.canonical_payload),
        audit_bundle_hash=str(rebuilt_audit.bundle_hash),
        semantics_payload=bytes(rebuilt_semantics.canonical_payload),
        reproduction_fingerprint=str(rebuilt_semantics.reproduction_fingerprint),
    )


class ResearchFoldRunState(StrEnum):
    """Typed numerical runner outcome consumed by the durable worker."""

    COMPLETED = "completed"
    STOPPED = "stopped"


class ResearchFoldRunner(Protocol):
    """Run one existing deterministic backtest path from an exact audit bundle."""

    def run(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> ResearchFoldRunState:
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
    ) -> ResearchFoldRunState:
        """Build and run the existing single-backtest application service."""
        if external_should_stop():
            return ResearchFoldRunState.STOPPED
        audit_anchor = _rebuild_execution_audit_anchor(audit)
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
        if _rebuild_execution_audit_anchor(audit) != audit_anchor:
            raise _worker_error("research_execution_audit_drift")
        if external_should_stop():
            return ResearchFoldRunState.STOPPED
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
        _require_verified_research_backtest_build_seal(build)
        try:
            BacktestService.run(service)
        except StrategyError as error:
            raise ResearchCandidateExecutionError(
                "research candidate strategy execution failed"
            ) from error
        if service.last_run_cancelled:
            return ResearchFoldRunState.STOPPED
        return ResearchFoldRunState.COMPLETED


class ResearchWorkerCoordinator(Protocol):
    """Narrow lease-fenced coordinator operations owned by the worker."""

    def renew_lease(self, *, occurred_at: datetime) -> SchedulerLease: ...

    def start_attempt(
        self,
        dispatch: ExperimentDispatch,
        *,
        occurred_at: datetime,
    ) -> PersistedAttemptStart: ...

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        occurred_at: datetime,
    ) -> object: ...

    def fail_attempt(
        self,
        attempt_id: AttemptId,
        failure_code: ExperimentFailureCode,
        *,
        occurred_at: datetime,
    ) -> object: ...


_TERMINAL_AUTHORITY_LOSS_CODES = frozenset(
    {"LEASE_LOST", "EXPERIMENT_INTEGRITY_FAILED"}
)


class ResearchExecutionControl:
    """Lease-aware cooperative stop callback polled by BacktestService."""

    def __init__(
        self,
        *,
        coordinator: ResearchWorkerCoordinator,
        clock: Callable[[], datetime],
    ) -> None:
        self._coordinator = coordinator
        self._clock = clock
        self._failure: AppProcessError | None = None

    @property
    def failure(self) -> AppProcessError | None:
        """Return the first renewal failure observed by the engine fence."""
        return self._failure

    def should_stop(self) -> bool:
        """Renew once per engine poll and fail closed on any renewal error."""
        if self._failure is not None:
            return True
        try:
            self._coordinator.renew_lease(occurred_at=self._clock())
        except AppProcessError as error:
            self._failure = error
            return True
        except Exception as error:  # pragma: no cover - defensive port boundary
            self._failure = AppProcessError(
                "research execution lease renewal failed",
                details={
                    "code": "SYSTEM_ERROR",
                    "reason": "lease_renewal_failed",
                    "error_type": type(error).__name__,
                },
            )
            return True
        return False


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
    """Freeze a fingerprint and stable first-attempt identity before claim."""

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


class ResearchWorkerState(StrEnum):
    """Stable one-attempt worker outcome."""

    COMPLETED = "completed"
    CANDIDATE_FAILED = "candidate_failed"
    INPUT_FAILED = "input_failed"
    SYSTEM_FAILED = "system_failed"


@dataclass(frozen=True, slots=True)
class ResearchWorkerResult:
    """Serializable worker result derived from a durable attempt transition."""

    attempt_id: AttemptId
    backtest_run_id: BacktestRunId
    reproduction_fingerprint: ContentHash
    state: ResearchWorkerState
    failure_code: ExperimentFailureCode | None
    error_type: str | None


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


class ResearchExperimentWorker:
    """Execute a claimed fold and persist one typed terminal outcome."""

    def __init__(
        self,
        *,
        coordinator: ResearchWorkerCoordinator,
        semantics_resolver: ResearchExecutionSemanticsResolver,
        runner: ResearchFoldRunner,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._resolver = semantics_resolver
        self._runner = runner
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
        persisted = self._coordinator.start_attempt(
            dispatch,
            occurred_at=occurred_at,
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
            clock=self._clock,
        )
        try:
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
            run_state = self._runner.run(
                audit,
                external_should_stop=execution_control.should_stop,
            )
            if execution_control.failure is not None:
                raise execution_control.failure
            if run_state is ResearchFoldRunState.STOPPED:
                raise _ResearchCooperativeStopError(
                    "research backtest stopped cooperatively"
                )
            if run_state is not ResearchFoldRunState.COMPLETED:
                raise _worker_error("invalid_research_fold_run_state")
        except Exception as error:
            effective_error = execution_control.failure or error
            if _lost_terminal_authority(effective_error):
                if effective_error is error:
                    raise
                raise effective_error from error
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
