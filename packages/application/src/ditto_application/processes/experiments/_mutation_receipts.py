"""Typed codecs for durable experiment mutation receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ditto_analysis.experiments import (
    ExperimentDesiredState,
    ExperimentId,
    ExperimentStatus,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
)

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_request_hash,
    canonical_resource_id,
    find_mutation_receipt,
    mutation_receipt_detail,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerStoreProtocol,
)

_CONTROL_OPERATIONS = frozenset(
    {
        "research_pause_experiment",
        "research_cancel_experiment",
        "research_resume_experiment",
        "research_retry_fold_experiment",
    }
)
_LIVE = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})
_CONTROL_CONTEXT_KEY = "experiment_control_request"
_CONTROL_CONTEXT_KIND = "ditto_experiment_control_request"
_CONTROL_CONTEXT_KEYS = frozenset({"schema_version", "kind", "operation_id", "request"})
_EXPERIMENT_EVENT_SEMANTICS = {
    "research_pause_experiment": (
        ExperimentStatus.PAUSE_REQUESTED,
        ExperimentDesiredState.PAUSE,
        "operator_pause",
        frozenset({ExperimentStatus.RUNNING}),
    ),
    "research_cancel_experiment": (
        ExperimentStatus.CANCEL_REQUESTED,
        ExperimentDesiredState.CANCEL,
        "operator_cancel",
        frozenset(
            {
                ExperimentStatus.QUEUED,
                ExperimentStatus.RUNNING,
                ExperimentStatus.PAUSED,
            }
        ),
    ),
    "research_resume_experiment": (
        ExperimentStatus.QUEUED,
        ExperimentDesiredState.RUN,
        "operator_resume",
        frozenset({ExperimentStatus.PAUSED}),
    ),
}


@dataclass(frozen=True, slots=True)
class OperatorControlIntent:
    """One revision-fenced experiment transition and its audit semantics."""

    expected_revision: int
    occurred_at: datetime
    target_status: ExperimentStatus
    target_desired_state: ExperimentDesiredState
    reason_code: str


@dataclass(frozen=True, slots=True)
class OperatorControlRequestContext:
    """Canonical request fields that bind one experiment-control event."""

    expected_revision: int

    def __post_init__(self) -> None:
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise _invalid_receipt()

    def request_payload(self) -> dict[str, object]:
        return {"expected_revision": self.expected_revision}


@dataclass(frozen=True, slots=True)
class RetryFoldRequestContext:
    """Canonical request fields that bind one exact fold-retry event."""

    candidate_id: str
    fold_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        if (
            type(self.candidate_id) is not str
            or not self.candidate_id
            or type(self.fold_id) is not str
            or not self.fold_id
            or type(self.expected_revision) is not int
            or self.expected_revision < 0
        ):
            raise _invalid_receipt()

    def request_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "fold_id": self.fold_id,
            "expected_revision": self.expected_revision,
        }


type ControlRequestContext = OperatorControlRequestContext | RetryFoldRequestContext


def _invalid_receipt() -> AppProcessError:
    return AppProcessError(
        "durable experiment mutation receipt is invalid",
        details={
            "code": "IDEMPOTENCY_RECEIPT_INVALID",
            "reason": "idempotency_receipt_invalid",
        },
    )


def _has_exact_string_keys(
    value: Mapping[object, object],
    expected: frozenset[str],
) -> bool:
    keys = tuple(value)
    return (
        all(type(key) is str for key in keys)
        and cast("frozenset[str]", frozenset(keys)) == expected
    )


def control_receipt_payload(receipt: ExperimentControlReceipt) -> dict[str, object]:
    """Encode the exact response fields returned at the command boundary."""
    return {
        "experiment_id": receipt.experiment_id,
        "status": receipt.status,
        "desired_state": receipt.desired_state,
        "revision": receipt.revision,
        "occurred_at": receipt.occurred_at.isoformat(),
        "live_run_ids": list(receipt.live_run_ids),
    }


def control_receipt_detail(
    identity: MutationIdempotency,
    receipt: ExperimentControlReceipt,
    *,
    request_context: ControlRequestContext,
    detail: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Embed one typed control receipt into the transition event detail."""
    is_retry = identity.operation_id == "research_retry_fold_experiment"
    if (
        identity.operation_id not in _CONTROL_OPERATIONS
        or (is_retry and type(request_context) is not RetryFoldRequestContext)
        or (not is_retry and type(request_context) is not OperatorControlRequestContext)
        or (detail is not None and _CONTROL_CONTEXT_KEY in detail)
    ):
        raise _invalid_receipt()
    request_payload = request_context.request_payload()
    if canonical_request_hash(request_payload) != identity.request_hash:
        raise _invalid_receipt()
    return mutation_receipt_detail(
        identity,
        response=control_receipt_payload(receipt),
        detail={
            **dict(detail or {}),
            _CONTROL_CONTEXT_KEY: {
                "schema_version": 1,
                "kind": _CONTROL_CONTEXT_KIND,
                "operation_id": identity.operation_id,
                "request": request_payload,
            },
        },
    )


