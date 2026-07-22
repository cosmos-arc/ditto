"""Unit tests for immutable logical trial-family declarations."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import CandidateId, ContentHash, ExperimentId
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)


def _trial(
    ordinal: int,
    *,
    origin: str = "experiment-current",
    candidate: str | None = None,
    kind: TrialKind = TrialKind.CURRENT,
    parameter_hash: str | None = None,
) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        origin_experiment_id=ExperimentId(origin),
        candidate_id=CandidateId(candidate or f"candidate-{ordinal}"),
        ordinal=ordinal,
        parameter_hash=ContentHash(parameter_hash or f"{ordinal:x}" * 64),
        kind=kind,
    )


def test_trial_family_canonically_sorts_prior_then_current_members() -> None:
    prior = _trial(
        2,
        origin="experiment-prior",
        candidate="prior-2",
        kind=TrialKind.PRIOR,
    )
    current_two = _trial(2)
    current_one = _trial(1)

    declaration = TrialFamilyDeclaration(
        family_id="stock-selection-r3-v1",
        members=(current_two, prior, current_one),
    )

    assert declaration.members == (prior, current_one, current_two)
    assert declaration.prior_members == (prior,)
    assert declaration.current_members == (current_one, current_two)
    assert declaration.declared_trial_count == 3


def test_trial_family_rejects_a_duplicate_logical_trial() -> None:
    member = _trial(1)

    with pytest.raises(ExperimentSpecError) as exc_info:
        TrialFamilyDeclaration("stock-selection-r3-v1", (member, member))

    assert exc_info.value.details["reason_code"] == "duplicate_logical_trial"


def test_trial_family_rejects_kind_flip_double_count_for_one_identity() -> None:
    current = _trial(1)
    prior = LogicalTrialIdentity(
        current.origin_experiment_id,
        current.candidate_id,
        current.ordinal,
        current.parameter_hash,
        TrialKind.PRIOR,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        TrialFamilyDeclaration("stock-selection-r3-v1", (prior, current))

    assert exc_info.value.details["reason_code"] == "duplicate_logical_trial"


@pytest.mark.parametrize(
    ("replacement", "reason_code"),
    [
        (
            _trial(2, candidate="candidate-1"),
            "ambiguous_trial_candidate_identity",
        ),
        (
            _trial(1, candidate="candidate-1", parameter_hash="f" * 64),
            "ambiguous_trial_candidate_identity",
        ),
        (
            _trial(1, candidate="candidate-other", parameter_hash="e" * 64),
            "ambiguous_trial_ordinal",
        ),
    ],
)
def test_trial_family_enforces_origin_local_candidate_and_ordinal_bijection(
    replacement: LogicalTrialIdentity,
    reason_code: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        TrialFamilyDeclaration(
            "stock-selection-r3-v1",
            (_trial(1), replacement),
        )

    assert exc_info.value.details["reason_code"] == reason_code


def test_trial_family_identity_has_no_execution_attempt_dimension() -> None:
    member = _trial(1)

    assert tuple(member.__dataclass_fields__) == (
        "origin_experiment_id",
        "candidate_id",
        "ordinal",
        "parameter_hash",
        "kind",
    )
    with pytest.raises(FrozenInstanceError):
        member.ordinal = 2


@pytest.mark.parametrize("ordinal", [0, -1, True])
def test_logical_trial_ordinal_must_be_a_positive_integer(ordinal: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        LogicalTrialIdentity(
            origin_experiment_id=ExperimentId("experiment-current"),
            candidate_id=CandidateId("candidate-1"),
            ordinal=cast("int", ordinal),
            parameter_hash=ContentHash("a" * 64),
            kind=TrialKind.CURRENT,
        )

    assert exc_info.value.details["reason_code"] == "invalid_logical_trial_ordinal"
