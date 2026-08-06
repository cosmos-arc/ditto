"""Durable launch orchestration extracted from read-only preflight planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol, cast

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import MutationIdempotency
from ditto_application.processes.experiments._launch_contracts import (
    DurableLaunchReplay,
    PreparedExperimentLaunch,
)
from ditto_application.processes.experiments._launch_idempotency import (
    bind_prepared_launch_idempotency,
    try_replay_idempotent_launch,
)
from ditto_application.processes.experiments._launch_saga import (
    persist_prepared_launch,
    try_replay_durable_launch,
)
from ditto_application.processes.experiments._planning_request_identity import (
    planning_request_hash,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    ExperimentPreflightCheck,
    PreflightOutcome,
)


class PreparedReport(Protocol):
    """Report fields required by the mutation path."""

    @property
    def plan_hash(self) -> str | None: ...

    @property
    def checks(self) -> tuple[ExperimentPreflightCheck, ...]: ...

    @property
    def candidate_count(self) -> int: ...

    @property
    def planned_fold_count(self) -> int: ...


class PreparedPlan(Protocol):
    """Prepared preflight output required by the mutation path."""

    @property
    def report(self) -> PreparedReport: ...

    @property
    def launch(self) -> PreparedExperimentLaunch | None: ...


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


def execute_planning_launch(
    *,
    reader: ExperimentReaderProtocol,
    writer: ExperimentWriterProtocol,
    request: ExperimentPlanningRequest,
    confirmed_plan_hash: str,
    idempotency: MutationIdempotency | None,
    validate_request: Callable[[ExperimentPlanningRequest], None],
    prepare: Callable[[ExperimentPlanningRequest], PreparedPlan],
) -> ExperimentLaunchReceipt:
    """Replay first, then prepare and atomically persist one confirmed plan."""
    validate_request(request)
    request = replace(
        request,
        dataset_requirements=tuple(
            sorted(request.dataset_requirements, key=lambda item: item.dataset_id)
        ),
    )
    idempotent = try_replay_idempotent_launch(
        reader=reader,
        experiment_id=request.experiment_id,
        identity=idempotency,
    )
    if idempotent is not None:
        return _durable_receipt(request, idempotent)
    durable = try_replay_durable_launch(
        reader=reader,
        experiment_id=request.experiment_id,
        confirmed_plan_hash=confirmed_plan_hash,
        request_hash_factory=lambda: planning_request_hash(request),
        idempotency=idempotency,
    )
    if durable is not None:
        return _durable_receipt(request, durable)
    prepared = prepare(request)
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
        launch = (
            prepared.launch
            if idempotency is None
            else bind_prepared_launch_idempotency(prepared.launch, idempotency)
        )
        projection = persist_prepared_launch(
            reader=reader,
            writer=writer,
            prepared=launch,
        )
    except AnalysisError as exc:
        replay = try_replay_idempotent_launch(
            reader=reader,
            experiment_id=request.experiment_id,
            identity=idempotency,
        )
        if replay is not None:
            return _durable_receipt(request, replay)
        try_replay_durable_launch(
            reader=reader,
            experiment_id=request.experiment_id,
            confirmed_plan_hash=confirmed_plan_hash,
            request_hash_factory=lambda: planning_request_hash(request),
            idempotency=idempotency,
        )
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


__all__ = ["ExperimentLaunchReceipt", "execute_planning_launch"]
