"""R5 operational-attempt/statistical-trial ledger contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_analysis.errors import ExperimentSpecError
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


def _logical_trial(
    *,
    candidate_id: str = "candidate-1",
    ordinal: int = 1,
    parameter_hash: ContentHash | None = None,
) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        origin_experiment_id=ExperimentId("campaign-1"),
        candidate_id=CandidateId(candidate_id),
        ordinal=ordinal,
        parameter_hash=parameter_hash or _hash("a"),
        kind=TrialKind.CURRENT,
    )


def _statistical_trial(
    logical_trial: LogicalTrialIdentity | None = None,
) -> StatisticalTrial:
    return StatisticalTrial(
        logical_trial=logical_trial or _logical_trial(),
        candidate_hash=_hash("b"),
        validation_protocol_hash=_hash("c"),
        lineage_root=_hash("d"),
        family_id="family-1",
    )


def _family(*members: LogicalTrialIdentity) -> TrialFamilyDeclaration:
    return TrialFamilyDeclaration(family_id="family-1", members=members)


def test_retries_add_operational_attempts_but_count_one_statistical_trial() -> None:
    trial = _statistical_trial()
    first = OperationalAttempt(
        attempt_id=AttemptId("attempt-1"),
        logical_trial=trial.logical_trial,
        ordinal=1,
        parent_attempt_id=None,
        lineage_root=trial.lineage_root,
        family_id=trial.family_id,
    )
    retry = OperationalAttempt(
        attempt_id=AttemptId("attempt-2"),
        logical_trial=trial.logical_trial,
        ordinal=2,
        parent_attempt_id=first.attempt_id,
        lineage_root=trial.lineage_root,
        family_id=trial.family_id,
    )
    ledger = SearchLedger(
        lineage_root=trial.lineage_root,
        trial_family=_family(trial.logical_trial),
        statistical_trials=(trial,),
        operational_attempts=(retry, first),
    )

    assert ledger.statistical_trial_count == 1
    assert ledger.operational_attempt_count == 2
    assert tuple(item.ordinal for item in ledger.operational_attempts) == (1, 2)


def test_candidate_and_validation_protocol_are_the_statistical_identity() -> None:
    logical_one = _logical_trial()
    logical_two = _logical_trial(
        candidate_id="candidate-2",
        ordinal=2,
        parameter_hash=_hash("e"),
    )
    trial_one = _statistical_trial(logical_one)
    duplicate_key = replace(_statistical_trial(logical_two), candidate_hash=_hash("b"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=_hash("d"),
            trial_family=_family(logical_one, logical_two),
            statistical_trials=(trial_one, duplicate_key),
            operational_attempts=(),
        )

    assert exc_info.value.details["reason_code"] == "duplicate_statistical_trial"


def test_protocol_change_creates_a_distinct_statistical_trial() -> None:
    logical_one = _logical_trial()
    logical_two = _logical_trial(
        candidate_id="candidate-2",
        ordinal=2,
        parameter_hash=_hash("e"),
    )
    first = _statistical_trial(logical_one)
    changed_protocol = replace(
        _statistical_trial(logical_two),
        validation_protocol_hash=_hash("f"),
    )
    ledger = SearchLedger(
        lineage_root=_hash("d"),
        trial_family=_family(logical_one, logical_two),
        statistical_trials=(first, changed_protocol),
        operational_attempts=(),
    )

    assert ledger.statistical_trial_count == 2


def test_ledger_rejects_lineage_reset_on_fork_or_retry() -> None:
    trial = _statistical_trial()
    reset = OperationalAttempt(
        attempt_id=AttemptId("attempt-reset"),
        logical_trial=trial.logical_trial,
        ordinal=1,
        parent_attempt_id=None,
        lineage_root=_hash("e"),
        family_id=trial.family_id,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=trial.lineage_root,
            trial_family=_family(trial.logical_trial),
            statistical_trials=(trial,),
            operational_attempts=(reset,),
        )

    assert exc_info.value.details["reason_code"] == "search_lineage_mismatch"


def test_ledger_rejects_family_counter_reset() -> None:
    trial = _statistical_trial()

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=trial.lineage_root,
            trial_family=_family(trial.logical_trial),
            statistical_trials=(replace(trial, family_id="fresh-family"),),
            operational_attempts=(),
        )

    assert exc_info.value.details["reason_code"] == "search_family_mismatch"


def test_retry_must_reference_an_earlier_attempt_of_same_trial() -> None:
    trial = _statistical_trial()
    orphan = OperationalAttempt(
        attempt_id=AttemptId("attempt-2"),
        logical_trial=trial.logical_trial,
        ordinal=2,
        parent_attempt_id=AttemptId("missing-parent"),
        lineage_root=trial.lineage_root,
        family_id=trial.family_id,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=trial.lineage_root,
            trial_family=_family(trial.logical_trial),
            statistical_trials=(trial,),
            operational_attempts=(orphan,),
        )

    assert (
        exc_info.value.details["reason_code"] == "invalid_operational_attempt_lineage"
    )


def test_attempt_cannot_reference_an_undeclared_statistical_trial() -> None:
    declared = _statistical_trial()
    undeclared_trial = _logical_trial(candidate_id="candidate-2", ordinal=2)
    attempt = OperationalAttempt(
        attempt_id=AttemptId("attempt-1"),
        logical_trial=undeclared_trial,
        ordinal=1,
        parent_attempt_id=None,
        lineage_root=declared.lineage_root,
        family_id=declared.family_id,
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        SearchLedger(
            lineage_root=declared.lineage_root,
            trial_family=_family(declared.logical_trial),
            statistical_trials=(declared,),
            operational_attempts=(attempt,),
        )

    assert exc_info.value.details["reason_code"] == "undeclared_operational_attempt"
