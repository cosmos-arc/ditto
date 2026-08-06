"""Unit tests for immutable experiment launch specifications."""

from collections import UserList
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    ContentHash,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentFailurePolicy,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldProtocolSpec,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    SnapshotId,
    StrategyVersion,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)


class _CustomSequence(UserList[object]):
    """Non-built-in Sequence used to prove structural cycle handling."""


def _cyclic_dict() -> object:
    value: dict[str, object] = {}
    value["self"] = value
    return value


def _cyclic_list() -> object:
    value: list[object] = []
    value.append(value)
    return value


def _tuple_via_list_cycle() -> object:
    bridge: list[object] = []
    value = (bridge,)
    bridge.append(value)
    return value


def _cyclic_custom_sequence() -> object:
    value = _CustomSequence()
    value.append(value)
    return value


def _candidate(
    ordinal: int,
    *,
    baseline: bool = False,
    parameters: object | None = None,
) -> CandidateSpec:
    return CandidateSpec(
        candidate_id=CandidateId(f"candidate-{ordinal}"),
        ordinal=ordinal,
        is_baseline=baseline,
        # Launch candidates must have unique canonical parameter payloads,
        # including the explicit baseline.
        parameters={"candidate": ordinal} if parameters is None else parameters,
    )


def _objective(
    *,
    baseline_candidate_id: str = "candidate-1",
    candidates: tuple[CandidateSpec, ...] | None = None,
    parameter_hash_override: str | None = None,
    prior_members: tuple[LogicalTrialIdentity, ...] = (),
) -> PromotionObjective:
    current_candidates = candidates or (
        _candidate(1, baseline=True),
        _candidate(2),
    )
    current_members = tuple(
        LogicalTrialIdentity(
            ExperimentId("exp-1"),
            candidate.candidate_id,
            candidate.ordinal,
            ContentHash(
                parameter_hash_override
                if parameter_hash_override is not None and candidate.ordinal == 2
                else str(candidate.parameter_hash)
            ),
            TrialKind.CURRENT,
        )
        for candidate in current_candidates
    )
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=CandidateId(baseline_candidate_id),
        economic_rationale="Capture durable returns after costs.",
        trial_family=TrialFamilyDeclaration(
            "stock-selection-r3-v1",
            (*prior_members, *current_members),
        ),
    )


def _execution_bindings(
    candidates: tuple[CandidateSpec, ...],
) -> tuple[CandidateExecutionBinding, ...]:
    return tuple(
        CandidateExecutionBinding(
            candidate.candidate_id,
            candidate.ordinal,
            candidate.parameter_hash,
            ContentHash(f"{candidate.ordinal + 256:064x}"),
        )
        for candidate in candidates
    )


def _launch(
    *,
    candidates: object | None = None,
    created_at: datetime = NOW,
    desired_state: ExperimentDesiredState = ExperimentDesiredState.RUN,
    promotion_objective: PromotionObjective | None = None,
    execution_bindings: object | None = None,
) -> ExperimentLaunchSpec:
    resolved_candidates = (
        (_candidate(1, baseline=True), _candidate(2))
        if candidates is None
        else candidates
    )
    resolved_bindings = (
        _execution_bindings(
            cast("tuple[CandidateSpec, ...]", resolved_candidates)
            if type(resolved_candidates) is tuple
            else (_candidate(1, baseline=True), _candidate(2))
        )
        if execution_bindings is None
        else execution_bindings
    )
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId("exp-1"),
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=resolved_candidates,
        execution_bindings=resolved_bindings,
        promotion_objective=(
            _objective() if promotion_objective is None else promotion_objective
        ),
        fold_protocol=FoldProtocolSpec(
            protocol_id="r3-walk-forward",
            protocol_version=1,
            protocol_hash=ContentHash("b" * 64),
        ),
        seed=42,
        worker_count=2,
        failure_policy=ExperimentFailurePolicy.CONTINUE_CANDIDATE_FAILURES,
        budget=ExperimentBudget(candidate_limit=128, fold_run_limit=1024),
        desired_state=desired_state,
        created_at=created_at,
    )