def _decode_control_receipt(
    value: Mapping[str, object],
) -> ExperimentControlReceipt:
    live_run_ids = value.get("live_run_ids")
    run_id_values = (
        () if not isinstance(live_run_ids, list) else cast("list[object]", live_run_ids)
    )
    if (
        set(value)
        != {
            "experiment_id",
            "status",
            "desired_state",
            "revision",
            "occurred_at",
            "live_run_ids",
        }
        or type(value["experiment_id"]) is not str
        or type(value["status"]) is not str
        or type(value["desired_state"]) is not str
        or type(value["revision"]) is not int
        or type(value["occurred_at"]) is not str
        or not isinstance(live_run_ids, list)
        or any(type(item) is not str for item in run_id_values)
        or value["revision"] < 0
    ):
        raise _invalid_receipt()
    typed_run_ids = cast("list[str]", run_id_values)
    if typed_run_ids != sorted(set(typed_run_ids)):
        raise _invalid_receipt()
    try:
        occurred_at = datetime.fromisoformat(value["occurred_at"])
        ExperimentStatus(value["status"])
        ExperimentDesiredState(value["desired_state"])
    except ValueError as exc:
        raise _invalid_receipt() from exc
    if occurred_at.utcoffset() is None:
        raise _invalid_receipt()
    return ExperimentControlReceipt(
        experiment_id=value["experiment_id"],
        status=value["status"],
        desired_state=value["desired_state"],
        revision=value["revision"],
        occurred_at=occurred_at,
        live_run_ids=tuple(typed_run_ids),
        replayed=True,
    )


def _receipt_match(
    events: Sequence[StatusEventRecord],
    identity: MutationIdempotency,
) -> tuple[ExperimentControlReceipt, StatusEventRecord] | None:
    matches: list[tuple[StatusEventRecord, Mapping[str, object]]] = []
    for event in events:
        try:
            receipt = find_mutation_receipt((event.detail,), identity)
        except AppCommandError as exc:
            raise AppProcessError(str(exc), details=exc.details) from exc
        if receipt is not None:
            try:
                actual_hash = canonical_payload(event.detail).content_hash
            except (TypeError, ValueError) as exc:
                raise _invalid_receipt() from exc
            if actual_hash != event.detail_hash:
                raise _invalid_receipt()
            matches.append((event, receipt))
    if len(matches) > 1:
        raise _invalid_receipt()
    if not matches:
        return None
    event, value = matches[0]
    return _decode_control_receipt(value), event


def _decode_request_context(
    event: StatusEventRecord,
    identity: MutationIdempotency,
    *,
    is_retry: bool,
    candidate_id: str | None,
    fold_id: str | None,
) -> int:
    raw_context = event.detail.get(_CONTROL_CONTEXT_KEY)
    if not isinstance(raw_context, Mapping):
        raise _invalid_receipt()
    context = cast("Mapping[object, object]", raw_context)
    if (
        not _has_exact_string_keys(context, _CONTROL_CONTEXT_KEYS)
        or type(context["schema_version"]) is not int
        or context["schema_version"] != 1
        or context["kind"] != _CONTROL_CONTEXT_KIND
        or context["operation_id"] != identity.operation_id
        or not isinstance(context["request"], Mapping)
    ):
        raise _invalid_receipt()
    request = cast("Mapping[object, object]", context["request"])
    expected_keys = (
        frozenset({"candidate_id", "fold_id", "expected_revision"})
        if is_retry
        else frozenset({"expected_revision"})
    )
    if (
        not _has_exact_string_keys(request, expected_keys)
        or type(request["expected_revision"]) is not int
        or request["expected_revision"] < 0
        or (
            is_retry
            and (
                type(request["candidate_id"]) is not str
                or not request["candidate_id"]
                or type(request["fold_id"]) is not str
                or not request["fold_id"]
                or request["candidate_id"] != candidate_id
                or request["fold_id"] != fold_id
            )
        )
    ):
        raise _invalid_receipt()
    typed_request = cast("Mapping[str, object]", request)
    try:
        request_hash = canonical_request_hash(typed_request)
    except AppCommandError as exc:
        raise _invalid_receipt() from exc
    if request_hash != identity.request_hash:
        raise _invalid_receipt()
    return request["expected_revision"]


