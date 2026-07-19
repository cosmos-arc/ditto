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


@pytest.mark.parametrize(
    "status",
    [ExperimentStatus.DRAFT, ExperimentStatus.BLOCKED],
)
def test_attempt_rejects_pre_attempt_experiment_statuses(
    status: ExperimentStatus,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        AttemptRecord(
            attempt_id=AttemptId("attempt-1"),
            experiment_id=ExperimentId("exp-1"),
            candidate_id=CandidateId("candidate-1"),
            fold_id=FoldId("fold-1"),
            ordinal=1,
            status=status,
            created_at=NOW,
        )

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
