"""Unit tests for deterministic experiment candidate and budget planning."""

from __future__ import annotations

from collections.abc import Sequence

import orjson
import pytest
from ditto_analysis.experiments.specs import ExperimentFailurePolicy
from ditto_application.processes.experiments.planning import (
    BASELINE_PARAMETER_KEY,
    BaselineCandidatePlan,
    BaselineDescriptor,
    BinderCandidatePlan,
    CandidateMatrixSize,
    CandidateMatrixSpec,
    CandidateRole,
    ExperimentBudgetSpec,
    ExperimentPlanningError,
    ExperimentPlanningSpec,
    ExperimentTrack,
    ParameterAxis,
    ResourceCostModel,
    ValidationWorkload,
    estimate_resource_budget,
    expand_candidate_matrix,
    inspect_candidate_matrix_size,
    plan_experiment_work,
)
from ditto_strategy.alpha.parameters import CandidateParameter, ParameterValue


def _baseline() -> BaselineDescriptor:
    return BaselineDescriptor(
        descriptor_type="buy-and-hold",
        payload={
            "benchmark": "000300.SH",
            "include_costs": True,
            "weights": [0.7, 0.3],
            "metadata": {"version": 2, "note": None},
        },
    )


def _parameter_pairs(candidate: BinderCandidatePlan) -> tuple[tuple[str, object], ...]:
    return tuple(
        (parameter.path, parameter.value) for parameter in candidate.binder_parameters
    )


def test_no_axes_expand_to_distinct_baseline_and_default_candidate() -> None:
    plan = expand_candidate_matrix(CandidateMatrixSpec(baseline=_baseline()))

    assert plan.candidate_count == 2
    assert [candidate.ordinal for candidate in plan.candidates] == [1, 2]
    assert [candidate.role for candidate in plan.candidates] == [
        CandidateRole.BASELINE,
        CandidateRole.DEFAULT,
    ]
    assert isinstance(plan.baseline_candidate, BaselineCandidatePlan)
    assert not hasattr(plan.baseline_candidate, "binder_parameters")
    default = plan.binder_candidates[0]
    assert default.binder_parameters == ()
    assert dict(default.persistence_parameters) == {}
    assert plan.baseline_candidate.candidate_hash != default.candidate_hash


def test_baseline_uses_lossless_reserved_persistence_envelope() -> None:
    baseline = _baseline()

    candidate = expand_candidate_matrix(
        CandidateMatrixSpec(baseline=baseline),
    ).baseline_candidate

    assert tuple(candidate.persistence_parameters) == (BASELINE_PARAMETER_KEY,)
    envelope = orjson.loads(
        candidate.persistence_parameters[BASELINE_PARAMETER_KEY],
    )
    assert envelope == {
        "descriptor_type": "buy-and-hold",
        "payload": {
            "benchmark": "000300.SH",
            "include_costs": True,
            "metadata": {"note": None, "version": 2},
            "weights": [0.7, 0.3],
        },
        "schema_version": 1,
    }


def test_cartesian_expansion_is_canonical_across_axis_and_value_order() -> None:
    first = expand_candidate_matrix(
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(
                ParameterAxis(name="z.window", values=(20, 10)),
                ParameterAxis(name="a.mode", values=("slow", "fast")),
            ),
        ),
    )
    reordered = expand_candidate_matrix(
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(
                ParameterAxis(name="a.mode", values=("fast", "slow")),
                ParameterAxis(name="z.window", values=(10, 20)),
            ),
        ),
    )

    assert first.matrix_hash == reordered.matrix_hash
    assert [candidate.candidate_hash for candidate in first.candidates] == [
        candidate.candidate_hash for candidate in reordered.candidates
    ]
    assert [_parameter_pairs(candidate) for candidate in first.binder_candidates] == [
        (("a.mode", "fast"), ("z.window", 10)),
        (("a.mode", "fast"), ("z.window", 20)),
        (("a.mode", "slow"), ("z.window", 10)),
        (("a.mode", "slow"), ("z.window", 20)),
    ]
    assert [candidate.ordinal for candidate in first.candidates] == [1, 2, 3, 4, 5]
    assert all(
        candidate.role is CandidateRole.MATRIX for candidate in first.binder_candidates
    )