def test_launch_spec_is_immutable_and_candidate_count_includes_baseline() -> None:
    spec = _launch()

    with pytest.raises(FrozenInstanceError):
        _set_attribute(spec, "seed", 7)

    assert spec.candidate_count == 2
    assert spec.baseline_candidate.candidate_id == CandidateId("candidate-1")
    assert spec.promotion_objective == _objective()


@pytest.mark.parametrize(
    ("objective", "reason_code"),
    [
        (
            _objective(baseline_candidate_id="candidate-2"),
            "promotion_baseline_candidate_mismatch",
        ),
        (
            _objective(parameter_hash_override="f" * 64),
            "promotion_current_trial_family_mismatch",
        ),
    ],
)
def test_launch_spec_binds_promotion_objective_to_the_complete_candidate_family(
    objective: PromotionObjective,
    reason_code: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(promotion_objective=objective)

    assert exc_info.value.details["reason_code"] == reason_code


def test_launch_spec_rejects_substituted_execution_binding() -> None:
    candidates = (_candidate(1, baseline=True), _candidate(2))
    bindings = _execution_bindings(candidates)
    substituted = (
        bindings[0],
        CandidateExecutionBinding(
            CandidateId("candidate-substituted"),
            2,
            bindings[1].parameter_hash,
            bindings[1].resolved_spec_hash,
        ),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates, execution_bindings=substituted)

    assert exc_info.value.details["reason_code"] == (
        "candidate_execution_binding_mismatch"
    )


def test_launch_spec_rejects_execution_parameter_hash_substitution() -> None:
    candidates = (_candidate(1, baseline=True), _candidate(2))
    bindings = _execution_bindings(candidates)
    substituted = (
        bindings[0],
        CandidateExecutionBinding(
            bindings[1].candidate_id,
            bindings[1].ordinal,
            ContentHash("f" * 64),
            bindings[1].resolved_spec_hash,
        ),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates, execution_bindings=substituted)

    assert exc_info.value.details["reason_code"] == (
        "candidate_execution_parameter_hash_mismatch"
    )


def test_launch_spec_allows_prior_trials_while_binding_current_candidates() -> None:
    prior = LogicalTrialIdentity(
        ExperimentId("exp-prior"),
        CandidateId("prior-candidate"),
        1,
        ContentHash("e" * 64),
        TrialKind.PRIOR,
    )

    spec = _launch(promotion_objective=_objective(prior_members=(prior,)))

    assert spec.promotion_objective.trial_family.prior_members == (prior,)
    assert len(spec.promotion_objective.trial_family.current_members) == 2


def test_launch_spec_revalidates_mutated_objective_before_persistence() -> None:
    objective = _objective()
    object.__setattr__(objective.primary, "direction", "maximize")

    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(promotion_objective=objective)

    assert exc_info.value.details["reason_code"] == "invalid_promotion_objective_graph"


@pytest.mark.parametrize(
    "desired_state",
    [ExperimentDesiredState.PAUSE, ExperimentDesiredState.CANCEL],
)
def test_launch_spec_requires_initial_run_intent_before_any_persistence(
    desired_state: ExperimentDesiredState,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(desired_state=desired_state)

    assert exc_info.value.details["reason_code"] == "initial_desired_state_must_be_run"


def test_launch_spec_defensively_freezes_nested_candidate_parameters() -> None:
    source = {"weights": [1.0, 2.0], "nested": {"window": 20}}
    candidate = _candidate(1, baseline=True, parameters=source)
    source["weights"].append(3.0)
    source["nested"]["window"] = 30

    assert candidate.parameters["weights"] == (1.0, 2.0)
    assert candidate.parameters["nested"]["window"] == 20
    with pytest.raises(TypeError):
        cast("dict[str, object]", candidate.parameters)["new"] = 1


@pytest.mark.parametrize(
    "value_factory",
    [
        _cyclic_dict,
        _cyclic_list,
        _tuple_via_list_cycle,
        _cyclic_custom_sequence,
    ],
)
def test_candidate_parameters_reject_cyclic_containers(
    value_factory: Callable[[], object],
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _candidate(1, baseline=True, parameters={"cycle": value_factory()})

    assert exc_info.value.details["reason_code"] == "cyclic_experiment_value"


def test_candidate_parameters_allow_shared_non_cyclic_containers() -> None:
    shared = [1, 2]

    candidate = _candidate(
        1,
        baseline=True,
        parameters={"left": shared, "right": shared},
    )

    assert candidate.parameters["left"] == (1, 2)
    assert candidate.parameters["right"] == (1, 2)


def test_launch_and_record_share_utc_validation_reason() -> None:
    naive = datetime(2026, 7, 19, 4, 0)

    with pytest.raises(ExperimentSpecError) as launch_exc:
        _launch(created_at=naive)
    with pytest.raises(ExperimentSpecError) as record_exc:
        ExperimentRecord(
            experiment_id=ExperimentId("exp-1"),
            status=ExperimentStatus.DRAFT,
            desired_state=ExperimentDesiredState.RUN,
            stage=ExperimentStage.PREFLIGHT,
            created_at=naive,
        )

    expected = {"reason_code": "datetime_not_utc", "field": "created_at"}
    assert launch_exc.value.details == expected
    assert record_exc.value.details == expected


@pytest.mark.parametrize(
    "candidates",
    [
        "candidate-1",
        {1},
        iter((_candidate(1, baseline=True),)),
    ],
)
def test_launch_spec_rejects_fake_or_unordered_sequences(candidates: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates)

    assert exc_info.value.details["reason_code"] == "invalid_candidate_sequence"


@pytest.mark.parametrize("ordinal", [True, 0, -1, 1.0])
def test_candidate_ordinal_must_be_a_positive_real_integer(ordinal: object) -> None:
    with pytest.raises(ExperimentSpecError):
        _candidate(cast("int", ordinal))


def test_candidate_ordinals_are_unique_contiguous_and_stable() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=(_candidate(1, baseline=True), _candidate(3)))

    assert exc_info.value.details["reason_code"] == "candidate_ordinals_not_contiguous"


@pytest.mark.parametrize(
    ("candidates", "reason_code"),
    [
        ((_candidate(1),), "baseline_candidate_missing"),
        (
            (_candidate(1, baseline=True), _candidate(2, baseline=True)),
            "multiple_baseline_candidates",
        ),
    ],
)
def test_launch_spec_requires_exactly_one_explicit_baseline(
    candidates: tuple[CandidateSpec, ...], reason_code: str
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates)

    assert exc_info.value.details["reason_code"] == reason_code


def test_candidate_count_must_not_exceed_128() -> None:
    candidates = tuple(_candidate(i, baseline=i == 1) for i in range(1, 130))

    with pytest.raises(ExperimentSpecError) as exc_info:
        _launch(candidates=candidates)

    assert exc_info.value.details["reason_code"] == "candidate_limit_exceeded"


def test_candidate_parameters_preserve_boolean_as_an_exact_scalar_type() -> None:
    candidate = _candidate(
        1,
        baseline=True,
        parameters={"enabled": True, "nested": {"disabled": False}},
    )

    assert candidate.parameters["enabled"] is True
    assert candidate.parameters["nested"]["disabled"] is False


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_deterministic_numeric_inputs_reject_non_finite(value: object) -> None:
    with pytest.raises(ExperimentSpecError):
        _launch(candidates=(_candidate(1, baseline=True, parameters={"x": value}),))


def _set_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)
