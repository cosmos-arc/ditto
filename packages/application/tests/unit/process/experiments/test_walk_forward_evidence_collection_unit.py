# pyright: reportPrivateUsage=false
"""Unit tests for production walk-forward evidence collection."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from statistics import stdev

import pytest
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CheckpointRef,
    ContentHash,
    ExperimentFailureCode,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldView,
    ResearchMetricId,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FOLD_SELECTION_TRACE_ARTIFACT_KINDS,
    LoadedFoldSelectionTraceArtifacts,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.comparison import (
    build_candidate_comparison,
)
from ditto_application.processes.experiments.execution_bundle import (
    ResearchExecutionSemantics,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.walk_forward import (
    CandidateWalkForwardStatus,
    aggregate_walk_forward,
)

from .walk_forward_evidence_collection_fixtures import (
    CANDIDATE_ID,
    NOW,
    Resolver,
    artifact_identity,
    build_case,
    snapshot_manifest,
    trace_identity,
)


def _topology_variant(
    fold: FoldView,
    *,
    fold_id: FoldId | None = None,
    ordinal: int | None = None,
    purge_sessions: int | None = None,
) -> FoldView:
    original = fold.spec
    key = FoldKey(
        original.key.experiment_id,
        original.key.candidate_id,
        original.key.fold_id if fold_id is None else fold_id,
    )
    spec = FoldPersistenceSpec.create(
        key,
        original.ordinal if ordinal is None else ordinal,
        original.fold_role,
        original.train_window,
        original.test_window,
        (original.purge_sessions if purge_sessions is None else purge_sessions),
        original.embargo_sessions,
    )
    return FoldView(spec, replace(fold.projection, key=key))


def test_collects_real_indexed_reports_into_deterministic_walk_forward_metrics(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)

    collected = case.assemble()

    assert tuple(
        (row.fold_ordinal, row.candidate_ordinal) for row in collected.source_rows
    ) == ((2, 1), (2, 2), (3, 1), (3, 2))
    assert tuple(
        (
            row.parameter_hash,
            row.resolved_spec_hash,
        )
        for row in collected.source_rows
        if row.candidate_id == CANDIDATE_ID
    ) == tuple(
        (
            case.snapshot().launch_spec.execution_bindings[1].parameter_hash,
            case.snapshot().launch_spec.execution_bindings[1].resolved_spec_hash,
        )
        for _ in range(2)
    )
    candidate = collected.aggregation.candidates[1]
    returns = (0.1, 105.0 / 110.0 - 1.0, 0.06, 112.0 / 106.0 - 1.0)
    expected_sharpe = sum(returns) / len(returns) / stdev(returns) * math.sqrt(252)
    assert candidate.metrics[ResearchMetricId.NET_RETURN].value == pytest.approx(17.6)
    assert candidate.metrics[ResearchMetricId.SHARPE_RATIO].value == pytest.approx(
        expected_sharpe
    )
    assert collected.fold_cost_config_hashes == tuple(
        ContentHash(
            case.semantics[
                row.execution_binding.fold_view.spec.key
            ].policy.canonical_hash
        )
        for row in collected.source_rows
    )
    assert collected.missing_artifact_refs == ()
    assert len(collected.selection_traces) == 4
    assert all(
        type(bundle) is LoadedFoldSelectionTraceArtifacts
        and bundle.evidence.initial_universe == ()
        for bundle in collected.selection_traces
    )


def test_missing_all_four_trace_files_preserves_report_metrics_and_adds_refs(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, trace_publish_indices=(0, 1, 3))
    missing_fold = case.folds[2]
    missing_attempt = case.attempts[2]
    identity = trace_identity(missing_fold, missing_attempt)

    collected = case.assemble()

    row = next(
        item
        for item in collected.source_rows
        if item.fold_id == missing_fold.spec.key.fold_id
        and item.candidate_id == missing_fold.spec.key.candidate_id
    )
    assert row.report_artifact is not None
    assert (
        collected.aggregation.candidates[1].status
        is CandidateWalkForwardStatus.COMPLETED
    )
    assert collected.missing_artifact_refs == tuple(
        sorted(
            (
                identity.relative_path(kind)
                for kind in FOLD_SELECTION_TRACE_ARTIFACT_KINDS
            ),
            key=str.encode,
        )
    )
    assert len(collected.selection_traces) == 3


def test_partial_trace_index_fails_integrity_instead_of_producing_collection(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    identity = trace_identity(case.folds[2], case.attempts[2])
    del case.index.records[identity.artifact_id(FOLD_SELECTION_TRACE_ARTIFACT_KINDS[0])]

    with pytest.raises(ExperimentIntegrityError):
        case.assemble()


def test_resolves_execution_semantics_for_every_walk_forward_source_row(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)

    class RecordingResolver:
        def __init__(self) -> None:
            self.fold_keys: list[FoldKey] = []

        def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
            self.fold_keys.append(fold.spec.key)
            return case.semantics[fold.spec.key]

    resolver = RecordingResolver()

    collected = case.assemble(resolver=resolver)

    assert tuple(resolver.fold_keys) == tuple(
        row.execution_binding.fold_view.spec.key for row in collected.source_rows
    )
    assert len(collected.fold_cost_config_hashes) == len(collected.source_rows) == 4


def test_missing_nonbaseline_execution_semantics_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    semantics = dict(case.semantics)
    del semantics[case.folds[2].spec.key]

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics=semantics)

    assert (
        captured.value.details["reason"] == "walk_forward_execution_semantics_missing"
    )


def test_effective_runtime_parameter_hash_can_differ_from_candidate_hash(
    tmp_path: Path,
) -> None:
    """Defaulted runtime values must not drift the frozen candidate identity."""
    case = build_case(tmp_path, publish_indices=())
    effective_parameter_hash = "d" * 64
    semantics = dict(case.semantics)
    for key, value in tuple(semantics.items()):
        if key.candidate_id != CANDIDATE_ID:
            continue
        assert type(value.strategy) is StrategyExecutionBinding
        semantics[key] = replace(
            value,
            strategy=replace(
                value.strategy,
                parameter_hash=effective_parameter_hash,
            ),
        )
    attempts = tuple(
        replace(
            attempt,
            spec=replace(
                attempt.spec,
                reproduction_fingerprint=semantics[
                    attempt.spec.fold_key
                ].reproduction_fingerprint,
            ),
        )
        for attempt in case.attempts
    )
    adjusted = replace(case, attempts=attempts, semantics=semantics)
    for fold, attempt in zip(adjusted.folds, adjusted.attempts, strict=True):
        adjusted.publish_report(fold, attempt)
        adjusted.publish_trace(fold, attempt)

    collected = adjusted.assemble()

    assert all(
        row.parameter_hash != ContentHash(effective_parameter_hash)
        for row in collected.source_rows
        if row.candidate_id == CANDIDATE_ID
    )


@pytest.mark.parametrize(
    ("field_name", "drifted_value"),
    [
        ("candidate_id", "candidate-other"),
        ("fold_id", "fold-other"),
        ("is_baseline", True),
    ],
)
def test_nonbaseline_execution_semantics_identity_drift_fails_closed(
    tmp_path: Path,
    field_name: str,
    drifted_value: object,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[2].spec.key
    drifted = replace(case.semantics[key])
    object.__setattr__(drifted, field_name, drifted_value)
    semantics = {**case.semantics, key: drifted}

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics=semantics)

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


@pytest.mark.parametrize(
    "drift",
    ["snapshot_id", "manifest_hash", "known_at_policy"],
)
def test_nonbaseline_snapshot_lineage_drift_fails_closed(
    tmp_path: Path,
    drift: str,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[2].spec.key
    original = case.semantics[key]
    if drift == "known_at_policy":
        snapshot = replace(original.snapshot)
        object.__setattr__(snapshot, "known_at_policy", "unsafe")
    else:
        exact = replace(
            original.snapshot.exact_snapshot,
            **{drift: ("snapshot-other" if drift == "snapshot_id" else "0" * 64)},
        )
        snapshot = replace(original.snapshot, exact_snapshot=exact)
    semantics_value = replace(original)
    object.__setattr__(semantics_value, "snapshot", snapshot)

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics={**case.semantics, key: semantics_value})

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


@pytest.mark.parametrize("field_name", ["parameter_hash", "resolved_spec_hash"])
def test_nonbaseline_launch_binding_drift_fails_closed(
    tmp_path: Path,
    field_name: str,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[2].spec.key
    original = case.semantics[key]
    strategy = replace(original.strategy, **{field_name: "0" * 64})
    semantics_value = replace(original)
    object.__setattr__(semantics_value, "strategy", strategy)

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics={**case.semantics, key: semantics_value})

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


@pytest.mark.parametrize(
    ("field_name", "drifted_value"),
    [
        ("strategy_id", "other-strategy"),
        ("version", 9),
        ("spec_hash", "f" * 64),
    ],
)
def test_nonbaseline_exact_strategy_launch_drift_fails_closed(
    tmp_path: Path,
    field_name: str,
    drifted_value: object,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    original = case.semantics[key]
    assert type(original.strategy) is StrategyExecutionBinding
    exact_strategy = replace(
        original.strategy.exact_strategy,
        **{field_name: drifted_value},
    )
    strategy = replace(original.strategy, exact_strategy=exact_strategy)
    semantics_value = replace(original, strategy=strategy)
    attempt = replace(
        case.attempts[3],
        spec=replace(
            case.attempts[3].spec,
            reproduction_fingerprint=semantics_value.reproduction_fingerprint,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(*case.attempts[:3], attempt),
            semantics={**case.semantics, key: semantics_value},
        )

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_nonbaseline_node_registry_manifest_drift_fails_closed(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    original = case.semantics[key]
    assert type(original.strategy) is StrategyExecutionBinding
    strategy = replace(original.strategy, node_registry_manifest_hash="0" * 64)
    semantics_value = replace(original, strategy=strategy)
    attempt = replace(
        case.attempts[3],
        spec=replace(
            case.attempts[3].spec,
            reproduction_fingerprint=semantics_value.reproduction_fingerprint,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(*case.attempts[:3], attempt),
            semantics={**case.semantics, key: semantics_value},
        )

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_nonbaseline_attempt_fingerprint_drift_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    drifted = replace(
        case.attempts[2],
        spec=replace(
            case.attempts[2].spec,
            reproduction_fingerprint=ContentHash("0" * 64),
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(attempts=(*case.attempts[:2], drifted, case.attempts[3]))

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_observes_cross_fold_cost_hash_drift_without_rejecting_collection(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    original = case.semantics[key]
    slippage = replace(
        original.policy.slippage,
        basis_points=original.policy.slippage.basis_points + 1,
    )
    policy = replace(original.policy, slippage=slippage)
    backtest = replace(
        original.backtest,
        slippage_basis_points=slippage.basis_points,
        policy_hash=policy.canonical_hash,
    )
    drifted = replace(original, policy=policy, backtest=backtest)
    semantics = {**case.semantics, key: drifted}
    attempt = replace(
        case.attempts[3],
        spec=replace(
            case.attempts[3].spec,
            reproduction_fingerprint=drifted.reproduction_fingerprint,
        ),
    )

    collected = case.assemble(
        attempts=(*case.attempts[:3], attempt),
        semantics=semantics,
    )

    assert collected.fold_cost_config_hashes[-1] == ContentHash(policy.canonical_hash)
    assert len(set(collected.fold_cost_config_hashes)) == 2


def test_mutated_policy_derived_hash_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    semantics_value = replace(case.semantics[key])
    policy = replace(semantics_value.policy)
    object.__setattr__(policy, "canonical_hash", "0" * 64)
    object.__setattr__(semantics_value, "policy", policy)

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics={**case.semantics, key: semantics_value})

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_mutated_backtest_policy_hash_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    semantics_value = replace(case.semantics[key])
    backtest = replace(semantics_value.backtest)
    object.__setattr__(backtest, "policy_hash", "f" * 64)
    object.__setattr__(semantics_value, "backtest", backtest)

    with pytest.raises(AppProcessError) as captured:
        case.assemble(semantics={**case.semantics, key: semantics_value})

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_mutated_semantics_fingerprint_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    key = case.folds[3].spec.key
    semantics_value = replace(case.semantics[key])
    forged_fingerprint = ContentHash("f" * 64)
    object.__setattr__(
        semantics_value,
        "reproduction_fingerprint",
        forged_fingerprint,
    )
    attempt = replace(
        case.attempts[3],
        spec=replace(
            case.attempts[3].spec,
            reproduction_fingerprint=forged_fingerprint,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(*case.attempts[:3], attempt),
            semantics={**case.semantics, key: semantics_value},
        )

    assert captured.value.details["reason"] == "walk_forward_execution_semantics_drift"


def test_later_resolver_call_cannot_mutate_validated_cost_hash(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    expected_by_key = {
        key: ContentHash(semantics.policy.canonical_hash)
        for key, semantics in case.semantics.items()
    }

    class MutatingResolver:
        def __init__(self) -> None:
            self.calls = 0
            self.validated_candidate: ResearchExecutionSemantics | None = None

        def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
            self.calls += 1
            if self.calls == 3:
                target = self.validated_candidate
                assert target is not None
                slippage = replace(
                    target.policy.slippage,
                    basis_points=target.policy.slippage.basis_points + 1,
                )
                object.__setattr__(
                    target,
                    "policy",
                    replace(target.policy, slippage=slippage),
                )
            semantics = case.semantics[fold.spec.key]
            if self.calls == 2:
                self.validated_candidate = semantics
            return semantics

    collected = case.assemble(resolver=MutatingResolver())

    assert collected.fold_cost_config_hashes == tuple(
        expected_by_key[row.execution_binding.fold_view.spec.key]
        for row in collected.source_rows
    )


@pytest.mark.parametrize(
    "cost_hashes",
    [
        (),
        ["0" * 64],
        ("0" * 64, "0" * 64, "0" * 64, "0" * 64),
    ],
)
def test_collected_container_rejects_invalid_fold_cost_config_hashes(
    tmp_path: Path,
    cost_hashes: object,
) -> None:
    case = build_case(tmp_path)
    collected = case.assemble()

    with pytest.raises(AppProcessError) as captured:
        replace(collected, fold_cost_config_hashes=cost_hashes)

    assert captured.value.details["reason"] == "invalid_fold_cost_config_hashes"


def test_candidate_missing_one_walk_forward_fold_fails_topology_gate(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            folds=case.folds[:3],
            attempts=case.attempts[:3],
        )

    assert captured.value.details["reason"] == "candidate_walk_forward_topology_drift"


def test_candidate_missing_all_walk_forward_folds_fails_topology_gate(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            folds=case.folds[:2],
            attempts=case.attempts[:2],
        )

    assert captured.value.details["reason"] == "candidate_walk_forward_topology_drift"


def test_candidate_extra_walk_forward_fold_fails_topology_gate(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    extra = _topology_variant(
        case.folds[3],
        fold_id=FoldId("wf-extra"),
        ordinal=4,
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(folds=(*case.folds, extra))

    assert captured.value.details["reason"] == "candidate_walk_forward_topology_drift"


def test_candidate_isolation_drift_fails_shared_topology_gate(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    drifted = _topology_variant(
        case.folds[2],
        purge_sessions=case.folds[2].spec.purge_sessions + 1,
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            folds=(case.folds[0], case.folds[1], drifted, case.folds[3]),
        )

    assert captured.value.details["reason"] == "candidate_walk_forward_topology_drift"


def test_candidate_with_all_walk_forward_folds_cancelled_cannot_disappear(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    cancelled = tuple(
        replace(
            fold,
            projection=replace(
                fold.projection,
                status=ExperimentStatus.CANCELLED,
            ),
        )
        for fold in case.folds[2:]
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            folds=(case.folds[0], case.folds[1], *cancelled),
            attempts=case.attempts[:2],
        )

    assert (
        captured.value.details["reason"] == "candidate_walk_forward_source_rows_missing"
    )


def test_missing_completed_report_is_objective_and_not_evaluated(
    tmp_path: Path,
) -> None:
    case = build_case(
        tmp_path,
        publish_indices=(0, 1, 3),
        trace_publish_indices=(0, 1, 2, 3),
    )

    collected = case.assemble()

    assert collected.missing_artifact_refs == (
        artifact_identity(case.folds[2], case.attempts[2]).relative_path,
    )
    assert (
        collected.aggregation.candidates[1].status
        is CandidateWalkForwardStatus.NOT_EVALUATED
    )


def test_multiple_missing_completed_reports_use_canonical_artifact_order(
    tmp_path: Path,
) -> None:
    case = build_case(
        tmp_path,
        publish_indices=(1, 3),
        trace_publish_indices=(0, 1, 2, 3),
    )

    collected = case.assemble()

    assert collected.missing_artifact_refs == tuple(
        sorted(
            (
                artifact_identity(case.folds[0], case.attempts[0]).relative_path,
                artifact_identity(case.folds[2], case.attempts[2]).relative_path,
            ),
            key=str.encode,
        )
    )


def test_collected_container_rejects_erased_missing_artifact_refs(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=(0, 1, 3))
    collected = case.assemble()

    with pytest.raises(AppProcessError) as captured:
        replace(collected, missing_artifact_refs=())

    assert captured.value.details["reason"] == "missing_artifact_ref_parity_drift"


@pytest.mark.parametrize("keep_cancelled_attempt", [False, True])
def test_failed_fold_and_cancelled_fold_never_read_artifacts(
    tmp_path: Path,
    *,
    keep_cancelled_attempt: bool,
) -> None:
    case = build_case(tmp_path, publish_indices=(0, 1))
    failed_fold = replace(
        case.folds[2],
        projection=replace(
            case.folds[2].projection,
            status=ExperimentStatus.FAILED,
        ),
    )
    cancelled_fold = replace(
        case.folds[3],
        projection=replace(
            case.folds[3].projection,
            status=ExperimentStatus.CANCELLED,
        ),
    )
    failed_attempt = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            status=ExperimentStatus.FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        ),
    )
    cancelled_attempt = replace(
        case.attempts[3],
        projection=replace(
            case.attempts[3].projection,
            status=ExperimentStatus.CANCELLED,
        ),
    )
    attempts = (
        case.attempts[0],
        case.attempts[1],
        failed_attempt,
        *((cancelled_attempt,) if keep_cancelled_attempt else ()),
    )

    collected = case.assemble(
        folds=(case.folds[0], case.folds[1], failed_fold, cancelled_fold),
        attempts=attempts,
    )

    assert (
        collected.aggregation.candidates[1].status is CandidateWalkForwardStatus.FAILED
    )
    assert collected.source_rows[1].failure_reason == "candidate_failed"
    assert len(collected.source_rows) == 3
    assert collected.missing_artifact_refs == ()


def test_retry_selects_highest_attempt_and_accepts_independent_checkpoint_ref(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=(0, 1, 3))
    parent = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            status=ExperimentStatus.FAILED,
            checkpoint_ref=CheckpointRef("checkpoint-1"),
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        ),
    )
    created_at = NOW + timedelta(seconds=1)
    successor_id = AttemptId("attempt:candidate-selected:wf-2:retry-2")
    successor = AttemptView(
        AttemptPersistenceSpec(
            successor_id,
            parent.spec.fold_key,
            2,
            parent.spec.attempt_id,
            parent.projection.backtest_run_id,
            parent.spec.reproduction_fingerprint,
            created_at,
        ),
        AttemptProjection(
            successor_id,
            ExperimentStatus.COMPLETED,
            BacktestRunId("run:candidate-selected:wf-2:retry-2"),
            None,
            None,
            created_at,
            created_at,
            1,
        ),
    )
    case.publish(case.folds[2], successor)

    collected = case.assemble(
        attempts=(
            case.attempts[3],
            successor,
            case.attempts[0],
            parent,
            case.attempts[1],
        )
    )

    selected = next(
        row
        for row in collected.source_rows
        if row.candidate_id == CANDIDATE_ID and row.fold_ordinal == 2
    )
    assert selected.attempt_id == successor_id
    selected_trace = next(
        bundle
        for bundle in collected.selection_traces
        if bundle.identity.candidate_id == CANDIDATE_ID
        and bundle.identity.fold_id == selected.fold_id
    )
    assert selected_trace.identity.attempt_id == successor_id
    assert selected_trace.identity.run_id == successor.projection.backtest_run_id
    assert collected.missing_artifact_refs == ()


def test_duplicate_attempt_ordinal_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    duplicate_id = AttemptId("attempt:candidate-selected:wf-2:duplicate")
    duplicate = replace(
        case.attempts[2],
        spec=replace(case.attempts[2].spec, attempt_id=duplicate_id),
        projection=replace(case.attempts[2].projection, attempt_id=duplicate_id),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(attempts=(*case.attempts, duplicate))

    assert captured.value.details["reason"] == "duplicate_attempt_ordinal"


@pytest.mark.parametrize(
    ("status", "failure_code", "reason"),
    [
        (
            ExperimentStatus.FAILED,
            ExperimentFailureCode.CANDIDATE_FAILED,
            "fold_attempt_status_mismatch",
        ),
        (ExperimentStatus.RUNNING, None, "latest_attempt_not_terminal"),
    ],
)
def test_status_mismatch_and_latest_nonterminal_fail_closed(
    tmp_path: Path,
    status: ExperimentStatus,
    failure_code: ExperimentFailureCode | None,
    reason: str,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    drifted = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            status=status,
            failure_code=failure_code,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(
                case.attempts[0],
                case.attempts[1],
                drifted,
                case.attempts[3],
            )
        )

    assert captured.value.details["reason"] == reason


def test_completed_attempt_without_run_id_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    drifted = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            backtest_run_id=None,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(
                case.attempts[0],
                case.attempts[1],
                drifted,
                case.attempts[3],
            )
        )

    assert captured.value.details["reason"] == "terminal_attempt_run_id_missing"


def test_malformed_attempt_value_fails_closed_without_attribute_error(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    snapshot = case.snapshot()
    object.__setattr__(snapshot, "attempts", (object(),))
    assembler = WalkForwardEvidenceAssembler(
        report_reader=case.adapter,
        fold_selection_trace_reader=case.trace_adapter,
        semantics_resolver=Resolver(case.semantics),
    )

    with pytest.raises(AppProcessError) as captured:
        assembler.assemble(snapshot, snapshot_manifest())

    assert captured.value.details["reason"] == "invalid_attempt_evidence"


def test_duplicate_attempt_id_across_ordinals_fails_closed_after_mutation(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    parent = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            status=ExperimentStatus.FAILED,
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        ),
    )
    created_at = NOW + timedelta(seconds=1)
    successor = AttemptView(
        AttemptPersistenceSpec(
            parent.spec.attempt_id,
            parent.spec.fold_key,
            2,
            parent.spec.attempt_id,
            None,
            parent.spec.reproduction_fingerprint,
            created_at,
        ),
        AttemptProjection(
            parent.spec.attempt_id,
            ExperimentStatus.COMPLETED,
            BacktestRunId("run:candidate-selected:wf-2:duplicate-id"),
            None,
            None,
            created_at,
            created_at,
            1,
        ),
    )
    snapshot = case.snapshot()
    object.__setattr__(
        snapshot,
        "attempts",
        (
            case.attempts[0],
            case.attempts[1],
            parent,
            successor,
            case.attempts[3],
        ),
    )
    assembler = WalkForwardEvidenceAssembler(
        report_reader=case.adapter,
        fold_selection_trace_reader=case.trace_adapter,
        semantics_resolver=Resolver(case.semantics),
    )

    with pytest.raises(AppProcessError) as captured:
        assembler.assemble(snapshot, snapshot_manifest())

    assert (
        captured.value.details["reason"] == "scheduler_snapshot_attempt_lineage_invalid"
    )


def test_cross_fold_duplicate_attempt_id_is_rejected_by_snapshot_revalidation(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    duplicate_id = case.attempts[0].spec.attempt_id
    duplicate = replace(
        case.attempts[2],
        spec=replace(case.attempts[2].spec, attempt_id=duplicate_id),
        projection=replace(case.attempts[2].projection, attempt_id=duplicate_id),
    )
    snapshot = case.snapshot()
    object.__setattr__(
        snapshot,
        "attempts",
        (
            case.attempts[0],
            case.attempts[1],
            duplicate,
            case.attempts[3],
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        WalkForwardEvidenceAssembler(
            report_reader=case.adapter,
            fold_selection_trace_reader=case.trace_adapter,
            semantics_resolver=Resolver(case.semantics),
        ).assemble(snapshot, snapshot_manifest())

    assert (
        captured.value.details["reason"] == "scheduler_snapshot_attempt_lineage_invalid"
    )


def test_mutated_manifest_is_revalidated_at_collection_boundary(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    manifest = snapshot_manifest()
    object.__setattr__(manifest, "pit_policy", "")

    with pytest.raises(AppProcessError) as captured:
        WalkForwardEvidenceAssembler(
            report_reader=case.adapter,
            fold_selection_trace_reader=case.trace_adapter,
            semantics_resolver=Resolver(case.semantics),
        ).assemble(case.snapshot(), manifest)

    assert captured.value.details["reason"] == "invalid_snapshot_manifest_projection"


def test_baseline_attempt_fingerprint_drift_fails_closed(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())
    drifted = replace(
        case.attempts[0],
        spec=replace(
            case.attempts[0].spec,
            reproduction_fingerprint=ContentHash("0" * 64),
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(attempts=(drifted, *case.attempts[1:]))

    assert captured.value.details["reason"] == "baseline_execution_semantics_drift"


def test_two_baseline_semantics_with_different_plans_fail_closed(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path, publish_indices=())
    original = case.semantics[case.folds[1].spec.key]
    drifted_plan = default_baseline_registry().plan(
        BaselinePlanRequest(
            BaselineRef("stock_universe_equal_weight", 1),
            original.snapshot.exact_snapshot,
            ExactUniverseIdentity("other-universe", original.membership_hash),
        )
    )
    drifted_semantics = replace(original, baseline_plan=drifted_plan)
    semantics = {**case.semantics, case.folds[1].spec.key: drifted_semantics}
    drifted_attempt = replace(
        case.attempts[1],
        spec=replace(
            case.attempts[1].spec,
            reproduction_fingerprint=drifted_semantics.reproduction_fingerprint,
        ),
    )

    with pytest.raises(AppProcessError) as captured:
        case.assemble(
            attempts=(case.attempts[0], drifted_attempt, *case.attempts[2:]),
            semantics=semantics,
        )

    assert captured.value.details["reason"] == "baseline_plan_identity_drift"


def test_reader_corruption_is_not_downgraded_to_missing(tmp_path: Path) -> None:
    case = build_case(tmp_path)
    identity = artifact_identity(case.folds[2], case.attempts[2])
    record = case.index.records[identity.artifact_id]
    (case.index.artifact_root / record.relative_path).write_bytes(b"{")

    with pytest.raises(ExperimentIntegrityError):
        case.assemble()


def test_input_permutations_produce_identical_collection(tmp_path: Path) -> None:
    case = build_case(tmp_path)

    original = case.assemble()
    permuted = case.assemble(
        folds=tuple(reversed(case.folds)),
        attempts=tuple(reversed(case.attempts)),
    )

    assert permuted == original
    assert permuted.fold_cost_config_hashes == original.fold_cost_config_hashes
    assert permuted.comparison.content_hash == original.comparison.content_hash
    assert permuted.aggregation.content_hash == original.aggregation.content_hash


class _ForgedSemantics(ResearchExecutionSemantics):
    """Subclass without fields proving exact-type semantics validation."""


class _ForgedResolver:
    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        _ = fold
        return object.__new__(_ForgedSemantics)


def test_semantics_subclass_is_rejected_before_field_access(tmp_path: Path) -> None:
    case = build_case(tmp_path, publish_indices=())

    with pytest.raises(AppProcessError) as captured:
        case.assemble(resolver=_ForgedResolver())

    assert captured.value.details["reason"] == "invalid_baseline_execution_semantics"


def test_collected_container_rejects_aggregation_from_another_comparison(
    tmp_path: Path,
) -> None:
    case = build_case(tmp_path)
    collected = case.assemble()
    altered = build_candidate_comparison(
        collected.comparison.baseline,
        collected.source_rows[:-1],
    )

    with pytest.raises(AppProcessError) as captured:
        replace(collected, aggregation=aggregate_walk_forward(altered))

    assert captured.value.details["reason"] == "invalid_collected_walk_forward_evidence"