def test_canonical_values_preserve_bool_int_float_and_string_identity() -> None:
    plan = expand_candidate_matrix(
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(ParameterAxis(name="node.value", values=("1", 1.0, 1, True)),),
        ),
    )

    values = [
        candidate.binder_parameters[0].value for candidate in plan.binder_candidates
    ]
    typed_values = {(type(value), value) for value in values}
    assert typed_values == {(bool, True), (int, 1), (float, 1.0), (str, "1")}
    assert len({candidate.candidate_hash for candidate in plan.candidates}) == 5


def test_baseline_counts_toward_hard_candidate_limit_without_truncation() -> None:
    exact = expand_candidate_matrix(
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(ParameterAxis(name="node.rank", values=tuple(range(127))),),
        ),
    )

    assert exact.candidate_count == 128
    assert {
        candidate.binder_parameters[0].value for candidate in exact.binder_candidates
    } == set(range(127))

    with pytest.raises(ExperimentPlanningError) as exc_info:
        expand_candidate_matrix(
            CandidateMatrixSpec(
                baseline=_baseline(),
                axes=(ParameterAxis(name="node.rank", values=tuple(range(128))),),
            ),
        )

    assert exc_info.value.details == {
        "code": "MATRIX_TOO_LARGE",
        "candidate_count": 129,
        "candidate_limit": 128,
    }


def test_matrix_size_is_an_independent_typed_canonical_measurement() -> None:
    spec = CandidateMatrixSpec(
        baseline=_baseline(),
        axes=(ParameterAxis(name="node.rank", values=tuple(range(128))),),
    )

    measured = inspect_candidate_matrix_size(spec)

    assert measured == CandidateMatrixSize(
        candidate_count=129,
        candidate_limit=128,
    )
    assert measured.exceeds_limit


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({1, 2}, id="set"),
        pytest.param((value for value in (1, 2)), id="generator"),
        pytest.param([], id="empty"),
        pytest.param([0.0, -0.0], id="canonical-duplicate"),
        pytest.param([float("inf")], id="non-finite"),
    ],
)
def test_axis_requires_an_explicit_nonempty_unique_value_list(
    values: Sequence[ParameterValue],
) -> None:
    with pytest.raises(ExperimentPlanningError) as exc_info:
        ParameterAxis(name="node.value", values=values)

    assert exc_info.value.details["code"] == "SPEC_INVALID"


def test_axis_rejects_duplicate_or_reserved_parameter_names() -> None:
    with pytest.raises(ExperimentPlanningError) as duplicate:
        CandidateMatrixSpec(
            baseline=_baseline(),
            axes=(
                ParameterAxis(name="node.window", values=(10,)),
                ParameterAxis(name="node.window", values=(20,)),
            ),
        )
    with pytest.raises(ExperimentPlanningError) as reserved:
        ParameterAxis(name=BASELINE_PARAMETER_KEY, values=(1,))

    assert duplicate.value.details["code"] == "SPEC_INVALID"
    assert reserved.value.details["code"] == "SPEC_INVALID"


def _budget(
    *,
    candidate_limit: int = 128,
    fold_run_limit: int = 385,
    trading_session_limit: int = 100_000,
    disk_byte_limit: int = 1_000_000,
) -> ExperimentBudgetSpec:
    return ExperimentBudgetSpec(
        candidate_limit=candidate_limit,
        fold_run_limit=fold_run_limit,
        trading_session_limit=trading_session_limit,
        disk_byte_limit=disk_byte_limit,
    )


