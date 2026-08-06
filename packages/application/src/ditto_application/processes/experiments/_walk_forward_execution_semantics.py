"""Exact execution-semantics lineage for persisted walk-forward folds."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Protocol

from ditto_analysis.experiments.models import CandidateId, ContentHash
from ditto_analysis.experiments.persistence import (
    AttemptView,
    FoldKey,
    FoldView,
    encode_launch_spec,
)
from ditto_analysis.experiments.specs import (
    CandidateExecutionBinding,
    CandidateSpec,
    ExperimentLaunchSpec,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_inputs import (
    SnapshotManifestProjection,
)
from ditto_application.processes.experiments._evidence_values import (
    comparison_error,
)
from ditto_application.processes.experiments.execution_bundle import (
    BaselineExecutorBinding,
    ResearchExecutionSemantics,
    ResearchSnapshotBinding,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ResearchExecutionPolicy,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentSchedulerSnapshot,
)

__all__ = [
    "ValidatedWalkForwardExecutionSemantics",
    "WalkForwardExecutionBindings",
    "WalkForwardExecutionSemanticsResolver",
    "build_walk_forward_execution_bindings",
    "resolve_walk_forward_execution_semantics",
]


class WalkForwardExecutionSemanticsResolver(Protocol):
    """Reconstruct exact result-determining semantics for one persisted fold."""

    def resolve(self, fold: FoldView) -> ResearchExecutionSemantics:
        """Resolve one fold without latest/provider fallback."""
        ...


@dataclass(frozen=True, slots=True)
class WalkForwardExecutionBindings:
    """Canonical launch candidate and execution identities used by all WF folds."""

    baseline: CandidateSpec
    candidates: dict[CandidateId, CandidateSpec]
    execution: dict[CandidateId, CandidateExecutionBinding]
    launch_hash: ContentHash


@dataclass(frozen=True, slots=True)
class ValidatedWalkForwardExecutionSemantics:
    """Detached semantics plus the cost hash captured at validation time."""

    semantics: ResearchExecutionSemantics
    cost_config_hash: ContentHash

    def __post_init__(self) -> None:
        """Reject any untyped trusted-snapshot construction."""
        if (
            type(self.semantics) is not ResearchExecutionSemantics
            or type(self.cost_config_hash) is not ContentHash
        ):
            comparison_error("invalid_validated_execution_semantics")


def build_walk_forward_execution_bindings(
    snapshot: ExperimentSchedulerSnapshot,
) -> WalkForwardExecutionBindings:
    """Revalidate and index the exact launch bindings used by WF evidence."""
    launch = snapshot.launch_spec
    if type(launch) is not ExperimentLaunchSpec:
        comparison_error("invalid_evidence_launch_spec")
    candidates = tuple(launch.candidates)
    bindings = tuple(launch.execution_bindings)
    if (
        any(type(item) is not CandidateSpec for item in candidates)
        or any(type(item) is not CandidateExecutionBinding for item in bindings)
        or len(candidates) != len(bindings)
    ):
        comparison_error("invalid_evidence_launch_spec")
    candidate_by_id = {item.candidate_id: item for item in candidates}
    execution_by_id = {item.candidate_id: item for item in bindings}
    if len(candidate_by_id) != len(candidates) or len(execution_by_id) != len(bindings):
        comparison_error("invalid_evidence_launch_spec")
    baseline_id = launch.promotion_objective.baseline_candidate_id
    baseline = candidate_by_id.get(baseline_id)
    if (
        baseline is None
        or not baseline.is_baseline
        or baseline.ordinal != 1
        or tuple(item for item in candidates if item.is_baseline) != (baseline,)
    ):
        comparison_error("baseline_launch_identity_drift")
    for candidate, binding in zip(candidates, bindings, strict=True):
        if (
            binding.candidate_id != candidate.candidate_id
            or binding.ordinal != candidate.ordinal
            or binding.parameter_hash != candidate.parameter_hash
        ):
            comparison_error("candidate_launch_binding_drift")
    return WalkForwardExecutionBindings(
        baseline,
        candidate_by_id,
        execution_by_id,
        encode_launch_spec(launch).content_hash,
    )


def _semantics_drift_reason(candidate: CandidateSpec) -> str:
    return (
        "baseline_execution_semantics_drift"
        if candidate.is_baseline
        else "walk_forward_execution_semantics_drift"
    )


def _validate_semantics_fold(
    semantics: ResearchExecutionSemantics,
    fold: FoldView,
    *,
    snapshot_state: ExperimentSchedulerSnapshot,
    manifest: SnapshotManifestProjection,
    bindings: WalkForwardExecutionBindings,
    attempt: AttemptView | None,
) -> ValidatedWalkForwardExecutionSemantics:
    spec = fold.spec
    candidate = bindings.candidates[spec.key.candidate_id]
    execution = bindings.execution[spec.key.candidate_id]
    train = spec.train_window
    snapshot = semantics.snapshot
    strategy = semantics.strategy
    policy = semantics.policy
    if type(policy) is not ResearchExecutionPolicy:
        comparison_error(_semantics_drift_reason(candidate))
    rebuilt_policy = replace(policy)
    if policy.canonical_hash != rebuilt_policy.canonical_hash:
        comparison_error(_semantics_drift_reason(candidate))
    try:
        rebuilt_semantics = replace(semantics, policy=rebuilt_policy)
    except AppProcessError:
        comparison_error(_semantics_drift_reason(candidate))
    if (
        semantics.canonical_payload != rebuilt_semantics.canonical_payload
        or semantics.reproduction_fingerprint
        != rebuilt_semantics.reproduction_fingerprint
    ):
        comparison_error(_semantics_drift_reason(candidate))
    if (
        semantics.experiment_id != str(spec.key.experiment_id)
        or semantics.candidate_id != str(spec.key.candidate_id)
        or semantics.fold_id != str(spec.key.fold_id)
        or semantics.fold_role != spec.fold_role.value
        or semantics.is_baseline is not candidate.is_baseline
        or semantics.launch_spec_hash != str(bindings.launch_hash)
        or semantics.fold_spec_hash != str(spec.payload_hash)
        or semantics.train_start != (None if train is None else train.start)
        or semantics.train_end != (None if train is None else train.end)
        or semantics.test_start != spec.test_window.start
        or semantics.test_end != spec.test_window.end
        or semantics.purge_sessions != spec.purge_sessions
        or semantics.embargo_sessions != spec.embargo_sessions
        or type(snapshot) is not ResearchSnapshotBinding
        or snapshot.exact_snapshot.snapshot_id
        != str(snapshot_state.launch_spec.snapshot_id)
        or snapshot.exact_snapshot.manifest_hash != str(manifest.snapshot_hash)
        or snapshot.known_at_policy != manifest.pit_policy
        # The launch binding hashes the frozen candidate grid values, while
        # StrategyExecutionBinding hashes canonical effective runtime values,
        # including defaults.  The durable resolver and attempt reproduction
        # fingerprint validate that second identity; they need not be equal.
        or (
            type(strategy) is StrategyExecutionBinding
            and (
                strategy.resolved_spec_hash != str(execution.resolved_spec_hash)
                or (
                    not candidate.is_baseline
                    and (
                        f"{strategy.exact_strategy.strategy_id}@{strategy.exact_strategy.version}"
                        != str(snapshot_state.launch_spec.strategy_version)
                        or strategy.exact_strategy.spec_hash
                        != str(snapshot_state.launch_spec.strategy_spec_hash)
                        or strategy.node_registry_manifest_hash
                        != str(manifest.registry_hash)
                    )
                )
            )
        )
        or (
            not candidate.is_baseline and type(strategy) is not StrategyExecutionBinding
        )
        or (
            candidate.is_baseline
            and type(strategy)
            not in {StrategyExecutionBinding, BaselineExecutorBinding}
        )
        or (
            attempt is not None
            and semantics.reproduction_fingerprint
            != attempt.spec.reproduction_fingerprint
        )
    ):
        comparison_error(_semantics_drift_reason(candidate))
    return ValidatedWalkForwardExecutionSemantics(
        deepcopy(rebuilt_semantics),
        ContentHash(rebuilt_policy.canonical_hash),
    )


def _canonical_fold_order(
    folds: tuple[FoldView, ...],
    bindings: WalkForwardExecutionBindings,
) -> tuple[FoldView, ...]:
    return tuple(
        sorted(
            folds,
            key=lambda fold: (
                fold.spec.ordinal,
                bindings.candidates[fold.spec.key.candidate_id].ordinal,
                str(fold.spec.key.fold_id),
                str(fold.spec.key.candidate_id),
            ),
        )
    )


def resolve_walk_forward_execution_semantics(
    resolver: WalkForwardExecutionSemanticsResolver,
    snapshot: ExperimentSchedulerSnapshot,
    manifest: SnapshotManifestProjection,
    bindings: WalkForwardExecutionBindings,
    folds: tuple[FoldView, ...],
    selected: dict[FoldKey, AttemptView | None],
) -> dict[FoldKey, ValidatedWalkForwardExecutionSemantics]:
    """Resolve each WF fold exactly once and validate its persisted lineage."""
    resolved: dict[FoldKey, ValidatedWalkForwardExecutionSemantics] = {}
    for fold in _canonical_fold_order(folds, bindings):
        candidate = bindings.candidates[fold.spec.key.candidate_id]
        try:
            semantics_value = resolver.resolve(fold)
        except LookupError:
            comparison_error(
                "walk_forward_execution_semantics_missing",
                fold_id=str(fold.spec.key.fold_id),
                candidate_id=str(fold.spec.key.candidate_id),
            )
        if type(semantics_value) is not ResearchExecutionSemantics:
            comparison_error(
                "invalid_baseline_execution_semantics"
                if candidate.is_baseline
                else "invalid_walk_forward_execution_semantics"
            )
        semantics = semantics_value
        validated = _validate_semantics_fold(
            semantics,
            fold,
            snapshot_state=snapshot,
            manifest=manifest,
            bindings=bindings,
            attempt=selected[fold.spec.key],
        )
        resolved[fold.spec.key] = validated
    return resolved
