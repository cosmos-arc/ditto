# pyright: reportPrivateUsage=false
"""Fail-closed boundary tests for persisted walk-forward evidence collection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    ExperimentFailureCode,
    ExperimentStatus,
    FoldKey,
    FoldPersistenceSpec,
    FoldRole,
    FoldView,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    SnapshotManifestProjection,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)
from packages.application.tests.unit.process.experiments import (
    walk_forward_evidence_collection_fixtures as fixtures,
)

pytestmark = pytest.mark.pit


def _assert_rejected(action: Callable[[], object], reason: str) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        action()

    assert exc_info.value.details["reason"] == reason


def _assembler(case: fixtures.EvidenceCase) -> WalkForwardEvidenceAssembler:
    return WalkForwardEvidenceAssembler(
        report_reader=case.adapter,
        fold_selection_trace_reader=case.trace_adapter,
        semantics_resolver=fixtures.Resolver(case.semantics),
    )


def _assemble_snapshot(
    case: fixtures.EvidenceCase,
    snapshot: ExperimentSchedulerSnapshot,
    manifest: SnapshotManifestProjection | None = None,
) -> object:
    return _assembler(case).assemble(
        snapshot,
        fixtures.snapshot_manifest() if manifest is None else manifest,
    )


def _replace_fold(
    values: tuple[FoldView, ...],
    index: int,
    replacement: FoldView,
) -> tuple[FoldView, ...]:
    return (*values[:index], replacement, *values[index + 1 :])


def _replace_attempt(
    values: tuple[AttemptView, ...],
    index: int,
    replacement: AttemptView,
) -> tuple[AttemptView, ...]:
    return (*values[:index], replacement, *values[index + 1 :])


def test_collected_evidence_rejects_non_tuple_selection_traces(
    tmp_path: Path,
) -> None:
    collected = fixtures.build_case(tmp_path).assemble()

    _assert_rejected(
        lambda: replace(collected, **{"selection_traces": []}),
        "invalid_fold_selection_trace_artifacts",
    )


def test_collected_evidence_rejects_duplicate_selection_trace_identity(
    tmp_path: Path,
) -> None:
    collected = fixtures.build_case(tmp_path).assemble()
    duplicated = (*collected.selection_traces, collected.selection_traces[0])

    _assert_rejected(
        lambda: replace(collected, selection_traces=duplicated),
        "duplicate_fold_selection_trace_artifacts",
    )


def test_collected_evidence_rejects_reordered_selection_traces(
    tmp_path: Path,
) -> None:
    collected = fixtures.build_case(tmp_path).assemble()

    _assert_rejected(
        lambda: replace(
            collected,
            selection_traces=tuple(reversed(collected.selection_traces)),
        ),
        "noncanonical_fold_selection_trace_artifacts",
    )


def test_collected_evidence_rejects_non_tuple_source_rows(tmp_path: Path) -> None:
    collected = fixtures.build_case(tmp_path).assemble()

    _assert_rejected(
        lambda: replace(collected, **{"source_rows": list(collected.source_rows)}),
        "invalid_collected_walk_forward_evidence",
    )


def test_collected_evidence_rejects_reordered_source_rows(tmp_path: Path) -> None:
    collected = fixtures.build_case(tmp_path).assemble()

    _assert_rejected(
        lambda: replace(
            collected,
            source_rows=tuple(reversed(collected.source_rows)),
        ),
        "noncanonical_collected_source_rows",
    )


def test_collected_evidence_rejects_non_tuple_missing_refs(tmp_path: Path) -> None:
    collected = fixtures.build_case(tmp_path).assemble()

    _assert_rejected(
        lambda: replace(collected, **{"missing_artifact_refs": []}),
        "invalid_missing_artifact_refs",
    )


def test_collected_evidence_rejects_noncanonical_missing_ref_order(
    tmp_path: Path,
) -> None:
    collected = fixtures.build_case(
        tmp_path,
        publish_indices=(0, 1, 3),
    ).assemble()
    assert len(collected.missing_artifact_refs) > 1

    _assert_rejected(
        lambda: replace(
            collected,
            missing_artifact_refs=tuple(reversed(collected.missing_artifact_refs)),
        ),
        "noncanonical_missing_artifact_refs",
    )


def test_assembler_rejects_mutable_snapshot_collections(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    snapshot = case.snapshot()
    object.__setattr__(snapshot, "folds", list(snapshot.folds))

    _assert_rejected(
        lambda: _assemble_snapshot(case, snapshot),
        "invalid_scheduler_snapshot",
    )


def test_assembler_rejects_untyped_fold_before_attribute_access(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    snapshot = case.snapshot()
    object.__setattr__(snapshot, "folds", (object(),))

    _assert_rejected(
        lambda: _assemble_snapshot(case, snapshot),
        "invalid_walk_forward_fold",
    )


def test_assembler_normalizes_snapshot_constructor_type_errors(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    snapshot = case.snapshot()
    object.__setattr__(snapshot.folds[0].spec, "key", [])

    _assert_rejected(
        lambda: _assemble_snapshot(case, snapshot),
        "invalid_scheduler_snapshot",
    )


class _ForgedFoldKey(FoldKey):
    """Subtype-shaped provider corruption rejected by exact identity checks."""


def test_assembler_rejects_fold_key_subtype_smuggling(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    original_fold = case.folds[0]
    original_key = original_fold.spec.key
    forged_key = _ForgedFoldKey(
        original_key.experiment_id,
        original_key.candidate_id,
        original_key.fold_id,
    )
    forged_fold = replace(
        original_fold,
        spec=replace(original_fold.spec, key=forged_key),
        projection=replace(original_fold.projection, key=forged_key),
    )
    original_attempt = case.attempts[0]
    forged_attempt = replace(
        original_attempt,
        spec=replace(original_attempt.spec, fold_key=forged_key),
    )
    snapshot = case.snapshot(
        folds=_replace_fold(case.folds, 0, forged_fold),
        attempts=_replace_attempt(case.attempts, 0, forged_attempt),
    )

    _assert_rejected(
        lambda: _assemble_snapshot(case, snapshot),
        "walk_forward_fold_lineage_drift",
    )


def test_assembler_recomputes_persisted_fold_spec_identity(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    fold = case.folds[0]
    drifted = replace(
        fold,
        spec=replace(fold.spec, canonical_payload=b"{}"),
    )

    _assert_rejected(
        lambda: case.assemble(folds=_replace_fold(case.folds, 0, drifted)),
        "persisted_fold_spec_drift",
    )


def test_assembler_requires_exactly_two_baseline_walk_forward_folds(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())

    _assert_rejected(
        lambda: case.assemble(
            folds=case.folds[1:],
            attempts=case.attempts[1:],
        ),
        "baseline_two_walk_forward_folds_required",
    )


def _fold_with_role(fold: FoldView, role: FoldRole) -> FoldView:
    spec = fold.spec
    rebuilt = FoldPersistenceSpec.create(
        spec.key,
        spec.ordinal,
        role,
        spec.train_window,
        spec.test_window,
        spec.purge_sessions,
        spec.embargo_sessions,
    )
    return replace(fold, spec=rebuilt)


def test_assembler_rejects_snapshot_without_walk_forward_evidence(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    exploration = tuple(
        _fold_with_role(fold, FoldRole.EXPLORATION) for fold in case.folds
    )

    _assert_rejected(
        lambda: case.assemble(folds=exploration),
        "walk_forward_evidence_missing",
    )


def test_assembler_rejects_nonterminal_walk_forward_fold(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    fold = case.folds[2]
    running = replace(
        fold,
        projection=replace(fold.projection, status=ExperimentStatus.RUNNING),
    )

    _assert_rejected(
        lambda: case.assemble(folds=_replace_fold(case.folds, 2, running)),
        "walk_forward_fold_not_terminal",
    )


def test_assembler_rejects_non_utc_attempt_evidence(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    attempt = case.attempts[2]
    naive_created_at = attempt.spec.created_at.replace(tzinfo=None)
    drifted = replace(
        attempt,
        spec=replace(attempt.spec, created_at=naive_created_at),
        projection=replace(attempt.projection, created_at=naive_created_at),
    )

    _assert_rejected(
        lambda: case.assemble(
            attempts=_replace_attempt(case.attempts, 2, drifted),
        ),
        "attempt_identity_drift",
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"status": ExperimentStatus.QUEUED},
            "queued_attempt_projection_invalid",
        ),
        (
            {"failure_code": ExperimentFailureCode.CANDIDATE_FAILED},
            "completed_attempt_failure_code_drift",
        ),
        (
            {"status": ExperimentStatus.FAILED},
            "failed_attempt_failure_code_missing",
        ),
        (
            {
                "status": ExperimentStatus.CANCELLED,
                "failure_code": ExperimentFailureCode.CANDIDATE_FAILED,
            },
            "cancelled_attempt_failure_code_drift",
        ),
    ],
)
def test_assembler_rejects_impossible_attempt_outcomes(
    tmp_path: Path,
    changes: dict[str, object],
    reason: str,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    attempt = case.attempts[2]
    drifted = replace(
        attempt,
        projection=replace(attempt.projection, **changes),
    )

    _assert_rejected(
        lambda: case.assemble(
            attempts=_replace_attempt(case.attempts, 2, drifted),
        ),
        reason,
    )


def test_cancelled_attempt_without_run_id_remains_valid_terminal_history(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    fold = case.folds[2]
    cancelled_fold = replace(
        fold,
        projection=replace(fold.projection, status=ExperimentStatus.CANCELLED),
    )
    attempt = case.attempts[2]
    cancelled_attempt = replace(
        attempt,
        projection=replace(
            attempt.projection,
            status=ExperimentStatus.CANCELLED,
            backtest_run_id=None,
            checkpoint_ref=None,
            failure_code=None,
        ),
    )

    collected = case.assemble(
        folds=_replace_fold(case.folds, 2, cancelled_fold),
        attempts=_replace_attempt(case.attempts, 2, cancelled_attempt),
    )

    assert all(
        row.fold_id != fold.spec.key.fold_id
        or row.candidate_id != fold.spec.key.candidate_id
        for row in collected.source_rows
    )


def _failed_parent(attempt: AttemptView) -> AttemptView:
    return replace(
        attempt,
        projection=replace(
            attempt.projection,
            status=ExperimentStatus.FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        ),
    )


def _successor(
    parent: AttemptView,
    *,
    ordinal: int,
    parent_attempt_id: AttemptId,
    run_id: BacktestRunId,
) -> AttemptView:
    attempt_id = AttemptId(f"{parent.spec.attempt_id}:retry-{ordinal}")
    created_at = fixtures.NOW + timedelta(seconds=ordinal)
    return AttemptView(
        AttemptPersistenceSpec(
            attempt_id,
            parent.spec.fold_key,
            ordinal,
            parent_attempt_id,
            None,
            parent.spec.reproduction_fingerprint,
            created_at,
        ),
        AttemptProjection(
            attempt_id,
            ExperimentStatus.COMPLETED,
            run_id,
            None,
            None,
            created_at,
            created_at,
            1,
        ),
    )


def _with_retry(
    case: fixtures.EvidenceCase,
    parent: AttemptView,
    successor: AttemptView,
) -> tuple[AttemptView, ...]:
    return (
        case.attempts[0],
        case.attempts[1],
        parent,
        successor,
        case.attempts[3],
    )


def test_assembler_rejects_duplicate_run_identity_within_retry_history(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    parent = _failed_parent(case.attempts[2])
    run_id = parent.projection.backtest_run_id
    assert run_id is not None
    successor = _successor(
        parent,
        ordinal=2,
        parent_attempt_id=parent.spec.attempt_id,
        run_id=run_id,
    )

    _assert_rejected(
        lambda: case.assemble(attempts=_with_retry(case, parent, successor)),
        "attempt_run_identity_drift",
    )


def test_assembler_rejects_lineage_on_first_attempt(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    attempt = case.attempts[2]
    drifted = replace(
        attempt,
        spec=replace(
            attempt.spec,
            parent_attempt_id=AttemptId("ghost-parent"),
        ),
    )

    _assert_rejected(
        lambda: case.assemble(
            attempts=_replace_attempt(case.attempts, 2, drifted),
        ),
        "first_attempt_invalid",
    )


def test_assembler_rejects_retry_with_wrong_parent_identity(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    parent = _failed_parent(case.attempts[2])
    successor = _successor(
        parent,
        ordinal=2,
        parent_attempt_id=AttemptId("wrong-parent"),
        run_id=BacktestRunId("run:candidate-selected:wf-2:retry-2"),
    )

    _assert_rejected(
        lambda: case.assemble(attempts=_with_retry(case, parent, successor)),
        "attempt_lineage_drift",
    )


def test_assembler_rejects_retry_ordinal_gap(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    parent = _failed_parent(case.attempts[2])
    successor = _successor(
        parent,
        ordinal=3,
        parent_attempt_id=parent.spec.attempt_id,
        run_id=BacktestRunId("run:candidate-selected:wf-2:retry-3"),
    )

    _assert_rejected(
        lambda: case.assemble(attempts=_with_retry(case, parent, successor)),
        "attempt_ordinal_gap",
    )


def test_completed_fold_requires_terminal_attempt_evidence(tmp_path: Path) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())

    _assert_rejected(
        lambda: case.assemble(
            attempts=(*case.attempts[:2], case.attempts[3]),
        ),
        "terminal_attempt_evidence_missing",
    )


def test_cancelled_baseline_fold_still_requires_baseline_attempt_evidence(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    fold = case.folds[0]
    cancelled = replace(
        fold,
        projection=replace(fold.projection, status=ExperimentStatus.CANCELLED),
    )

    _assert_rejected(
        lambda: case.assemble(
            folds=_replace_fold(case.folds, 0, cancelled),
            attempts=case.attempts[1:],
        ),
        "baseline_attempt_evidence_missing",
    )


def test_assembler_rejects_untyped_public_inputs_before_provider_access(
    tmp_path: Path,
) -> None:
    case = fixtures.build_case(tmp_path, publish_indices=())
    assembler = _assembler(case)

    _assert_rejected(
        lambda: assembler.assemble(
            cast("ExperimentSchedulerSnapshot", object()),
            fixtures.snapshot_manifest(),
        ),
        "invalid_walk_forward_collection_input",
    )
    _assert_rejected(
        lambda: assembler.assemble(
            case.snapshot(),
            cast("SnapshotManifestProjection", object()),
        ),
        "invalid_walk_forward_collection_input",
    )