def _planning_spec(
    *,
    track: ExperimentTrack,
    worker_count: int = 2,
    seed: int = 17,
    failure_policy: ExperimentFailurePolicy | None = None,
    budget: ExperimentBudgetSpec | None = None,
) -> ExperimentPlanningSpec:
    policy = failure_policy or ExperimentFailurePolicy.FAIL_FAST
    return ExperimentPlanningSpec(
        matrix=CandidateMatrixSpec(baseline=_baseline()),
        track=track,
        workload=ValidationWorkload(
            fold_session_counts=(10, 20, 30),
            holdout_session_count=15,
        ),
        cost_model=ResourceCostModel(
            bytes_per_run=100,
            bytes_per_trading_session=2,
        ),
        budget=budget or _budget(),
        seed=seed,
        worker_count=worker_count,
        failure_policy=policy,
    )


def test_promotion_budget_is_three_runs_per_candidate_plus_one_holdout() -> None:
    plan = plan_experiment_work(
        _planning_spec(track=ExperimentTrack.PROMOTION),
    )

    assert plan.candidate_matrix.candidate_count == 2
    assert plan.estimate.validation_run_count == 6
    assert plan.estimate.holdout_run_count == 1
    assert plan.estimate.total_run_count == 7
    assert plan.estimate.estimated_trading_sessions == 135
    assert plan.estimate.estimated_disk_bytes == 970


def test_research_only_budget_is_three_runs_per_candidate_without_holdout() -> None:
    plan = plan_experiment_work(
        _planning_spec(track=ExperimentTrack.RESEARCH_ONLY),
    )

    assert plan.estimate.validation_run_count == 6
    assert plan.estimate.holdout_run_count == 0
    assert plan.estimate.total_run_count == 6
    assert plan.estimate.estimated_trading_sessions == 120
    assert plan.estimate.estimated_disk_bytes == 840


def test_resource_estimate_is_a_pure_function_of_workload_and_cost_model() -> None:
    workload = ValidationWorkload(
        fold_session_counts=(5, 6, 7),
        holdout_session_count=8,
    )
    cost_model = ResourceCostModel(
        bytes_per_run=11,
        bytes_per_trading_session=3,
    )

    first = estimate_resource_budget(
        candidate_count=4,
        track=ExperimentTrack.PROMOTION,
        workload=workload,
        cost_model=cost_model,
    )
    second = estimate_resource_budget(
        candidate_count=4,
        track=ExperimentTrack.PROMOTION,
        workload=workload,
        cost_model=cost_model,
    )

    assert first == second
    assert first.total_run_count == 13
    assert first.estimated_trading_sessions == 80
    assert first.estimated_disk_bytes == 383


@pytest.mark.parametrize("worker_count", [2, 4])
def test_worker_count_accepts_only_bounded_supported_widths(worker_count: int) -> None:
    plan = plan_experiment_work(
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            worker_count=worker_count,
        ),
    )

    assert plan.worker_count == worker_count


@pytest.mark.parametrize("worker_count", [1, 3, 5, True])
def test_worker_count_rejects_every_unsupported_width(worker_count: int) -> None:
    with pytest.raises(ExperimentPlanningError) as exc_info:
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            worker_count=worker_count,
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "invalid_worker_count",
        "worker_count": worker_count,
        "allowed_worker_counts": (2, 4),
    }


def test_plan_fails_closed_when_any_registered_budget_is_exceeded() -> None:
    with pytest.raises(ExperimentPlanningError) as exc_info:
        plan_experiment_work(
            _planning_spec(
                track=ExperimentTrack.PROMOTION,
                budget=_budget(
                    fold_run_limit=6,
                    trading_session_limit=134,
                    disk_byte_limit=969,
                ),
            ),
        )

    assert exc_info.value.details == {
        "code": "BUDGET_EXCEEDED",
        "exceeded": (
            "fold_run_limit",
            "trading_session_limit",
            "disk_byte_limit",
        ),
        "total_run_count": 7,
        "estimated_trading_sessions": 135,
        "estimated_disk_bytes": 970,
    }


