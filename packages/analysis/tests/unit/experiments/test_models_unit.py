"""Unit tests for experiment control-plane domain models."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from ditto_analysis.errors import ExperimentIdentityError, ExperimentSpecError
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    CandidateSpec,
    CheckpointRef,
    ContentHash,
    DateWindow,
    ExperimentDesiredState,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
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

    candidate = CandidateSpec(
        candidate_id=candidate_id,
        ordinal=1,
        is_baseline=True,
        parameters={"lookback": 20},
    )
    fold_key = FoldKey(experiment_id, candidate_id, fold_id)
    fold_spec = FoldPersistenceSpec.create(
        key=fold_key,
        ordinal=1,
        fold_role=FoldRole.WALK_FORWARD,
        train_window=DateWindow(date(2024, 1, 2), date(2025, 12, 31)),
        test_window=DateWindow(date(2026, 1, 5), date(2026, 3, 31)),
        purge_sessions=2,
        embargo_sessions=1,
    )
    fold = FoldView(
        spec=fold_spec,
        projection=FoldProjection(
            key=fold_key,
            status=ExperimentStatus.QUEUED,
            claim_owner_token=None,
            created_at=NOW,
            updated_at=NOW,
            revision=0,
        ),
    )
    attempt_spec = AttemptPersistenceSpec(
        attempt_id=attempt_id,
        fold_key=fold_key,
        ordinal=2,
        parent_attempt_id=AttemptId("attempt-1"),
        resume_from_run_id=BacktestRunId("run-1"),
        reproduction_fingerprint=ContentHash("a" * 64),
        created_at=NOW,
    )
    attempt = AttemptView(
        spec=attempt_spec,
        projection=AttemptProjection(
            attempt_id=attempt_id,
            status=ExperimentStatus.QUEUED,
            backtest_run_id=None,
            checkpoint_ref=CheckpointRef("checkpoint-1"),
            failure_code=None,
            created_at=NOW,
            updated_at=NOW,
            revision=0,
        ),
    )

    assert candidate.ordinal == fold.spec.ordinal == 1
    assert fold.spec.key == fold.projection.key == fold_key
    assert attempt.spec.ordinal == 2
    assert attempt.spec.fold_key == fold_key
    assert attempt.spec.parent_attempt_id == AttemptId("attempt-1")
    assert attempt.spec.resume_from_run_id == BacktestRunId("run-1")
    assert attempt.projection.checkpoint_ref == CheckpointRef("checkpoint-1")


def test_attempt_view_separates_immutable_lineage_from_execution_projection() -> None:
    attempt = _attempt(
        status=ExperimentStatus.RUNNING,
        ordinal=2,
        parent_attempt_id=AttemptId("attempt-1"),
    )

    assert attempt.spec.parent_attempt_id == AttemptId("attempt-1")
    assert attempt.spec.ordinal == 2
    assert attempt.projection.status is ExperimentStatus.RUNNING
    assert not hasattr(attempt.projection, "parent_attempt_id")


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


def test_attempt_projection_preserves_a_stable_failure_outcome() -> None:
    attempt = _attempt(
        status=ExperimentStatus.FAILED,
        failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
    )

    assert attempt.projection.status is ExperimentStatus.FAILED
    assert attempt.projection.failure_code is ExperimentFailureCode.CANDIDATE_FAILED


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
    ordinal: int = 1,
    parent_attempt_id: AttemptId | None = None,
) -> AttemptView:
    attempt_id = AttemptId(f"attempt-{ordinal}")
    return AttemptView(
        spec=AttemptPersistenceSpec(
            attempt_id=attempt_id,
            fold_key=FoldKey(
                ExperimentId("exp-1"),
                CandidateId("candidate-1"),
                FoldId("fold-1"),
            ),
            ordinal=ordinal,
            parent_attempt_id=parent_attempt_id,
            resume_from_run_id=None,
            reproduction_fingerprint=ContentHash("a" * 64),
            created_at=NOW,
        ),
        projection=AttemptProjection(
            attempt_id=attempt_id,
            status=status,
            backtest_run_id=None,
            checkpoint_ref=None,
            failure_code=failure_code,
            created_at=NOW,
            updated_at=NOW,
            revision=0,
        ),
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
