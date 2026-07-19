"""Unit tests for experiment control-plane domain models."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest
from ditto_analysis.errors import ExperimentIdentityError, ExperimentSpecError
from ditto_analysis.experiments import (
    AttemptId,
    AttemptRecord,
    BacktestRunId,
    CandidateId,
    CandidateRecord,
    CheckpointRef,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldRecord,
    SnapshotId,
    StrategyVersion,
)

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)

EXPERIMENT_FAILURE_POLICY_CASES = [
    (ExperimentStatus.DRAFT, None, ExperimentFailureCode.CANDIDATE_FAILED, False),
    (
        ExperimentStatus.BLOCKED,
        ExperimentFailureCode.SNAPSHOT_NOT_CERTIFIED,
        ExperimentFailureCode.CANDIDATE_FAILED,
        False,
    ),
    (ExperimentStatus.QUEUED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (ExperimentStatus.RUNNING, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (
        ExperimentStatus.PAUSE_REQUESTED,
        None,
        ExperimentFailureCode.SYSTEM_ERROR,
        False,
    ),
    (ExperimentStatus.PAUSED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (
        ExperimentStatus.CANCEL_REQUESTED,
        None,
        ExperimentFailureCode.SYSTEM_ERROR,
        False,
    ),
    (ExperimentStatus.CANCELLED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (ExperimentStatus.COMPLETED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (
        ExperimentStatus.COMPLETED_WITH_FAILURES,
        ExperimentFailureCode.CANDIDATE_FAILED,
        ExperimentFailureCode.SYSTEM_ERROR,
        True,
    ),
    (
        ExperimentStatus.FAILED,
        ExperimentFailureCode.SYSTEM_ERROR,
        ExperimentFailureCode.SNAPSHOT_NOT_CERTIFIED,
        True,
    ),
]

ATTEMPT_FAILURE_POLICY_CASES = [
    (ExperimentStatus.QUEUED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (ExperimentStatus.RUNNING, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (ExperimentStatus.CANCELLED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (ExperimentStatus.COMPLETED, None, ExperimentFailureCode.SYSTEM_ERROR, False),
    (
        ExperimentStatus.FAILED,
        ExperimentFailureCode.CANDIDATE_FAILED,
        ExperimentFailureCode.SNAPSHOT_NOT_CERTIFIED,
        True,
    ),
]


@pytest.mark.parametrize(
    "identity_type",
    [ExperimentId, CandidateId, FoldId, AttemptId, SnapshotId, StrategyVersion],
)
@pytest.mark.parametrize("value", ["", " ", "\t"])
def test_opaque_identity_rejects_empty_values(
    identity_type: Callable[[str], object], value: str
) -> None:
    with pytest.raises(ExperimentIdentityError) as exc_info:
        identity_type(value)

    assert exc_info.value.details["reason_code"] == "invalid_experiment_identity"


def test_distinct_identity_types_do_not_compare_equal() -> None:
    assert ExperimentId("same") != CandidateId("same")


def test_opaque_identity_values_have_no_instance_dictionary() -> None:
    assert not hasattr(ExperimentId("exp-1"), "__dict__")


def test_experiment_record_is_immutable_and_separates_desired_from_observed() -> None:
    record = ExperimentRecord(
        experiment_id=ExperimentId("exp-1"),
        status=ExperimentStatus.DRAFT,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.PREFLIGHT,
        created_at=NOW,
    )

    with pytest.raises(FrozenInstanceError):
        _set_attribute(record, "status", ExperimentStatus.QUEUED)

    assert record.status.value == "draft"
    assert record.desired_state.value == "run"


def test_candidate_fold_and_attempt_preserve_parent_identity_and_ordinals() -> None:
    experiment_id = ExperimentId("exp-1")
    candidate_id = CandidateId("candidate-1")
    fold_id = FoldId("fold-1")
    attempt_id = AttemptId("attempt-2")

    candidate = CandidateRecord(
        candidate_id,
        experiment_id,
        ordinal=1,
        is_baseline=True,
    )
    fold = FoldRecord(fold_id, experiment_id, candidate_id, ordinal=1)
    attempt = AttemptRecord(
        attempt_id=attempt_id,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
        ordinal=2,
        status=ExperimentStatus.QUEUED,
        created_at=NOW,
        parent_attempt_id=AttemptId("attempt-1"),
        resume_from_run_id=BacktestRunId("run-1"),
        checkpoint_ref=CheckpointRef("checkpoint-1"),
    )

    assert candidate.ordinal == fold.ordinal == 1
    assert attempt.ordinal == 2
    assert attempt.parent_attempt_id == AttemptId("attempt-1")
    assert attempt.resume_from_run_id == BacktestRunId("run-1")


def test_retry_cannot_overwrite_parent_identity_or_ordinal() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        AttemptRecord(
            attempt_id=AttemptId("attempt-1"),
            experiment_id=ExperimentId("exp-1"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            ordinal=1,
            status=ExperimentStatus.QUEUED,
            created_at=NOW,
            parent_attempt_id=AttemptId("attempt-1"),
        )

    assert exc_info.value.details["reason_code"] == "invalid_attempt_lineage"


def test_failure_code_is_stable_and_only_present_for_failure_outcomes() -> None:
    record = ExperimentRecord(
        experiment_id=ExperimentId("exp-failed"),
        status=ExperimentStatus.FAILED,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.WALK_FORWARD,
        created_at=NOW,
        failure_code=ExperimentFailureCode.SYSTEM_ERROR,
    )

    assert record.failure_code.value == "system_error"


def test_preflight_blocker_failure_codes_are_stable() -> None:
    assert (
        ExperimentFailureCode("snapshot_not_certified").value
        == "snapshot_not_certified"
    )
    assert ExperimentFailureCode("insufficient_history").value == "insufficient_history"


def test_blocked_experiment_rejects_candidate_failure_code() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ExperimentRecord(
            experiment_id=ExperimentId("exp-blocked"),
            status=ExperimentStatus.BLOCKED,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=NOW,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        )

    assert exc_info.value.details["reason_code"] == (
        "failure_code_not_allowed_for_status"
    )


@pytest.mark.parametrize(
    ("status", "allowed_code", "wrong_code", "code_required"),
    EXPERIMENT_FAILURE_POLICY_CASES,
)
def test_experiment_failure_code_policy_is_total_by_status(
    status: ExperimentStatus,
    allowed_code: ExperimentFailureCode | None,
    wrong_code: ExperimentFailureCode,
    code_required: bool,
) -> None:
    assert _experiment(status=status, failure_code=allowed_code).status is status

    with pytest.raises(ExperimentSpecError) as wrong_code_exc:
        _experiment(status=status, failure_code=wrong_code)
    expected_reason = (
        "failure_code_without_failure_outcome"
        if allowed_code is None
        else "failure_code_not_allowed_for_status"
    )
    assert wrong_code_exc.value.details["reason_code"] == expected_reason

    if code_required:
        with pytest.raises(ExperimentSpecError) as missing_code_exc:
            _experiment(status=status)
        assert missing_code_exc.value.details["reason_code"] == (
            "failure_code_required"
        )
    else:
        assert _experiment(status=status).failure_code is None


@pytest.mark.parametrize(
    ("status", "allowed_code", "wrong_code", "code_required"),
    ATTEMPT_FAILURE_POLICY_CASES,
)
def test_attempt_failure_code_policy_is_total_for_allowed_statuses(
    status: ExperimentStatus,
    allowed_code: ExperimentFailureCode | None,
    wrong_code: ExperimentFailureCode,
    code_required: bool,
) -> None:
    assert _attempt(status=status, failure_code=allowed_code).status is status

    with pytest.raises(ExperimentSpecError) as wrong_code_exc:
        _attempt(status=status, failure_code=wrong_code)
    expected_reason = (
        "failure_code_without_failure_outcome"
        if allowed_code is None
        else "failure_code_not_allowed_for_status"
    )
    assert wrong_code_exc.value.details["reason_code"] == expected_reason

    if code_required:
        with pytest.raises(ExperimentSpecError) as missing_code_exc:
            _attempt(status=status)
        assert missing_code_exc.value.details["reason_code"] == (
            "failure_code_required"
        )
    else:
        assert _attempt(status=status).failure_code is None


def test_failed_records_require_a_stable_failure_code() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ExperimentRecord(
            experiment_id=ExperimentId("exp-failed"),
            status=ExperimentStatus.FAILED,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.WALK_FORWARD,
            created_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "failure_code_required"


def test_failed_attempt_requires_a_stable_failure_code() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        AttemptRecord(
            attempt_id=AttemptId("attempt-1"),
            experiment_id=ExperimentId("exp-failed"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            ordinal=1,
            status=ExperimentStatus.FAILED,
            created_at=NOW,
        )

    assert exc_info.value.details["reason_code"] == "failure_code_required"


def test_non_failed_attempt_rejects_failure_code() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        AttemptRecord(
            attempt_id=AttemptId("attempt-1"),
            experiment_id=ExperimentId("exp-running"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            ordinal=1,
            status=ExperimentStatus.RUNNING,
            created_at=NOW,
            failure_code=ExperimentFailureCode.SYSTEM_ERROR,
        )

    assert exc_info.value.details["reason_code"] == (
        "failure_code_without_failure_outcome"
    )


@pytest.mark.parametrize("status", list(ExperimentStatus))
def test_attempt_statuses_use_an_explicit_minimal_allowlist(
    status: ExperimentStatus,
) -> None:
    allowed = {
        ExperimentStatus.QUEUED,
        ExperimentStatus.RUNNING,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.CANCELLED,
    }
    failure_code = (
        ExperimentFailureCode.SYSTEM_ERROR
        if status is ExperimentStatus.FAILED
        else None
    )

    if status in allowed:
        assert _attempt(status=status, failure_code=failure_code).status is status
        return

    with pytest.raises(ExperimentSpecError) as exc_info:
        _attempt(status=status, failure_code=failure_code)

    assert exc_info.value.details["reason_code"] == "invalid_attempt_status"


@pytest.mark.parametrize(
    "bad_time",
    [
        datetime(2026, 7, 19, 4, 0),
        datetime(2026, 7, 19, 12, 0, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_records_require_timezone_aware_utc_datetime(bad_time: datetime) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ExperimentRecord(
            experiment_id=ExperimentId("exp-1"),
            status=ExperimentStatus.DRAFT,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=bad_time,
        )

    assert exc_info.value.details["reason_code"] == "datetime_not_utc"


def _set_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _attempt(
    *,
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None = None,
) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=AttemptId("attempt-1"),
        experiment_id=ExperimentId("exp-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        ordinal=1,
        status=status,
        created_at=NOW,
        failure_code=failure_code,
    )


def _experiment(
    *,
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None = None,
) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=ExperimentId("exp-1"),
        status=status,
        desired_state=ExperimentDesiredState.RUN,
        stage=ExperimentStage.PREFLIGHT,
        created_at=NOW,
        failure_code=failure_code,
    )