def test_seed_failure_policy_worker_and_budget_are_frozen_into_plan_hash() -> None:
    base = plan_experiment_work(
        _planning_spec(track=ExperimentTrack.RESEARCH_ONLY),
    )
    replay = plan_experiment_work(
        _planning_spec(track=ExperimentTrack.RESEARCH_ONLY),
    )
    changed_seed = plan_experiment_work(
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            seed=18,
        ),
    )
    changed_policy = plan_experiment_work(
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        ),
    )
    changed_worker = plan_experiment_work(
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            worker_count=4,
        ),
    )
    changed_budget = plan_experiment_work(
        _planning_spec(
            track=ExperimentTrack.RESEARCH_ONLY,
            budget=_budget(disk_byte_limit=2_000_000),
        ),
    )

    assert base.plan_hash == replay.plan_hash
    assert (
        len(
            {
                base.plan_hash,
                changed_seed.plan_hash,
                changed_policy.plan_hash,
                changed_worker.plan_hash,
                changed_budget.plan_hash,
            },
        )
        == 5
    )
    assert base.seed == 17
    assert base.failure_policy is ExperimentFailurePolicy.FAIL_FAST
    assert base.budget == _budget()


def test_validation_workload_requires_exactly_three_positive_fold_counts() -> None:
    with pytest.raises(ExperimentPlanningError) as exc_info:
        ValidationWorkload(
            fold_session_counts=(10, 20),
            holdout_session_count=15,
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "invalid_fold_session_counts"


def test_public_planning_text_nodes_reject_string_subclasses() -> None:
    class _TextSubclass(str):
        pass

    with pytest.raises(ExperimentPlanningError):
        BaselineDescriptor(
            descriptor_type=_TextSubclass("buy-and-hold"),
            payload={},
        )
    with pytest.raises(ExperimentPlanningError):
        BaselineDescriptor(
            descriptor_type="buy-and-hold",
            payload={_TextSubclass("benchmark"): "000300.SH"},
        )
    with pytest.raises(ExperimentPlanningError):
        ParameterAxis(name=_TextSubclass("node.rank"), values=(1,))


def test_public_planning_graph_rejects_dto_subclasses() -> None:
    class _BaselineSubclass(BaselineDescriptor):
        pass

    class _AxisSubclass(ParameterAxis):
        pass

    class _MatrixSubclass(CandidateMatrixSpec):
        pass

    class _WorkloadSubclass(ValidationWorkload):
        pass

    class _CostSubclass(ResourceCostModel):
        pass

    class _BudgetSubclass(ExperimentBudgetSpec):
        pass

    class _PlanningSubclass(ExperimentPlanningSpec):
        pass

    class _CandidateParameterSubclass(CandidateParameter):
        pass

    factories = (
        lambda: _BaselineSubclass("buy-and-hold", {}),
        lambda: _AxisSubclass("node.rank", (1,)),
        lambda: _MatrixSubclass(_baseline()),
        lambda: _WorkloadSubclass((1, 2, 3), 4),
        lambda: _CostSubclass(1, 1),
        lambda: _BudgetSubclass(2, 10, 100, 1000),
        lambda: _PlanningSubclass(
            matrix=CandidateMatrixSpec(baseline=_baseline()),
            track=ExperimentTrack.RESEARCH_ONLY,
            workload=ValidationWorkload((1, 2, 3), 4),
            cost_model=ResourceCostModel(1, 1),
            budget=ExperimentBudgetSpec(128, 10, 100, 1000),
        ),
        lambda: BinderCandidatePlan(
            ordinal=2,
            binder_parameters=(_CandidateParameterSubclass("node.rank", 1),),
        ),
    )

    for factory in factories:
        with pytest.raises(ExperimentPlanningError):
            factory()
