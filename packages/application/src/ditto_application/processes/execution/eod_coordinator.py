"""EOD 纯业务编排：逐策略数据就绪判断、运行和信号发布。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Literal, cast

import orjson

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.signal_package import SignalPackage
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.queries.data_readiness import (
    DataReadinessQueryFacade,
    DatasetReadinessAssessment,
    DatasetReadinessRequirement,
    PartitionHealth,
)

__all__ = [
    "DatasetReadiness",
    "EodCoordinator",
    "EodStrategyOutcome",
    "EodStrategyRequest",
    "R2PreflightPolicy",
]


@dataclass(frozen=True)
class DatasetReadiness:
    """一个数据集在目标信号日的可用状态。"""

    dataset: str
    status: Literal["ready", "missing", "stale", "dq_failed", "unknown"]
    snapshot_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class EodStrategyRequest:
    """EOD 运行所需的已发布策略身份和数据依赖。"""

    strategy_id: str
    strategy_version: str
    required_datasets: tuple[str, ...]
    lookback_start: str | None = None


@dataclass(frozen=True)
class EodStrategyOutcome:
    """单策略机器可读 EOD 结果。"""

    strategy_id: str
    strategy_version: str
    batch_key: str
    status: Literal["completed", "no_rebalance", "blocked", "failed", "rerun_conflict"]
    required_dataset_states: tuple[DatasetReadiness, ...]
    artifact_id: str | None = None
    checksum: str | None = None
    reason: str = ""
    r2_preflight_status: Literal["not_run", "ready", "blocked"] = "not_run"


@dataclass(frozen=True, slots=True)
class R2PreflightPolicy:
    """R1 migration policy for the R2 data-product gate."""

    mode: Literal["shadow", "required"] = "shadow"
    certification_profile: str = "r2-modern-a-share-v1"

    def __post_init__(self) -> None:
        """Validate the explicit migration mode and certification profile."""
        if self.mode not in {"shadow", "required"}:
            raise AppProcessError(f"invalid R2 preflight mode: {self.mode}")
        if not self.certification_profile.strip():
            raise AppProcessError("R2 certification profile cannot be empty")


type EodOutcomeStatus = Literal[
    "completed", "no_rebalance", "blocked", "failed", "rerun_conflict"
]


type _RunStrategy = Callable[[EodStrategyRequest, str, str], object]
type _PublishSignals = Callable[[object, Mapping[str, str]], SignalPackage]
type _FinalizeSignals = Callable[[SignalPackage], SignalPackage]
type _FindStagedSignals = Callable[[EodStrategyRequest, str, str], SignalPackage | None]


class _RunLifecycleTransitionError(RuntimeError):
    """运行生命周期持久化未完成；不得把业务结果暴露为 completed。"""


class EodCoordinator:
    """让调度器和 CLI 共享同一套逐策略 EOD 决策。"""

    def __init__(
        self,
        *,
        run_strategy: _RunStrategy,
        publish_signals: _PublishSignals,
        finalize_signals: _FinalizeSignals,
        find_staged_signals: _FindStagedSignals,
        run_service: RunLifecycleService,
        data_readiness_query: DataReadinessQueryFacade | None = None,
        r2_preflight_policy: R2PreflightPolicy = R2PreflightPolicy(),
    ) -> None:
        self._run_strategy = run_strategy
        self._publish_signals = publish_signals
        self._finalize_signals = finalize_signals
        self._find_staged_signals = find_staged_signals
        self._run_service = run_service
        self._data_readiness_query = data_readiness_query
        self._r2_preflight_policy = r2_preflight_policy

    def run(
        self,
        *,
        signal_date: str,
        strategies: Sequence[EodStrategyRequest],
        dataset_states: Mapping[str, DatasetReadiness],
        strategy_id: str | None = None,
    ) -> tuple[EodStrategyOutcome, ...]:
        """按策略独立校验依赖并运行；不相关数据集失败不会扩散。"""
        outcomes: list[EodStrategyOutcome] = []
        for request in strategies:
            if strategy_id is not None and request.strategy_id != strategy_id:
                continue
            batch_key = (
                f"eod-{signal_date}-{request.strategy_id}-{request.strategy_version}"
            )
            required = tuple(
                _validated_readiness(
                    dataset_states.get(
                        dataset,
                        DatasetReadiness(dataset=dataset, status="unknown"),
                    )
                )
                for dataset in request.required_datasets
            )
            required, r2_preflight_status = self._apply_r2_preflight(
                request=request,
                signal_date=signal_date,
                required=required,
            )
            blocked = [state for state in required if state.status != "ready"]
            if blocked:
                reason = (
                    "R2_DATA_PREFLIGHT_BLOCKED"
                    if self._r2_preflight_policy.mode == "required"
                    and r2_preflight_status == "blocked"
                    and any(
                        state.reason.startswith(
                            (
                                "CERTIFICATION_",
                                "DATASET_",
                                "PARTITION_",
                                "PIT_",
                                "SOURCE_",
                                "R2_",
                            )
                        )
                        for state in blocked
                    )
                    else "REQUIRED_DATA_NOT_READY"
                )
                outcomes.append(
                    replace(
                        self._persist_blocked_outcome(
                            request=request,
                            batch_key=batch_key,
                            signal_date=signal_date,
                            required=required,
                            reason=reason,
                        ),
                        r2_preflight_status=r2_preflight_status,
                    )
                )
                continue
            recovered = self._recover_completed_staged(
                request=request,
                signal_date=signal_date,
                batch_key=batch_key,
                required=required,
            )
            if recovered is not None:
                outcomes.append(
                    replace(recovered, r2_preflight_status=r2_preflight_status)
                )
                continue
            outcomes.append(
                replace(
                    self._execute_ready_request(
                        request=request,
                        batch_key=batch_key,
                        signal_date=signal_date,
                        required=required,
                    ),
                    r2_preflight_status=r2_preflight_status,
                )
            )
        return tuple(outcomes)

    def _apply_r2_preflight(
        self,
        *,
        request: EodStrategyRequest,
        signal_date: str,
        required: tuple[DatasetReadiness, ...],
    ) -> tuple[
        tuple[DatasetReadiness, ...],
        Literal["not_run", "ready", "blocked"],
    ]:
        """Run the R2 query in shadow or fail-closed required mode."""
        query = self._data_readiness_query
        if query is None:
            if self._r2_preflight_policy.mode == "shadow":
                return required, "not_run"
            return (
                tuple(
                    replace(
                        state,
                        status="unknown",
                        reason=(
                            f"R2_PREFLIGHT_NOT_CONFIGURED:{state.dataset}:{signal_date}"
                        ),
                    )
                    for state in required
                ),
                "blocked",
            )
        required_to = date.fromisoformat(signal_date)
        required_from = date.fromisoformat(request.lookback_start or signal_date)
        requirements = tuple(
            DatasetReadinessRequirement(
                dataset_id=state.dataset,
                required_from=required_from,
                required_to=required_to,
                expected_snapshot_ids=(
                    (state.snapshot_id,) if state.snapshot_id is not None else ()
                ),
                requires_pit_universe=state.dataset
                in {"stock_basic", "stock_status", "index_weight"},
            )
            for state in required
        )
        partition_health = {
            state.dataset: PartitionHealth(
                status=state.status,
                snapshot_id=state.snapshot_id,
            )
            for state in required
        }
        try:
            report = query.assess(
                profile=self._r2_preflight_policy.certification_profile,
                requirements=requirements,
                partition_health=partition_health,
            )
        except Exception:
            if self._r2_preflight_policy.mode == "shadow":
                return required, "blocked"
            return (
                tuple(
                    replace(
                        state,
                        status="unknown",
                        reason=f"R2_PREFLIGHT_QUERY_FAILED:{state.dataset}:{signal_date}",
                    )
                    for state in required
                ),
                "blocked",
            )
        if report.status == "ready" or self._r2_preflight_policy.mode == "shadow":
            return required, report.status
        assessments = {item.dataset_id: item for item in report.datasets}
        return (
            tuple(
                _blocked_by_r2_assessment(
                    state,
                    assessments.get(state.dataset),
                    required_to=required_to,
                )
                for state in required
            ),
            "blocked",
        )

    def _execute_ready_request(
        self,
        *,
        request: EodStrategyRequest,
        batch_key: str,
        signal_date: str,
        required: tuple[DatasetReadiness, ...],
    ) -> EodStrategyOutcome:
        """Run one ready strategy and expose signals only after run completion."""
        stage = "create_run"
        claimed = False
        package: SignalPackage | None = None
        try:
            config_json = self._create_run(
                request=request,
                batch_key=batch_key,
                signal_date=signal_date,
                required=required,
                outcome="running",
            )
            stage = "mark_running"
            self._mark_running_or_retry(batch_key, config_json=config_json)
            claimed = True
            stage = "run_strategy"
            target = self._run_strategy(request, signal_date, batch_key)
            stage = "publish_signals"
            package = self._publish_signals(
                target,
                {state.dataset: cast(str, state.snapshot_id) for state in required},
            )
            if _package_status(package) == "failed":
                self._run_service.mark_failed(
                    batch_key,
                    "failed:INVALID_SIGNAL_PACKAGE_OUTCOME",
                )
                return _package_outcome(
                    request=request,
                    batch_key=batch_key,
                    required=required,
                    package=package,
                )
            stage = "mark_completed"
            if self._run_service.mark_completed(batch_key) is False:
                raise _RunLifecycleTransitionError
            stage = "finalize_signals"
            package = self._finalize_signals(package)
            outcome = _package_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=package,
            )
            if outcome.status == "failed":
                raise AppProcessError("finalized signal package outcome is invalid")
            return outcome
        except Exception as exc:
            error_code, outcome_status = _failure_outcome(exc, stage=stage)
            prefix = "blocked" if outcome_status == "blocked" else "failed"
            if claimed and stage != "finalize_signals":
                self._run_service.mark_failed(batch_key, f"{prefix}:{error_code}")
            return EodStrategyOutcome(
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                batch_key=batch_key,
                status=outcome_status,
                required_dataset_states=required,
                artifact_id=(
                    _optional_str(package.artifact_id) if package is not None else None
                ),
                checksum=(
                    _optional_str(package.checksum) if package is not None else None
                ),
                reason=error_code,
            )

    def _persist_blocked_outcome(
        self,
        *,
        request: EodStrategyRequest,
        batch_key: str,
        signal_date: str,
        required: tuple[DatasetReadiness, ...],
        reason: str = "REQUIRED_DATA_NOT_READY",
    ) -> EodStrategyOutcome:
        """Persist blocked evidence, never claiming success after a DB failure."""
        stage = "create_run"
        try:
            config_json = self._create_run(
                request=request,
                batch_key=batch_key,
                signal_date=signal_date,
                required=required,
                outcome="blocked",
            )
            stage = "mark_failed"
            persisted = self._run_service.mark_pending_failed(
                batch_key,
                f"blocked:{reason}",
            )
            if persisted is False:
                refreshed = self._run_service.refresh_blocked_evidence(
                    batch_key,
                    config_json=config_json,
                )
                if refreshed is not True and not self._is_same_blocked_run(
                    request,
                    batch_key,
                    config_json=config_json,
                    reason=reason,
                ):
                    raise _RunLifecycleTransitionError
        except Exception as exc:
            error_code, _ = _failure_outcome(exc, stage=stage)
            return EodStrategyOutcome(
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                batch_key=batch_key,
                status="failed",
                required_dataset_states=required,
                reason=error_code,
            )
        return EodStrategyOutcome(
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            batch_key=batch_key,
            status="blocked",
            required_dataset_states=required,
            reason=reason,
        )

    def _recover_completed_staged(
        self,
        *,
        request: EodStrategyRequest,
        signal_date: str,
        batch_key: str,
        required: tuple[DatasetReadiness, ...],
    ) -> EodStrategyOutcome | None:
        """Recompute canonical evidence before resuming a completed run's activation."""
        package: SignalPackage | None = None
        try:
            run = self._run_service.get_run(batch_key)
            if run is None or str(run.status) != "completed":
                return None
            package = self._find_staged_signals(request, signal_date, batch_key)
            if package is None:
                return None
        except Exception:
            return _recovery_failure_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=package,
                reason="SIGNAL_PACKAGE_RECOVERY_FAILED",
            )
        return self._reconcile_completed_package(
            request=request,
            signal_date=signal_date,
            batch_key=batch_key,
            required=required,
            package=package,
        )

    def _reconcile_completed_package(
        self,
        *,
        request: EodStrategyRequest,
        signal_date: str,
        batch_key: str,
        required: tuple[DatasetReadiness, ...],
        package: SignalPackage,
    ) -> EodStrategyOutcome:
        try:
            snapshots = {
                state.dataset: state.snapshot_id
                for state in required
                if state.status == "ready" and state.snapshot_id is not None
            }
            target = self._run_strategy(request, signal_date, batch_key)
            current = self._publish_signals(target, snapshots)
        except Exception:
            return _recovery_failure_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=package,
                reason="SIGNAL_PACKAGE_RECOVERY_FAILED",
            )
        if current.outcome == "rerun_conflict":
            return _package_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=current,
            )
        if package.artifact_status == "active":
            if current.dataset_snapshot_ids != snapshots:
                return _recovery_mismatch_outcome(
                    request=request,
                    batch_key=batch_key,
                    required=required,
                    package=current,
                )
            return self._finalize_recovered_package(
                request=request,
                batch_key=batch_key,
                required=required,
                package=current,
                invalid_error="recomputed signal package outcome is invalid",
            )
        if (
            package.dataset_snapshot_ids != snapshots
            or current.artifact_id != package.artifact_id
            or current.checksum != package.checksum
        ):
            return _recovery_mismatch_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=current,
            )
        return self._finalize_recovered_package(
            request=request,
            batch_key=batch_key,
            required=required,
            package=package,
            invalid_error="recovered signal package outcome is invalid",
        )

    def _finalize_recovered_package(
        self,
        *,
        request: EodStrategyRequest,
        batch_key: str,
        required: tuple[DatasetReadiness, ...],
        package: SignalPackage,
        invalid_error: str,
    ) -> EodStrategyOutcome:
        try:
            finalized = self._finalize_signals(package)
            return _validated_package_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=finalized,
                error=invalid_error,
            )
        except Exception:
            return _recovery_failure_outcome(
                request=request,
                batch_key=batch_key,
                required=required,
                package=package,
                reason="SIGNAL_PACKAGE_FINALIZE_FAILED",
            )

    def _create_run(
        self,
        *,
        request: EodStrategyRequest,
        batch_key: str,
        signal_date: str,
        required: tuple[DatasetReadiness, ...],
        outcome: Literal["blocked", "running"],
    ) -> str:
        """以 deterministic batch key 写入当前 EOD 尝试的可查询控制面事实。"""
        config_json = orjson.dumps(
            {
                "batch_key": batch_key,
                "outcome": outcome,
                "required_dataset_states": [asdict(state) for state in required],
                "signal_date": signal_date,
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode("utf-8")
        self._run_service.create_run(
            run_id=batch_key,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            mode="recommendation",
            config_json=config_json,
        )
        return config_json

    def _mark_running_or_retry(self, batch_key: str, *, config_json: str) -> None:
        """Start a new attempt without reopening a completed deterministic run."""
        if self._run_service.mark_running(batch_key):
            return
        existing = self._run_service.get_run(batch_key)
        if existing is None or str(existing.status) != "failed":
            raise _RunLifecycleTransitionError
        if not self._run_service.retry_failed(batch_key, config_json=config_json):
            raise _RunLifecycleTransitionError
        if not self._run_service.mark_running(batch_key):
            raise _RunLifecycleTransitionError

    def _is_same_blocked_run(
        self,
        request: EodStrategyRequest,
        batch_key: str,
        *,
        config_json: str,
        reason: str = "REQUIRED_DATA_NOT_READY",
    ) -> bool:
        existing = self._run_service.get_run(batch_key)
        return bool(
            existing is not None
            and str(existing.status) == "failed"
            and existing.strategy_id == request.strategy_id
            and existing.strategy_version == request.strategy_version
            and existing.mode == "recommendation"
            and existing.error_message == f"blocked:{reason}"
            and existing.config_json == config_json
        )


def _optional_str(value: object) -> str | None:
    """只把真实字符串暴露为 outcome 证据，避免 mock/未知对象泄漏。"""
    return value if isinstance(value, str) and value else None


def _blocked_by_r2_assessment(
    state: DatasetReadiness,
    assessment: DatasetReadinessAssessment | None,
    *,
    required_to: date,
) -> DatasetReadiness:
    """Project a blocked R2 assessment into the existing EOD evidence shape."""
    if assessment is not None and assessment.status == "ready":
        return state
    reason = (
        assessment.reason_codes[0]
        if assessment is not None and assessment.reason_codes
        else "R2_DATASET_ASSESSMENT_MISSING"
    )
    return replace(
        state,
        status="unknown",
        reason=f"{reason}:{state.dataset}:{required_to.isoformat()}",
    )


def _package_status(package: SignalPackage) -> EodOutcomeStatus:
    raw_status = getattr(package, "outcome", None)
    status = raw_status if isinstance(raw_status, str) else None
    if status is None:
        status = "no_rebalance" if not getattr(package, "intents", ()) else "completed"
    if status not in {"completed", "no_rebalance", "rerun_conflict"}:
        return "failed"
    return cast("EodOutcomeStatus", status)


def _package_outcome(
    *,
    request: EodStrategyRequest,
    batch_key: str,
    required: tuple[DatasetReadiness, ...],
    package: SignalPackage,
) -> EodStrategyOutcome:
    status = _package_status(package)
    return EodStrategyOutcome(
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        batch_key=batch_key,
        status=status,
        required_dataset_states=required,
        artifact_id=_optional_str(getattr(package, "artifact_id", None)),
        checksum=_optional_str(getattr(package, "checksum", None)),
        reason="INVALID_SIGNAL_PACKAGE_OUTCOME" if status == "failed" else "",
    )


def _validated_package_outcome(
    *,
    request: EodStrategyRequest,
    batch_key: str,
    required: tuple[DatasetReadiness, ...],
    package: SignalPackage,
    error: str,
) -> EodStrategyOutcome:
    outcome = _package_outcome(
        request=request,
        batch_key=batch_key,
        required=required,
        package=package,
    )
    if outcome.status == "failed":
        raise AppProcessError(error)
    return outcome


def _recovery_mismatch_outcome(
    *,
    request: EodStrategyRequest,
    batch_key: str,
    required: tuple[DatasetReadiness, ...],
    package: SignalPackage,
) -> EodStrategyOutcome:
    return EodStrategyOutcome(
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        batch_key=batch_key,
        status="failed",
        required_dataset_states=required,
        artifact_id=_optional_str(package.artifact_id),
        checksum=_optional_str(package.checksum),
        reason="SIGNAL_PACKAGE_RECOVERY_MISMATCH",
    )


def _recovery_failure_outcome(
    *,
    request: EodStrategyRequest,
    batch_key: str,
    required: tuple[DatasetReadiness, ...],
    package: SignalPackage | None,
    reason: str,
) -> EodStrategyOutcome:
    return EodStrategyOutcome(
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        batch_key=batch_key,
        status="failed",
        required_dataset_states=required,
        artifact_id=(
            _optional_str(package.artifact_id) if package is not None else None
        ),
        checksum=(_optional_str(package.checksum) if package is not None else None),
        reason=reason,
    )


def _validated_readiness(state: DatasetReadiness) -> DatasetReadiness:
    """Ready 必须同时携带非空权威快照标识。"""
    if state.status != "ready" or state.snapshot_id:
        return state
    return DatasetReadiness(
        dataset=state.dataset,
        status="unknown",
        snapshot_id=None,
        reason="SNAPSHOT_ID_MISSING",
    )


def _failure_outcome(
    exc: Exception,
    *,
    stage: str,
) -> tuple[str, Literal["blocked", "failed"]]:
    """把内部异常压缩为稳定、无敏感原文的机器码。"""
    if isinstance(exc, AppProcessError):
        code = exc.details.get("code")
        if code == "ACCOUNT_BASELINE_MISSING":
            return "ACCOUNT_BASELINE_MISSING", "blocked"
    if isinstance(exc, _RunLifecycleTransitionError) or stage.startswith("mark_"):
        return "RUN_LIFECYCLE_TRANSITION_FAILED", "failed"
    if stage == "create_run":
        return "RUN_LIFECYCLE_CREATE_FAILED", "failed"
    if stage == "publish_signals":
        return "SIGNAL_PACKAGE_PUBLISH_FAILED", "failed"
    if stage == "finalize_signals":
        return "SIGNAL_PACKAGE_FINALIZE_FAILED", "failed"
    return "STRATEGY_EXECUTION_FAILED", "failed"