def _expected_resource(
    *,
    is_retry: bool,
    experiment_id: str,
    candidate_id: str | None,
    fold_id: str | None,
) -> str:
    return (
        canonical_resource_id(
            "experiment_fold",
            {
                "experiment_id": experiment_id,
                "candidate_id": candidate_id,
                "fold_id": fold_id,
            },
        )
        if is_retry
        else canonical_resource_id(
            "experiment",
            {"experiment_id": experiment_id},
        )
    )


def _validate_event_target(
    event: StatusEventRecord,
    receipt: ExperimentControlReceipt,
    identity: MutationIdempotency,
    *,
    experiment_id: str,
    candidate_id: str | None,
    fold_id: str | None,
    is_retry: bool,
) -> None:
    if (
        str(event.experiment_id) != experiment_id
        or receipt.experiment_id != experiment_id
        or identity.resource_id
        != _expected_resource(
            is_retry=is_retry,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            fold_id=fold_id,
        )
        or (
            is_retry
            and (
                event.subject_type is not StatusSubjectType.FOLD
                or event.candidate_id is None
                or event.fold_id is None
                or str(event.candidate_id) != candidate_id
                or str(event.fold_id) != fold_id
            )
        )
        or (not is_retry and event.subject_type is not StatusSubjectType.EXPERIMENT)
        or (not is_retry and event.subject_revision != receipt.revision)
        or event.occurred_at != receipt.occurred_at
    ):
        raise _invalid_receipt()


def _validate_transition_event(
    event: StatusEventRecord,
    receipt: ExperimentControlReceipt,
    *,
    operation_id: str,
    is_retry: bool,
    expected_revision: int,
) -> None:
    if is_retry:
        invalid = (
            event.subject_revision != expected_revision + 1
            or event.previous_status is not ExperimentStatus.FAILED
            or event.status is not ExperimentStatus.QUEUED
            or event.desired_state is not None
            or event.stage is not None
            or event.attempt_id is not None
            or event.failure_code is not None
            or event.reason_code != "terminal_fold_retry"
        )
    else:
        expected_status, expected_desired, expected_reason, legal_predecessors = (
            _EXPERIMENT_EVENT_SEMANTICS[operation_id]
        )
        invalid = (
            event.subject_revision != expected_revision + 1
            or event.candidate_id is not None
            or event.fold_id is not None
            or event.attempt_id is not None
            or event.previous_status not in legal_predecessors
            or event.status is not expected_status
            or event.desired_state is not expected_desired
            or event.stage is None
            or event.failure_code is not None
            or event.reason_code != expected_reason
            or receipt.status != event.status.value
            or receipt.desired_state != expected_desired.value
        )
    if invalid:
        raise _invalid_receipt()


def _validate_receipt_projection_event(
    events: Sequence[StatusEventRecord],
    receipt: ExperimentControlReceipt,
) -> None:
    experiment_events = tuple(
        item
        for item in events
        if item.subject_type is StatusSubjectType.EXPERIMENT
        and item.subject_revision == receipt.revision
    )
    if (
        len(experiment_events) != 1
        or experiment_events[0].status.value != receipt.status
        or experiment_events[0].desired_state is None
        or experiment_events[0].desired_state.value != receipt.desired_state
    ):
        raise _invalid_receipt()


def _find_control_receipt_event(
    events: Sequence[StatusEventRecord],
    identity: MutationIdempotency,
    *,
    experiment_id: str,
    candidate_id: str | None = None,
    fold_id: str | None = None,
) -> tuple[ExperimentControlReceipt, StatusEventRecord] | None:
    if identity.operation_id not in _CONTROL_OPERATIONS:
        raise _invalid_receipt()
    match = _receipt_match(events, identity)
    if match is None:
        return None
    receipt, event = match
    is_retry = identity.operation_id == "research_retry_fold_experiment"
    expected_revision = _decode_request_context(
        event,
        identity,
        is_retry=is_retry,
        candidate_id=candidate_id,
        fold_id=fold_id,
    )
    _validate_event_target(
        event,
        receipt,
        identity,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
        is_retry=is_retry,
    )
    _validate_transition_event(
        event,
        receipt,
        operation_id=identity.operation_id,
        is_retry=is_retry,
        expected_revision=expected_revision,
    )
    _validate_receipt_projection_event(events, receipt)
    return receipt, event


