"""Read-only R3 experiment preflight and deterministic launch orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)
from ditto_analysis.experiments.preflight_authority import canonical_research_cycle_hash

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._executor_probe import probe_executor
from ditto_application.processes.experiments._launch_material import (
    LaunchMaterialInput,
    compile_launch_material,
)
from ditto_application.processes.experiments._launch_saga import (
    DurableLaunchReplay,
    PreparedExperimentLaunch,
    persist_prepared_launch,
    try_replay_durable_launch,
)
from ditto_application.processes.experiments._planning_request_identity import (
    planning_request_hash,
    validate_planning_request_graph,
)
from ditto_application.processes.experiments._preflight_checks import (
    certification_check,
    cycle_authority_check,
    executor_check,
)
from ditto_application.processes.experiments._preflight_codec import (
    decode_preflight_report,
)
from ditto_application.processes.experiments._validation_authority import (
    assess_validation_authority,
)
from ditto_application.processes.experiments._validation_workload import (
    compile_validation_workload,
)
from ditto_application.processes.experiments.planning import (
    CandidateMatrixPlan,
    ExperimentPlanningError,
    ExperimentPlanningSpec,
    ExperimentTrack,
    ExperimentWorkPlan,
    expand_candidate_matrix,
    inspect_candidate_matrix_size,
    plan_experiment_work,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    CandidateExecutorEvidence,
    ExperimentSnapshotIdentity,
    PlanningIdentityInput,
    ResearchCertificationProbe,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchDatasetRequirement,
    ResearchExecutorProbe,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
    validate_planning_identity,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityProbe,
    ResearchValidationAuthorityRequest,
)
from ditto_application.research_validation_protocol import (
    ValidationEligibility,
    ValidationProtocolPlan,
    ValidationProtocolRequest,
)

__all__ = [
    "R3_RESEARCH_CERTIFICATION_PROFILE",
    "CandidateExecutorEvidence",
    "ExperimentLaunchReceipt",
    "ExperimentPlanningProcess",
    "ExperimentPlanningRequest",
    "ExperimentPreflightCheck",
    "ExperimentPreflightReport",
    "ExperimentPreflightStatus",
    "ExperimentSnapshotIdentity",
    "PreflightOutcome",
    "ResearchCertificationProbe",
    "ResearchCertificationRequest",
    "ResearchCertificationResult",
    "ResearchDatasetRequirement",
    "ResearchExecutorProbe",
    "ResearchExecutorProbeRequest",
    "ResearchExecutorProbeResult",
    "ResearchSnapshotEvidence",
    "reconstruct_preflight_report",
]

_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_FOLD_PROTOCOL_ID = "r3-complete-month-walk-forward"
_FOLD_PROTOCOL_VERSION = 1
_FOLD_ID_PREFIX = "r3-fold"


class ExperimentPreflightStatus(StrEnum):
    """Capability granted by a complete preflight report."""

    READY = "ready"
    RESEARCH_ONLY = "research_only"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ExperimentPreflightReport:
    """Complete read-only preflight projection for operator confirmation."""

    status: ExperimentPreflightStatus
    plan_hash: str | None
    checks: tuple[ExperimentPreflightCheck, ...]
    candidate_count: int
    planned_fold_count: int
    budget_run_count: int
    estimated_trading_sessions: int
    estimated_disk_bytes: int
    eligible_month_count: int
    isolation_width_sessions: int
    validation_plan: ValidationProtocolPlan | None
    work_plan: ExperimentWorkPlan | None


@dataclass(frozen=True, slots=True)
class ExperimentLaunchReceipt:
    """Stable result returned after durable readback and final enqueue."""

    experiment_id: str
    status: str
    queue_ordinal: int
    revision: int
    candidate_count: int
    fold_count: int
    plan_hash: str


@dataclass(frozen=True, slots=True)
class _PreparedPlan:
    report: ExperimentPreflightReport
    launch: PreparedExperimentLaunch | None


@dataclass(frozen=True, slots=True)
class _ExecutorPhase:
    request: ExperimentPlanningRequest
    matrix: CandidateMatrixPlan
    executor: ResearchExecutorProbeResult
    checks: tuple[ExperimentPreflightCheck, ExperimentPreflightCheck]


def _check(
    rule_id: str,
    outcome: PreflightOutcome,
    *,
    code: str | None = None,
    reason: str | None = None,
    remediation: str | None = None,
    observed: Mapping[str, object],
    policy: Mapping[str, object],
) -> ExperimentPreflightCheck:
    return ExperimentPreflightCheck(
        rule_id,
        outcome,
        code,
        reason,
        remediation,
        observed,
        policy,
    )


def reconstruct_preflight_report(
    detail: Mapping[str, object],
) -> ExperimentPreflightReport:
    """Reconstruct and verify the complete report persisted in the enqueue event."""
    decoded = decode_preflight_report(
        detail,
        expected_policy_version=_PREFLIGHT_POLICY_VERSION,
    )
    return ExperimentPreflightReport(
        status=ExperimentPreflightStatus(decoded.status),
        plan_hash=decoded.plan_hash,
        checks=decoded.checks,
        candidate_count=decoded.candidate_count,
        planned_fold_count=decoded.planned_fold_count,
        budget_run_count=decoded.budget_run_count,
        estimated_trading_sessions=decoded.estimated_trading_sessions,
        estimated_disk_bytes=decoded.estimated_disk_bytes,
        eligible_month_count=decoded.eligible_month_count,
        isolation_width_sessions=decoded.isolation_width_sessions,
        validation_plan=decoded.validation_plan,
        work_plan=decoded.work_plan,
    )


def _cycle_authority_hash(
    result: ResearchCertificationResult,
    check: ExperimentPreflightCheck,
    request: ExperimentPlanningRequest,
    validation: ValidationProtocolPlan,
) -> str | None:
    snapshot = result.snapshot_evidence
    holdout = validation.reserved_holdout
    if (
        check.outcome is not PreflightOutcome.PASS
        or type(snapshot) is not ResearchSnapshotEvidence
        or holdout is None
    ):
        return None
    return str(
        canonical_research_cycle_hash(
            strategy_family_id=request.strategy_record.strategy_id,
            certified_data_cutoff=snapshot.snapshot_end,
            oos_window=holdout.test_window,
        )
    )


class ExperimentPlanningProcess:
    """Compile preflight facts, then persist only an exactly confirmed plan."""

    def __init__(
        self,
        *,
        reader: ExperimentReaderProtocol,
        writer: ExperimentWriterProtocol,
        certification_probe: ResearchCertificationProbe,
        executor_probe: ResearchExecutorProbe,
        authority_probe: ResearchValidationAuthorityProbe,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._certification_probe = certification_probe
        self._executor_probe = executor_probe
        self._authority_probe = authority_probe

    def preflight(
        self, request: ExperimentPlanningRequest
    ) -> ExperimentPreflightReport:
        """Perform only deterministic computation and read-side probes."""
        return self._prepare(request).report

    def launch(
        self,
        request: ExperimentPlanningRequest,
        *,
        confirmed_plan_hash: str,
    ) -> ExperimentLaunchReceipt:
        """Recompute, confirm, assemble DRAFT, read back, and enqueue last."""
        self._validate_request(request)
        request = replace(
            request,
            dataset_requirements=tuple(
                sorted(request.dataset_requirements, key=lambda item: item.dataset_id)
            ),
        )
        durable = try_replay_durable_launch(
            reader=self._reader,
            experiment_id=request.experiment_id,
            confirmed_plan_hash=confirmed_plan_hash,
            request_hash_factory=lambda: planning_request_hash(request),
        )
        if durable is not None:
            return self._durable_receipt(request, durable)
        prepared = self._prepare(request)
        failed = next(
            (
                check
                for check in prepared.report.checks
                if check.outcome is PreflightOutcome.FAIL
            ),
            None,
        )
        if failed is not None or prepared.launch is None:
            raise AppProcessError(
                "experiment preflight is blocked",
                details={
                    "code": "HARD_GATE_FAILED" if failed is None else failed.code,
                    "reason": None if failed is None else failed.reason,
                    "experiment_id": request.experiment_id,
                },
            )
        if confirmed_plan_hash != prepared.report.plan_hash:
            raise AppProcessError(
                "confirmed experiment plan hash is stale",
                details={
                    "code": "PLAN_HASH_MISMATCH",
                    "expected_plan_hash": prepared.report.plan_hash,
                    "confirmed_plan_hash": confirmed_plan_hash,
                },
            )
        try:
            projection = persist_prepared_launch(
                reader=self._reader,
                writer=self._writer,
                prepared=prepared.launch,
            )
        except AnalysisError as exc:
            raise AppProcessError(
                "experiment launch persistence failed",
                details={"code": "EXPERIMENT_PERSISTENCE_FAILED", **exc.details},
            ) from exc
        return ExperimentLaunchReceipt(
            experiment_id=request.experiment_id,
            status=projection.record.status.value,
            queue_ordinal=cast("int", projection.queue_ordinal),
            revision=projection.revision,
            candidate_count=prepared.report.candidate_count,
            fold_count=prepared.report.planned_fold_count,
            plan_hash=cast("str", prepared.report.plan_hash),
        )

    @staticmethod
    def _durable_receipt(
        request: ExperimentPlanningRequest,
        replay: DurableLaunchReplay,
    ) -> ExperimentLaunchReceipt:
        return ExperimentLaunchReceipt(
            experiment_id=request.experiment_id,
            status=replay.projection.record.status.value,
            queue_ordinal=cast("int", replay.projection.queue_ordinal),
            revision=replay.projection.revision,
            candidate_count=replay.candidate_count,
            fold_count=replay.fold_count,
            plan_hash=replay.plan_hash,
        )

    def _prepare_executor(
        self, request: ExperimentPlanningRequest
    ) -> _PreparedPlan | _ExecutorPhase:
        try:
            self._validate_request(request)
            request = replace(
                request,
                dataset_requirements=tuple(
                    sorted(
                        request.dataset_requirements, key=lambda item: item.dataset_id
                    )
                ),
            )
            matrix = expand_candidate_matrix(request.matrix_spec)
        except AppProcessError as exc:
            return self._compile_failure(request, exc)

        matrix_check = _check(
            "matrix",
            PreflightOutcome.PASS,
            observed={
                "candidate_count": matrix.candidate_count,
                "matrix_hash": matrix.matrix_hash,
            },
            policy={"candidate_limit": request.matrix_spec.candidate_limit},
        )
        executor = probe_executor(self._executor_probe, request, matrix)
        executor_check = self._executor_check(executor, matrix, request)
        if executor_check.outcome is PreflightOutcome.FAIL:
            return _PreparedPlan(
                ExperimentPreflightReport(
                    ExperimentPreflightStatus.BLOCKED,
                    None,
                    (matrix_check, executor_check),
                    matrix.candidate_count,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    None,
                ),
                None,
            )
        return _ExecutorPhase(
            request,
            matrix,
            executor,
            (matrix_check, executor_check),
        )

    def _prepare(self, request: ExperimentPlanningRequest) -> _PreparedPlan:
        phase = self._prepare_executor(request)
        if isinstance(phase, _PreparedPlan):
            return phase
        request = phase.request
        matrix = phase.matrix
        executor = phase.executor
        authority = assess_validation_authority(
            self._authority_probe,
            ResearchValidationAuthorityRequest(
                snapshot_identity=request.snapshot_identity,
                runtime_validation=executor.runtime_validation_evidence,
                declared_protocol=request.validation_request,
                declared_requirements=request.dataset_requirements,
            ),
        )
        initial_checks = (*phase.checks, authority.check)
        validation = authority.validation
        if validation is None or authority.evidence is None:
            return _PreparedPlan(
                ExperimentPreflightReport(
                    ExperimentPreflightStatus.BLOCKED,
                    None,
                    initial_checks,
                    matrix.candidate_count,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    None,
                ),
                None,
            )

        history_check = self._history_check(validation)
        if not validation.launchable or validation.reserved_holdout is None:
            report = ExperimentPreflightReport(
                ExperimentPreflightStatus.BLOCKED,
                None,
                (*initial_checks, history_check),
                matrix.candidate_count,
                0,
                0,
                0,
                0,
                len(validation.eligible_months),
                validation.isolation_width_sessions,
                validation,
                None,
            )
            return _PreparedPlan(report, None)

        workload = compile_validation_workload(
            authority.evidence.protocol,
            validation,
        )
        track = (
            ExperimentTrack.PROMOTION
            if validation.promotion_eligible
            else ExperimentTrack.RESEARCH_ONLY
        )
        try:
            work = plan_experiment_work(
                ExperimentPlanningSpec(
                    matrix=request.matrix_spec,
                    track=track,
                    workload=workload,
                    cost_model=request.cost_model,
                    budget=request.budget,
                    seed=request.seed,
                    worker_count=request.worker_count,
                    failure_policy=request.failure_policy,
                )
            )
        except ExperimentPlanningError as exc:
            if exc.details.get("code") == "BUDGET_EXCEEDED":
                return self._budget_failure(
                    request,
                    validation,
                    matrix,
                    (*initial_checks, history_check),
                    exc,
                )
            return self._compile_failure(
                request, exc, validation=validation, matrix=matrix
            )

        certification_required_from = authority.evidence.protocol.required_input_start
        certification_request = ResearchCertificationRequest(
            profile=R3_RESEARCH_CERTIFICATION_PROFILE,
            required_from=certification_required_from,
            required_to=validation.reserved_holdout.test_window.end,
            requirements=request.dataset_requirements,
            snapshot_identity=request.snapshot_identity,
        )
        try:
            raw_certification = cast(
                "object", self._certification_probe.assess(certification_request)
            )
        except Exception:  # Certification adapters are an untrusted boundary.
            raw_certification = None
        certification = (
            raw_certification
            if type(raw_certification) is ResearchCertificationResult
            else ResearchCertificationResult(
                False,
                "invalid",
                (),
                (),
                ("INVALID_CERTIFICATION_PROBE_RESULT",),
                None,
            )
        )
        base_certification_check = self._certification_check(
            certification, certification_request
        )
        expected_cycle_hash = _cycle_authority_hash(
            certification, base_certification_check, request, validation
        )
        certification_check = cycle_authority_check(
            base_certification_check,
            request,
            expected_cycle_hash,
        )
        budget_check = _check(
            "budget",
            PreflightOutcome.PASS,
            observed={
                "total_run_count": work.estimate.total_run_count,
                "estimated_trading_sessions": work.estimate.estimated_trading_sessions,
                "estimated_disk_bytes": work.estimate.estimated_disk_bytes,
            },
            policy={
                "fold_run_limit": request.budget.fold_run_limit,
                "trading_session_limit": request.budget.trading_session_limit,
                "disk_byte_limit": request.budget.disk_byte_limit,
                "worker_count": request.worker_count,
            },
        )
        checks = (
            *initial_checks,
            history_check,
            certification_check,
            budget_check,
        )
        status = (
            ExperimentPreflightStatus.BLOCKED
            if any(check.outcome is PreflightOutcome.FAIL for check in checks)
            else (
                ExperimentPreflightStatus.READY
                if validation.promotion_eligible
                else ExperimentPreflightStatus.RESEARCH_ONLY
            )
        )
        launch, plan_hash = (None, None)
        if status is not ExperimentPreflightStatus.BLOCKED:
            try:
                launch, plan_hash = self._launch_material(
                    request,
                    validation,
                    work,
                    executor,
                    certification,
                    authority.evidence,
                    checks,
                )
            except AppProcessError as exc:
                if exc.details.get("code") != "PREFLIGHT_DETAIL_TOO_LARGE":
                    raise
                detail_check = _check(
                    "preflight_detail",
                    PreflightOutcome.FAIL,
                    code="PREFLIGHT_DETAIL_TOO_LARGE",
                    reason=str(
                        exc.details.get(
                            "reason", "canonical_preflight_detail_exceeds_limit"
                        )
                    ),
                    remediation=(
                        "reduce the registered preflight matrix or evidence payload"
                    ),
                    observed={
                        "canonical_detail_bytes": exc.details.get(
                            "canonical_detail_bytes"
                        )
                    },
                    policy={
                        "maximum_canonical_detail_bytes": exc.details.get(
                            "maximum_canonical_detail_bytes"
                        )
                    },
                )
                checks = (*checks, detail_check)
                status = ExperimentPreflightStatus.BLOCKED
        report = ExperimentPreflightReport(
            status,
            plan_hash,
            checks,
            matrix.candidate_count,
            matrix.candidate_count * (len(validation.folds) + 1),
            work.estimate.total_run_count,
            work.estimate.estimated_trading_sessions,
            work.estimate.estimated_disk_bytes,
            len(validation.eligible_months),
            validation.isolation_width_sessions,
            validation,
            work,
        )
        return _PreparedPlan(
            report, launch if status is not ExperimentPreflightStatus.BLOCKED else None
        )

    @staticmethod
    def _validate_request(request: ExperimentPlanningRequest) -> None:
        validate_planning_request_graph(request)
        validate_planning_identity(
            PlanningIdentityInput(
                request.experiment_id,
                request.research_cycle_id,
                request.research_cycle_hash,
                request.strategy_record,
                request.snapshot_identity,
                request.dataset_requirements,
                request.created_at,
            )
        )
        if (
            type(request.validation_request) is not ValidationProtocolRequest
            or request.validation_request.planning_decision_date
            != request.created_at.date()
        ):
            raise AppProcessError(
                "planning decision date must match the canonical launch timestamp",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "planning_decision_date_created_at_mismatch",
                },
            )

    @staticmethod
    def _history_check(plan: ValidationProtocolPlan) -> ExperimentPreflightCheck:
        if plan.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE:
            outcome, code, remediation = PreflightOutcome.PASS, None, None
        elif plan.eligibility is ValidationEligibility.RESEARCH_ONLY:
            outcome = PreflightOutcome.WARN
            code = "INSUFFICIENT_PROMOTION_HISTORY"
            remediation = "collect 96 continuous eligible complete months before review"
        else:
            outcome = PreflightOutcome.FAIL
            code = "INSUFFICIENT_HISTORY"
            remediation = "collect at least 37 continuous eligible complete months"
        return _check(
            "history",
            outcome,
            code=code,
            reason=None if code is None else "continuous_complete_months_below_policy",
            remediation=remediation,
            observed={"eligible_month_count": len(plan.eligible_months)},
            policy={"research_minimum": 37, "promotion_minimum": 96},
        )

    @staticmethod
    def _executor_check(
        result: ResearchExecutorProbeResult,
        matrix: CandidateMatrixPlan,
        request: ExperimentPlanningRequest,
    ) -> ExperimentPreflightCheck:
        return executor_check(result, matrix, request)

    @staticmethod
    def _certification_check(
        result: ResearchCertificationResult,
        request: ResearchCertificationRequest,
    ) -> ExperimentPreflightCheck:
        return certification_check(result, request)

    @staticmethod
    def _compile_failure(
        request: ExperimentPlanningRequest,
        error: AppProcessError,
        *,
        validation: ValidationProtocolPlan | None = None,
        matrix: CandidateMatrixPlan | None = None,
    ) -> _PreparedPlan:
        code = str(error.details.get("code", "SPEC_INVALID"))
        candidate_count = 0 if matrix is None else matrix.candidate_count
        observed = dict(error.details)
        reason = str(error.details.get("reason", "planning_compile_failed"))
        if code == "MATRIX_TOO_LARGE":
            matrix_size = inspect_candidate_matrix_size(request.matrix_spec)
            candidate_count = matrix_size.candidate_count
            expected_details = {
                "code": "MATRIX_TOO_LARGE",
                "candidate_count": matrix_size.candidate_count,
                "candidate_limit": matrix_size.candidate_limit,
            }
            if dict(error.details) == expected_details and matrix_size.exceeds_limit:
                observed = expected_details
            else:
                code = "SPEC_INVALID"
                reason = "matrix_size_error_detail_mismatch"
                observed = {
                    "candidate_count": matrix_size.candidate_count,
                    "candidate_limit": matrix_size.candidate_limit,
                    "reported_details_match": False,
                }
        check = _check(
            "compile",
            PreflightOutcome.FAIL,
            code=code,
            reason=reason,
            remediation="fix validation, matrix, or registered resource limits",
            observed=observed,
            policy={"profile": R3_RESEARCH_CERTIFICATION_PROFILE},
        )
        return _PreparedPlan(
            ExperimentPreflightReport(
                ExperimentPreflightStatus.BLOCKED,
                None,
                (check,),
                candidate_count,
                0,
                0,
                0,
                0,
                0 if validation is None else len(validation.eligible_months),
                0 if validation is None else validation.isolation_width_sessions,
                validation,
                None,
            ),
            None,
        )

    @staticmethod
    def _budget_failure(
        request: ExperimentPlanningRequest,
        validation: ValidationProtocolPlan,
        matrix: CandidateMatrixPlan,
        checks: tuple[ExperimentPreflightCheck, ...],
        error: ExperimentPlanningError,
    ) -> _PreparedPlan:
        observed = dict(error.details)
        budget_check = _check(
            "budget",
            PreflightOutcome.FAIL,
            code="BUDGET_EXCEEDED",
            reason="resource_estimate_exceeds_registered_budget",
            remediation="reduce the candidate matrix or increase registered limits",
            observed=observed,
            policy={
                "fold_run_limit": request.budget.fold_run_limit,
                "trading_session_limit": request.budget.trading_session_limit,
                "disk_byte_limit": request.budget.disk_byte_limit,
            },
        )
        return _PreparedPlan(
            ExperimentPreflightReport(
                ExperimentPreflightStatus.BLOCKED,
                None,
                (*checks, budget_check),
                matrix.candidate_count,
                matrix.candidate_count
                * (len(validation.folds) + (validation.reserved_holdout is not None)),
                cast("int", observed["total_run_count"]),
                cast("int", observed["estimated_trading_sessions"]),
                cast("int", observed["estimated_disk_bytes"]),
                len(validation.eligible_months),
                validation.isolation_width_sessions,
                validation,
                None,
            ),
            None,
        )

    @staticmethod
    def _launch_material(
        request: ExperimentPlanningRequest,
        validation: ValidationProtocolPlan,
        work: ExperimentWorkPlan,
        executor: ResearchExecutorProbeResult,
        certification: ResearchCertificationResult,
        authority: ResearchValidationAuthorityEvidence,
        checks: tuple[ExperimentPreflightCheck, ...],
    ) -> tuple[PreparedExperimentLaunch | None, str | None]:
        return compile_launch_material(
            LaunchMaterialInput(
                request=request,
                validation=validation,
                work=work,
                executor=executor,
                certification=certification,
                authority=authority,
                checks=checks,
                preflight_policy_version=_PREFLIGHT_POLICY_VERSION,
                fold_protocol_id=_FOLD_PROTOCOL_ID,
                fold_protocol_version=_FOLD_PROTOCOL_VERSION,
                fold_id_prefix=_FOLD_ID_PREFIX,
            )
        )
