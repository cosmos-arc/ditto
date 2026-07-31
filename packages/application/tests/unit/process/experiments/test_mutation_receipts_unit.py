"""Exact durable cross-links for experiment control receipts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from ditto_analysis.experiments import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStage,
    ExperimentStatus,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
    canonical_resource_id,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments._mutation_receipts import (
    OperatorControlRequestContext,
    RetryFoldRequestContext,
    control_receipt_detail,
    find_control_receipt,
    replay_control_receipt,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

NOW = datetime(2026, 7, 31, 8, 0, tzinfo=UTC)


def _identity(operation_id: str):
    return build_mutation_idempotency(
        operation_id=operation_id,
        resource_id=canonical_resource_id(
            "experiment",
            {"experiment_id": "experiment-1"},
        ),
        raw_key="control-unit-001",
        request_payload={"expected_revision": 1},
    )


def _pause_event() -> tuple[StatusEventRecord, MutationIdempotency]:
    identity = _identity("research_pause_experiment")
    receipt = ExperimentControlReceipt(
        experiment_id="experiment-1",
        status="pause_requested",
        desired_state="pause",
        revision=2,
        occurred_at=NOW,
    )
    detail = control_receipt_detail(
        identity,
        receipt,
        request_context=OperatorControlRequestContext(expected_revision=1),
    )
    return (
        StatusEventRecord(
            event_id="experiment:experiment-1:2",
            experiment_id=ExperimentId("experiment-1"),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            subject_type=StatusSubjectType.EXPERIMENT,
            subject_revision=2,
            previous_status=ExperimentStatus.RUNNING,
            status=ExperimentStatus.PAUSE_REQUESTED,
            desired_state=ExperimentDesiredState.PAUSE,
            stage=ExperimentStage.EXPLORATION,
            failure_code=None,
            reason_code="operator_pause",
            detail=detail,
            detail_hash=canonical_payload(detail).content_hash,
            occurred_at=NOW,
        ),
        identity,
    )


@pytest.mark.parametrize(
    (
        "operation_id",
        "previous_status",
        "status",
        "desired_state",
        "reason_code",
    ),
    [
        (
            "research_pause_experiment",
            ExperimentStatus.QUEUED,
            ExperimentStatus.PAUSE_REQUESTED,
            ExperimentDesiredState.PAUSE,
            "operator_pause",
        ),
        (
            "research_cancel_experiment",
            ExperimentStatus.COMPLETED,
            ExperimentStatus.CANCEL_REQUESTED,
            ExperimentDesiredState.CANCEL,
            "operator_cancel",
        ),
        (
            "research_resume_experiment",
            ExperimentStatus.RUNNING,
            ExperimentStatus.QUEUED,
            ExperimentDesiredState.RUN,
            "operator_resume",
        ),
    ],
)
def test_control_receipt_rejects_illegal_predecessor(
    operation_id: str,
    previous_status: ExperimentStatus,
    status: ExperimentStatus,
    desired_state: ExperimentDesiredState,
    reason_code: str,
) -> None:
    identity = _identity(operation_id)
    receipt = ExperimentControlReceipt(
        experiment_id="experiment-1",
        status=status.value,
        desired_state=desired_state.value,
        revision=2,
        occurred_at=NOW,
    )
    detail = control_receipt_detail(
        identity,
        receipt,
        request_context=OperatorControlRequestContext(expected_revision=1),
    )
    event = StatusEventRecord(
        event_id="experiment:experiment-1:2",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        subject_type=StatusSubjectType.EXPERIMENT,
        subject_revision=2,
        previous_status=previous_status,
        status=status,
        desired_state=desired_state,
        stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        reason_code=reason_code,
        detail=detail,
        detail_hash=canonical_payload(detail).content_hash,
        occurred_at=NOW,
    )

    with pytest.raises(AppProcessError) as exc_info:
        find_control_receipt(
            (event,),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"


def test_control_receipt_rejects_detail_hash_drift() -> None:
    event, identity = _pause_event()
    drifted = replace(
        event,
        detail_hash=canonical_payload({"drifted": True}).content_hash,
    )

    with pytest.raises(AppProcessError) as exc_info:
        find_control_receipt(
            (drifted,),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"


def test_control_receipt_recomputes_request_hash_from_durable_context() -> None:
    event, identity = _pause_event()
    detail = dict(event.detail)
    context = dict(cast("dict[str, object]", detail["experiment_control_request"]))
    context["request"] = {"expected_revision": 2}
    detail["experiment_control_request"] = context
    drifted = replace(
        event,
        subject_revision=3,
        detail=detail,
        detail_hash=canonical_payload(detail).content_hash,
    )

    with pytest.raises(AppProcessError) as exc_info:
        find_control_receipt(
            (drifted,),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"


@pytest.mark.parametrize(
    "event_change",
    [
        {
            "status": ExperimentStatus.QUEUED,
            "desired_state": ExperimentDesiredState.RUN,
            "reason_code": "operator_resume",
        },
        {"reason_code": "operator_cancel"},
        {"subject_revision": 3},
        {"previous_status": ExperimentStatus.PAUSED},
    ],
)
def test_complete_pause_receipt_transplanted_to_wrong_event_fails_closed(
    event_change: dict[str, object],
) -> None:
    event, identity = _pause_event()
    wrong = replace(event, **event_change)

    with pytest.raises(AppProcessError) as exc_info:
        find_control_receipt(
            (wrong,),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details == {
        "code": "IDEMPOTENCY_RECEIPT_INVALID",
        "reason": "idempotency_receipt_invalid",
    }


def test_replay_rejects_receipt_ahead_of_durable_projection() -> None:
    event, identity = _pause_event()
    projection = SimpleNamespace(revision=1)
    store = SimpleNamespace(
        list_status_events=lambda _experiment_id: (event,),
        load_snapshot=lambda _experiment_id: SimpleNamespace(
            projection=projection,
            folds=(),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        replay_control_receipt(
            cast(ExperimentSchedulerStoreProtocol, store),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"


def test_invalid_receipt_fails_before_projection_or_mutation_side_effects() -> None:
    event, identity = _pause_event()

    class SideEffectGuardStore:
        def __init__(self) -> None:
            self.projection_reads = 0

        def list_status_events(
            self,
            _experiment_id: ExperimentId,
        ) -> tuple[StatusEventRecord, ...]:
            return (
                replace(
                    event,
                    detail_hash=canonical_payload({"drifted": True}).content_hash,
                ),
            )

        def load_snapshot(self, _experiment_id: ExperimentId) -> object:
            self.projection_reads += 1
            raise AssertionError("invalid replay must fail before projection access")

        def transition_operator_experiment(self, *_args: object, **_kwargs: object):
            raise AssertionError("invalid replay must never mutate")

        def retry_terminal_fold(self, *_args: object, **_kwargs: object):
            raise AssertionError("invalid replay must never mutate")

    store = SideEffectGuardStore()

    with pytest.raises(AppProcessError) as exc_info:
        replay_control_receipt(
            cast("ExperimentSchedulerStoreProtocol", store),
            identity,
            experiment_id="experiment-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"
    assert store.projection_reads == 0


@pytest.mark.parametrize(
    "event_change",
    [
        {"previous_status": ExperimentStatus.COMPLETED},
        {"status": ExperimentStatus.FAILED},
        {"reason_code": "fold_requeued"},
        {"subject_revision": 5},
    ],
)
def test_retry_receipt_requires_exact_fold_transition(
    event_change: dict[str, object],
) -> None:
    identity = build_mutation_idempotency(
        operation_id="research_retry_fold_experiment",
        resource_id=canonical_resource_id(
            "experiment_fold",
            {
                "experiment_id": "experiment-1",
                "candidate_id": "candidate-1",
                "fold_id": "fold-1",
            },
        ),
        raw_key="retry-unit-001",
        request_payload={
            "candidate_id": "candidate-1",
            "fold_id": "fold-1",
            "expected_revision": 3,
        },
    )
    receipt = ExperimentControlReceipt(
        experiment_id="experiment-1",
        status="running",
        desired_state="run",
        revision=5,
        occurred_at=NOW,
    )
    detail = control_receipt_detail(
        identity,
        receipt,
        request_context=RetryFoldRequestContext(
            candidate_id="candidate-1",
            fold_id="fold-1",
            expected_revision=3,
        ),
    )
    experiment_event = StatusEventRecord(
        event_id="experiment:experiment-1:5",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        subject_type=StatusSubjectType.EXPERIMENT,
        subject_revision=5,
        previous_status=ExperimentStatus.QUEUED,
        status=ExperimentStatus.RUNNING,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.EXPLORATION,
        failure_code=None,
        reason_code="scheduler_started",
        detail={},
        detail_hash=canonical_payload({}).content_hash,
        occurred_at=NOW,
    )
    fold_event = StatusEventRecord(
        event_id="fold:experiment-1:candidate-1:fold-1:4",
        experiment_id=ExperimentId("experiment-1"),
        candidate_id="candidate-1",
        fold_id="fold-1",
        attempt_id=None,
        subject_type=StatusSubjectType.FOLD,
        subject_revision=4,
        previous_status=ExperimentStatus.FAILED,
        status=ExperimentStatus.QUEUED,
        desired_state=None,
        stage=None,
        failure_code=None,
        reason_code="terminal_fold_retry",
        detail=detail,
        detail_hash=canonical_payload(detail).content_hash,
        occurred_at=NOW,
    )

    with pytest.raises(AppProcessError) as exc_info:
        find_control_receipt(
            (experiment_event, replace(fold_event, **event_change)),
            identity,
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_id="fold-1",
        )

    assert exc_info.value.details["code"] == "IDEMPOTENCY_RECEIPT_INVALID"
