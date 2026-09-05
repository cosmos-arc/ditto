"""Nominal identity and lineage edges for the campaign search ledger."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import search_ledger
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
)
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    SearchLedger,
    StatisticalTrial,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _logical(candidate: str = "candidate-1", ordinal: int = 1) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        ExperimentId("experiment-1"),
        CandidateId(candidate),
        ordinal,
        _hash(str(ordinal)),
        TrialKind.CURRENT,
    )


def _trial(
    logical: LogicalTrialIdentity | None = None,
    *,
    candidate_hash: ContentHash | None = None,
    protocol_hash: ContentHash | None = None,
) -> StatisticalTrial:
    return StatisticalTrial(
        logical_trial=_logical() if logical is None else logical,
        candidate_hash=_hash("a") if candidate_hash is None else candidate_hash,
        validation_protocol_hash=(
            _hash("b") if protocol_hash is None else protocol_hash
        ),
        lineage_root=_hash("c"),
        family_id="family-1",
    )


def _attempt(
    logical: LogicalTrialIdentity,
    *,
    attempt_id: str = "attempt-1",
    ordinal: int = 1,
    parent: AttemptId | None = None,
) -> OperationalAttempt:
    return OperationalAttempt(
        attempt_id=AttemptId(attempt_id),
        logical_trial=logical,
        ordinal=ordinal,
        parent_attempt_id=parent,
        lineage_root=_hash("c"),
        family_id="family-1",
    )


def _family(*members: LogicalTrialIdentity) -> TrialFamilyDeclaration:
    return TrialFamilyDeclaration("family-1", members)


def _reason(exc_info: pytest.ExceptionInfo[ExperimentSpecError]) -> object:
    return exc_info.value.details["reason_code"]


def test_family_id_requires_canonical_unpadded_text() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        search_ledger._family_id(" family-1")
    assert _reason(exc_info) == "invalid_search_family_id"


def test_statistical_trial_requires_exact_contract_nodes() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_trial(), candidate_hash=cast("ContentHash", "a" * 64))
    assert _reason(exc_info) == "invalid_statistical_trial"


def test_operational_attempt_rejects_untyped_identity_and_ordinal() -> None:
    logical = _logical()
    attempt = _attempt(logical)
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(attempt, attempt_id=cast("AttemptId", "attempt-1"))
    assert _reason(exc_info) == "invalid_operational_attempt"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(attempt, ordinal=0)
    assert _reason(exc_info) == "invalid_operational_attempt"


def test_operational_attempt_rejects_untyped_and_self_parent() -> None:
    logical = _logical()
    attempt = _attempt(logical)
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(attempt, parent_attempt_id=cast("AttemptId", "parent"))
    assert _reason(exc_info) == "invalid_operational_attempt"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(attempt, parent_attempt_id=attempt.attempt_id)
    assert _reason(exc_info) == "invalid_operational_attempt_lineage"


def test_ledger_sequence_freezers_reject_strings_and_untyped_members() -> None:
    for value in ("trial", (object(),)):
        with pytest.raises(ExperimentSpecError) as exc_info:
            search_ledger._freeze_trials(value)
        assert _reason(exc_info) == "invalid_statistical_trial_sequence"

    for value in ("attempt", (object(),)):
        with pytest.raises(ExperimentSpecError) as exc_info:
            search_ledger._freeze_attempts(value)
        assert _reason(exc_info) == "invalid_operational_attempt_sequence"


def test_search_ledger_requires_exact_root_and_family_contracts() -> None:
    logical = _logical()
    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=cast("ContentHash", "c" * 64),
            trial_family=_family(logical),
            statistical_trials=(),
            operational_attempts=(),
        )
    assert _reason(exc_info) == "invalid_search_lineage"

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("c"),
            trial_family=cast("TrialFamilyDeclaration", object()),
            statistical_trials=(),
            operational_attempts=(),
        )
    assert _reason(exc_info) == "invalid_search_trial_family"


def test_one_logical_trial_cannot_reset_its_statistical_identity() -> None:
    logical = _logical()
    first = _trial(logical)
    second = _trial(
        logical,
        candidate_hash=_hash("d"),
        protocol_hash=_hash("e"),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("c"),
            trial_family=_family(logical),
            statistical_trials=(first, second),
            operational_attempts=(),
        )

    assert _reason(exc_info) == "duplicate_logical_search_trial"


def test_statistical_trials_must_belong_to_declared_family() -> None:
    declared = _logical()
    undeclared = _logical("candidate-2", 2)

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("c"),
            trial_family=_family(declared),
            statistical_trials=(_trial(undeclared),),
            operational_attempts=(),
        )

    assert _reason(exc_info) == "search_trial_family_mismatch"


def test_operational_attempt_ids_are_globally_unique_in_ledger() -> None:
    first_logical = _logical()
    second_logical = _logical("candidate-2", 2)
    first_trial = _trial(first_logical)
    second_trial = _trial(
        second_logical,
        candidate_hash=_hash("d"),
        protocol_hash=_hash("e"),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("c"),
            trial_family=_family(first_logical, second_logical),
            statistical_trials=(first_trial, second_trial),
            operational_attempts=(
                _attempt(first_logical),
                _attempt(second_logical),
            ),
        )

    assert _reason(exc_info) == "duplicate_operational_attempt"


def test_first_operational_attempt_cannot_claim_a_parent() -> None:
    logical = _logical()
    trial = _trial(logical)
    attempt = _attempt(
        logical,
        parent=AttemptId("unrelated-parent"),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("c"),
            trial_family=_family(logical),
            statistical_trials=(trial,),
            operational_attempts=(attempt,),
        )

    assert _reason(exc_info) == "invalid_operational_attempt_lineage"
