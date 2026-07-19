"""Unit tests for immutable experiment launch specifications."""

from collections import UserList
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
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
    SnapshotId,
    StrategyVersion,
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


def _launch(
    *,
    candidates: object | None = None,
    created_at: datetime = NOW,
) -> ExperimentLaunchSpec:
    return ExperimentLaunchSpec(
        experiment_id=ExperimentId("exp-1"),
        strategy_version=StrategyVersion("stock-selection@3"),
        strategy_spec_hash=ContentHash("a" * 64),
        snapshot_id=SnapshotId("snapshot-certified-1"),
        candidates=(
            (_candidate(1, baseline=True), _candidate(2))
            if candidates is None
            else candidates
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
        desired_state=ExperimentDesiredState.RUN,
        created_at=created_at,
    )


def test_launch_spec_is_immutable_and_candidate_count_includes_baseline() -> None:
    spec = _launch()

    with pytest.raises(FrozenInstanceError):
        _set_attribute(spec, "seed", 7)

    assert spec.candidate_count == 2
    assert spec.baseline_candidate.candidate_id == CandidateId("candidate-1")


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


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_deterministic_numeric_inputs_reject_bool_and_non_finite(value: object) -> None:
    with pytest.raises(ExperimentSpecError):
        _launch(candidates=(_candidate(1, baseline=True, parameters={"x": value}),))


def _set_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)