def find_control_receipt(
    events: Sequence[StatusEventRecord],
    identity: MutationIdempotency,
    *,
    experiment_id: str,
    candidate_id: str | None = None,
    fold_id: str | None = None,
) -> ExperimentControlReceipt | None:
    """Find and validate one control receipt against exact event semantics."""
    match = _find_control_receipt_event(
        events,
        identity,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
    )
    return None if match is None else match[0]


def experiment_status_events(
    events: Sequence[StatusEventRecord],
    experiment_id: str,
) -> tuple[StatusEventRecord, ...]:
    """Validate the reader did not return cross-experiment event rows."""
    expected = ExperimentId(experiment_id)
    if any(event.experiment_id != expected for event in events):
        raise _invalid_receipt()
    return tuple(events)


def replay_control_receipt(
    store: ExperimentSchedulerStoreProtocol,
    identity: MutationIdempotency | None,
    *,
    experiment_id: str,
    candidate_id: str | None = None,
    fold_id: str | None = None,
) -> ExperimentControlReceipt | None:
    """Replay before projection, lease, provider, or notifier access."""
    if identity is None:
        return None
    events = experiment_status_events(
        store.list_status_events(ExperimentId(experiment_id)),
        experiment_id,
    )
    match = _find_control_receipt_event(
        events,
        identity,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
    )
    if match is None:
        return None
    receipt, event = match
    snapshot = store.load_snapshot(ExperimentId(experiment_id))
    if snapshot.projection.revision < receipt.revision:
        raise _invalid_receipt()
    if event.subject_type is StatusSubjectType.FOLD:
        folds = tuple(
            fold
            for fold in snapshot.folds
            if str(fold.spec.key.candidate_id) == candidate_id
            and str(fold.spec.key.fold_id) == fold_id
        )
        if len(folds) != 1 or folds[0].projection.revision < event.subject_revision:
            raise _invalid_receipt()
    return receipt


def persist_operator_control(
    store: ExperimentSchedulerStoreProtocol,
    identity: MutationIdempotency | None,
    *,
    experiment_id: str,
    intent: OperatorControlIntent,
) -> ExperimentControlReceipt:
    """Commit or race-replay one atomic experiment projection/status event."""
    replay = replay_control_receipt(
        store,
        identity,
        experiment_id=experiment_id,
    )
    if replay is not None:
        return replay
    snapshot = store.load_snapshot(ExperimentId(experiment_id))
    live_run_ids = tuple(
        sorted(
            {
                str(item.projection.backtest_run_id)
                for item in snapshot.attempts
                if item.projection.status in _LIVE
                and item.projection.backtest_run_id is not None
            }
        )
    )
    expected_receipt = ExperimentControlReceipt(
        experiment_id=experiment_id,
        status=intent.target_status.value,
        desired_state=intent.target_desired_state.value,
        revision=intent.expected_revision + 1,
        occurred_at=intent.occurred_at,
        live_run_ids=live_run_ids,
    )
    detail = (
        {}
        if identity is None
        else control_receipt_detail(
            identity,
            expected_receipt,
            request_context=OperatorControlRequestContext(intent.expected_revision),
        )
    )
    try:
        projection = store.transition_operator_experiment(
            snapshot.projection,
            target_status=intent.target_status,
            target_desired_state=intent.target_desired_state,
            expected_revision=intent.expected_revision,
            occurred_at=intent.occurred_at,
            reason_code=intent.reason_code,
            detail=detail,
        )
    except Exception:
        replay = replay_control_receipt(
            store,
            identity,
            experiment_id=experiment_id,
        )
        if replay is not None:
            return replay
        raise
    record = projection.record
    result = ExperimentControlReceipt(
        experiment_id=str(record.experiment_id),
        status=record.status.value,
        desired_state=record.desired_state.value,
        revision=projection.revision,
        occurred_at=intent.occurred_at,
        live_run_ids=live_run_ids,
    )
    if identity is not None and result != expected_receipt:
        raise _invalid_receipt()
    return result


__all__ = [
    "OperatorControlIntent",
    "OperatorControlRequestContext",
    "RetryFoldRequestContext",
    "control_receipt_detail",
    "control_receipt_payload",
    "experiment_status_events",
    "find_control_receipt",
    "persist_operator_control",
    "replay_control_receipt",
]
