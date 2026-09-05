# pyright: reportPrivateUsage=false
"""Fail-closed public-boundary tests for candidate comparison evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CandidateId,
    ContentHash,
    ExperimentFailureCode,
    ExperimentId,
    ExperimentStatus,
    FoldKey,
    FoldPersistenceSpec,
    FoldProjection,
    FoldRole,
    FoldView,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanKind,
    BaselineRef,
)
from ditto_application.processes.experiments.comparison import (
    BaselineComparisonIdentity,
    CandidateFoldEvidence,
    OOSFoldRegistration,
    PersistedFoldExecutionEvidence,
    build_candidate_comparison,
    load_persisted_fold_execution,
)
from packages.application.tests.unit.process.experiments import (
    test_comparison_unit as fixtures,
)

pytestmark = pytest.mark.pit


def _assert_rejected(action: Callable[[], object], reason: str) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        action()

    assert exc_info.value.details["reason"] == reason


def _binding(
    candidate_id: CandidateId,
    fold: OOSFoldRegistration,
    *,
    experiment_id: ExperimentId = fixtures.EXPERIMENT_ID,
    attempt_id: AttemptId | None = None,
    run_id: BacktestRunId | None = None,
    status: ExperimentStatus = ExperimentStatus.COMPLETED,
) -> PersistedFoldExecutionEvidence:
    occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    key = FoldKey(experiment_id, candidate_id, fold.fold_id)
    fold_view = FoldView(
        FoldPersistenceSpec.create(
            key,
            fold.fold_ordinal,
            FoldRole.WALK_FORWARD,
            None,
            fold.test_window,
            0,
            0,
        ),
        FoldProjection(key, status, None, occurred_at, occurred_at, 1),
    )
    selected_attempt_id = (
        AttemptId(f"attempt:{candidate_id}:{fold.fold_id}")
        if attempt_id is None
        else attempt_id
    )
    selected_run_id = (
        BacktestRunId(f"run:{candidate_id}:{fold.fold_id}")
        if run_id is None
        else run_id
    )
    attempt_view = AttemptView(
        AttemptPersistenceSpec(
            selected_attempt_id,
            key,
            1,
            None,
            None,
            ContentHash("c" * 64),
            occurred_at,
        ),
        AttemptProjection(
            selected_attempt_id,
            status,
            selected_run_id,
            None,
            (
                ExperimentFailureCode.CANDIDATE_FAILED
                if status is ExperimentStatus.FAILED
                else None
            ),
            occurred_at,
            occurred_at,
            1,
        ),
    )

    class _Reader:
        def get_fold(self, lookup: FoldKey) -> FoldView | None:
            return fold_view if lookup == key else None

        def get_attempt(self, lookup: AttemptId) -> AttemptView | None:
            return attempt_view if lookup == selected_attempt_id else None

    return load_persisted_fold_execution(
        cast("fixtures.ExperimentReaderProtocol", _Reader()),
        key,
        selected_attempt_id,
    )


def _bare_evidence(
    candidate: str,
    candidate_ordinal: int,
    fold: OOSFoldRegistration,
    *,
    experiment_id: ExperimentId = fixtures.EXPERIMENT_ID,
    attempt_id: AttemptId | None = None,
    run_id: BacktestRunId | None = None,
    status: ExperimentStatus = ExperimentStatus.COMPLETED,
    failure_reason: str | None = None,
) -> CandidateFoldEvidence:
    return CandidateFoldEvidence(
        execution_binding=_binding(
            CandidateId(candidate),
            fold,
            experiment_id=experiment_id,
            attempt_id=attempt_id,
            run_id=run_id,
            status=status,
        ),
        candidate_ordinal=candidate_ordinal,
        snapshot_id=fixtures.SNAPSHOT_ID,
        snapshot_hash=fixtures.SNAPSHOT_HASH,
        parameter_hash=ContentHash("1" * 64),
        resolved_spec_hash=ContentHash("2" * 64),
        failure_reason=failure_reason,
    )


def test_baseline_identity_rejects_untyped_nominal_identity() -> None:
    baseline = fixtures._baseline_identity()

    _assert_rejected(
        lambda: replace(baseline, **{"experiment_id": object()}),
        "invalid_baseline_identity",
    )


def test_baseline_identity_rejects_untyped_execution_plan() -> None:
    baseline = fixtures._baseline_identity()

    _assert_rejected(
        lambda: replace(baseline, **{"plan": object()}),
        "invalid_baseline_plan",
    )


def test_baseline_identity_rejects_extension_plan_kind_for_r3() -> None:
    baseline = fixtures._baseline_identity()
    extension_plan = replace(
        baseline.plan,
        kind=BaselinePlanKind.CODE_REGISTERED_EXTENSION,
    )

    _assert_rejected(
        lambda: replace(baseline, plan=extension_plan),
        "unsupported_r3_baseline_identity",
    )


def test_baseline_identity_normalizes_unknown_registry_plan() -> None:
    baseline = fixtures._baseline_identity()
    unknown_plan = replace(
        baseline.plan,
        baseline_ref=BaselineRef("unregistered-baseline", 1),
    )

    _assert_rejected(
        lambda: replace(baseline, plan=unknown_plan),
        "baseline_plan_identity_drift",
    )


def test_baseline_identity_recomputes_registered_plan_hash() -> None:
    baseline = fixtures._baseline_identity()
    object.__setattr__(baseline.plan, "canonical_hash", "0" * 64)

    _assert_rejected(
        lambda: replace(baseline),
        "baseline_plan_identity_drift",
    )


def test_baseline_identity_requires_exactly_two_typed_oos_folds() -> None:
    baseline = fixtures._baseline_identity()

    _assert_rejected(
        lambda: replace(baseline, oos_folds=baseline.oos_folds[:1]),
        "invalid_oos_fold_windows",
    )


def test_candidate_fold_rejects_untyped_snapshot_identity() -> None:
    row = fixtures._evidence("candidate-alpha", 2, 1, (100.0, 101.0))

    _assert_rejected(
        lambda: replace(row, **{"snapshot_id": "latest"}),
        "invalid_fold_evidence_identity",
    )


def test_failed_fold_requires_reason_and_projects_the_canonical_reason() -> None:
    failed = _bare_evidence(
        "candidate-alpha",
        2,
        fixtures.OOS_FOLDS[0],
        status=ExperimentStatus.FAILED,
        failure_reason="candidate_failed",
    )
    comparison = build_candidate_comparison(
        fixtures._baseline_identity(),
        (*fixtures._baseline_rows(), failed),
    )
    projected = next(
        row for row in comparison.folds if row.candidate_id == failed.candidate_id
    )
    assert projected.failure_reason == "candidate_failed"

    _assert_rejected(
        lambda: replace(failed, failure_reason=None),
        "failed_fold_reason_required",
    )


def test_completed_fold_cannot_claim_failure_reason() -> None:
    row = fixtures._evidence("candidate-alpha", 2, 1, (100.0, 101.0))

    _assert_rejected(
        lambda: replace(row, failure_reason="candidate_failed"),
        "completed_fold_cannot_have_failure_reason",
    )


def test_candidate_fold_rejects_untyped_factor_diagnostics() -> None:
    row = fixtures._evidence("candidate-alpha", 2, 1, (100.0, 101.0))

    _assert_rejected(
        lambda: replace(row, **{"factor_diagnostics": object()}),
        "invalid_factor_diagnostics",
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source", object(), "invalid_fold_comparison"),
        ("metrics", {}, "comparison_metric_schema_drift"),
        ("factor_diagnostics", {}, "factor_diagnostic_schema_drift"),
        ("return_evidence", object(), "invalid_fold_return_evidence"),
        ("execution_evidence", object(), "invalid_fold_execution_evidence"),
    ],
)
def test_fold_comparison_rejects_projection_schema_drift(
    field: str,
    value: object,
    reason: str,
) -> None:
    comparison = build_candidate_comparison(
        fixtures._baseline_identity(),
        fixtures._baseline_rows(),
    )

    _assert_rejected(
        lambda: replace(comparison.folds[0], **{field: value}),
        reason,
    )


def test_comparison_rejects_cross_experiment_evidence() -> None:
    foreign = _bare_evidence(
        "candidate-alpha",
        2,
        fixtures.OOS_FOLDS[0],
        experiment_id=ExperimentId("experiment-foreign"),
    )

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (*fixtures._baseline_rows(), foreign),
        ),
        "experiment_identity_drift",
    )


def test_comparison_rejects_duplicate_candidate_fold() -> None:
    rows = fixtures._baseline_rows()

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (*rows, rows[0]),
        ),
        "duplicate_candidate_fold_evidence",
    )


def test_comparison_rejects_candidate_ordinal_drift_across_folds() -> None:
    rows = fixtures._baseline_rows()

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (rows[0], replace(rows[1], candidate_ordinal=2)),
        ),
        "candidate_ordinal_drift",
    )


def test_comparison_rejects_candidate_spec_identity_drift_across_folds() -> None:
    rows = fixtures._baseline_rows()

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (
                rows[0],
                replace(
                    rows[1],
                    parameter_hash=ContentHash("9" * 64),
                    capacity=None,
                ),
            ),
        ),
        "candidate_spec_identity_drift",
    )


def test_comparison_rejects_candidate_reusing_baseline_ordinal() -> None:
    candidate = fixtures._evidence("candidate-alpha", 1, 1, (100.0, 101.0))

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (*fixtures._baseline_rows(), candidate),
        ),
        "duplicate_candidate_ordinal",
    )


def test_comparison_rejects_duplicate_attempt_across_distinct_folds() -> None:
    attempt_id = AttemptId("attempt:candidate-alpha:shared")
    candidate_rows = (
        _bare_evidence(
            "candidate-alpha",
            2,
            fixtures.OOS_FOLDS[0],
            attempt_id=attempt_id,
        ),
        _bare_evidence(
            "candidate-alpha",
            2,
            fixtures.OOS_FOLDS[1],
            attempt_id=attempt_id,
        ),
    )

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (*fixtures._baseline_rows(), *candidate_rows),
        ),
        "duplicate_attempt_evidence",
    )


def test_comparison_rejects_duplicate_run_across_distinct_folds() -> None:
    run_id = BacktestRunId("run:candidate-alpha:shared")
    candidate_rows = (
        _bare_evidence(
            "candidate-alpha",
            2,
            fixtures.OOS_FOLDS[0],
            run_id=run_id,
        ),
        _bare_evidence(
            "candidate-alpha",
            2,
            fixtures.OOS_FOLDS[1],
            run_id=run_id,
        ),
    )

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            (*fixtures._baseline_rows(), *candidate_rows),
        ),
        "duplicate_run_evidence",
    )


def test_comparison_requires_baseline_candidate_ordinal_one() -> None:
    rows = tuple(replace(row, candidate_ordinal=2) for row in fixtures._baseline_rows())

    _assert_rejected(
        lambda: build_candidate_comparison(fixtures._baseline_identity(), rows),
        "baseline_candidate_must_be_first",
    )


def test_comparison_requires_both_registered_baseline_folds() -> None:
    rows = fixtures._baseline_rows()

    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            rows[:1],
        ),
        "baseline_two_fold_evidence_required",
    )


def test_comparison_builder_rejects_untyped_baseline() -> None:
    _assert_rejected(
        lambda: build_candidate_comparison(
            cast("BaselineComparisonIdentity", object()),
            fixtures._baseline_rows(),
        ),
        "invalid_baseline_identity",
    )


@pytest.mark.parametrize("evidence", [{}, set(), "rows"])
def test_comparison_builder_rejects_ambiguous_evidence_containers(
    evidence: object,
) -> None:
    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            cast("object", evidence),
        ),
        "invalid_fold_evidence_sequence",
    )


def test_comparison_builder_normalizes_noniterable_evidence() -> None:
    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            cast("object", object()),
        ),
        "invalid_fold_evidence_sequence",
    )


@pytest.mark.parametrize("evidence", [(), (object(),)])
def test_comparison_builder_requires_nonempty_exact_evidence_rows(
    evidence: object,
) -> None:
    _assert_rejected(
        lambda: build_candidate_comparison(
            fixtures._baseline_identity(),
            cast("object", evidence),
        ),
        "invalid_fold_evidence_sequence",
    )
