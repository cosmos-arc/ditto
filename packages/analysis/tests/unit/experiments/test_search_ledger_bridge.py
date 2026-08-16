"""Governed novelty and multiple-testing registration over SearchLedger."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.candidate_novelty import (
    CandidateNoveltyEvidence,
    CandidateNoveltyPolicy,
    CandidateOutputProfile,
    evaluate_candidate_novelty,
)
from ditto_analysis.experiments.metric_schema import (
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
)
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    StatisticalTrial,
)
from ditto_analysis.experiments.search_ledger_bridge import (
    build_multiple_testing_ledger,
    record_operational_attempt,
    register_statistical_trial,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    MetricEvidenceLineage,
    ObjectiveMetric,
    PromotionObjective,
    TrialOutcome,
    TrialStatus,
    build_trial_ledger,
)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _logical(candidate: str, ordinal: int) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        origin_experiment_id=ExperimentId("campaign-novelty"),
        candidate_id=CandidateId(candidate),
        ordinal=ordinal,
        parameter_hash=ContentHash(f"{ordinal:064x}"),
        kind=TrialKind.CURRENT,
    )


def _trial(
    logical: LogicalTrialIdentity,
    *,
    candidate_hash: ContentHash,
    protocol_hash: ContentHash = ContentHash("c" * 64),
) -> StatisticalTrial:
    return StatisticalTrial(
        logical_trial=logical,
        candidate_hash=candidate_hash,
        validation_protocol_hash=protocol_hash,
        lineage_root=_hash("d"),
        family_id="family-novelty",
    )


def _profile(
    *,
    candidate_hash: ContentHash,
    ast_hash: ContentHash,
    outputs: tuple[float, ...],
) -> CandidateOutputProfile:
    return CandidateOutputProfile(
        candidate_hash=candidate_hash,
        canonical_ast_hash=ast_hash,
        validation_protocol_hash=_hash("c"),
        lineage_root=_hash("d"),
        observation_grid_hash=_hash("e"),
        outputs=outputs,
    )


def _accepted(
    profile: CandidateOutputProfile,
    *references: CandidateOutputProfile,
) -> CandidateNoveltyEvidence:
    return evaluate_candidate_novelty(
        profile,
        references=references,
        policy=CandidateNoveltyPolicy(max_abs_output_correlation=0.99),
    )


def test_retry_and_recovery_attempts_do_not_increment_statistical_trials() -> None:
    logical = _logical("candidate-1", 1)
    profile = _profile(
        candidate_hash=_hash("a"),
        ast_hash=_hash("1"),
        outputs=(1.0, -1.0, 1.0, -1.0),
    )
    family = TrialFamilyDeclaration("family-novelty", (logical,))
    ledger = register_statistical_trial(
        ledger=None,
        trial=_trial(logical, candidate_hash=profile.candidate_hash),
        trial_family=family,
        novelty_evidence=_accepted(profile),
    )
    first = OperationalAttempt(
        attempt_id=AttemptId("attempt-1"),
        logical_trial=logical,
        ordinal=1,
        parent_attempt_id=None,
        lineage_root=_hash("d"),
        family_id="family-novelty",
    )
    retry = replace(
        first,
        attempt_id=AttemptId("attempt-2"),
        ordinal=2,
        parent_attempt_id=first.attempt_id,
    )

    ledger = record_operational_attempt(ledger, first)
    ledger = record_operational_attempt(ledger, retry)

    assert ledger.statistical_trial_count == 1
    assert ledger.operational_attempt_count == 2


def test_non_novel_candidate_cannot_register_same_protocol_trial() -> None:
    first_logical = _logical("candidate-1", 1)
    second_logical = _logical("candidate-2", 2)
    first_profile = _profile(
        candidate_hash=_hash("a"),
        ast_hash=_hash("1"),
        outputs=(1.0, 2.0, 3.0, 4.0),
    )
    duplicate = _profile(
        candidate_hash=_hash("b"),
        ast_hash=_hash("2"),
        outputs=(2.0, 4.0, 6.0, 8.0),
    )
    first_family = TrialFamilyDeclaration("family-novelty", (first_logical,))
    ledger = register_statistical_trial(
        ledger=None,
        trial=_trial(first_logical, candidate_hash=first_profile.candidate_hash),
        trial_family=first_family,
        novelty_evidence=_accepted(first_profile),
    )
    expanded_family = TrialFamilyDeclaration(
        "family-novelty", (first_logical, second_logical)
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        register_statistical_trial(
            ledger=ledger,
            trial=_trial(second_logical, candidate_hash=duplicate.candidate_hash),
            trial_family=expanded_family,
            novelty_evidence=_accepted(duplicate, first_profile),
        )

    assert exc_info.value.details["reason_code"] == "candidate_not_novel"


def test_protocol_change_is_a_new_trial_even_for_same_candidate_content() -> None:
    first_logical = _logical("candidate-1", 1)
    second_logical = _logical("candidate-2", 2)
    candidate_hash = _hash("a")
    first_family = TrialFamilyDeclaration("family-novelty", (first_logical,))
    ledger = register_statistical_trial(
        ledger=None,
        trial=_trial(first_logical, candidate_hash=candidate_hash),
        trial_family=first_family,
        novelty_evidence=_accepted(
            _profile(
                candidate_hash=candidate_hash,
                ast_hash=_hash("1"),
                outputs=(1.0, -1.0, 1.0, -1.0),
            )
        ),
    )
    expanded_family = TrialFamilyDeclaration(
        "family-novelty", (first_logical, second_logical)
    )

    changed = register_statistical_trial(
        ledger=ledger,
        trial=_trial(
            second_logical,
            candidate_hash=candidate_hash,
            protocol_hash=_hash("f"),
        ),
        trial_family=expanded_family,
        novelty_evidence=None,
    )

    assert changed.statistical_trial_count == 2
    assert {item.validation_protocol_hash for item in changed.statistical_trials} == {
        _hash("c"),
        _hash("f"),
    }


def test_exact_registration_replay_does_not_increment_counter() -> None:
    logical = _logical("candidate-1", 1)
    profile = _profile(
        candidate_hash=_hash("a"),
        ast_hash=_hash("1"),
        outputs=(1.0, -1.0, 1.0, -1.0),
    )
    trial = _trial(logical, candidate_hash=profile.candidate_hash)
    family = TrialFamilyDeclaration("family-novelty", (logical,))
    ledger = register_statistical_trial(
        ledger=None,
        trial=trial,
        trial_family=family,
        novelty_evidence=_accepted(profile),
    )

    replay = register_statistical_trial(
        ledger=ledger,
        trial=trial,
        trial_family=family,
        novelty_evidence=_accepted(profile),
    )

    assert replay == ledger
    assert replay.statistical_trial_count == 1


def test_fork_cannot_replace_lineage_root_or_family_counter() -> None:
    logical = _logical("candidate-1", 1)
    profile = _profile(
        candidate_hash=_hash("a"),
        ast_hash=_hash("1"),
        outputs=(1.0, -1.0, 1.0, -1.0),
    )
    family = TrialFamilyDeclaration("family-novelty", (logical,))
    ledger = register_statistical_trial(
        ledger=None,
        trial=_trial(logical, candidate_hash=profile.candidate_hash),
        trial_family=family,
        novelty_evidence=_accepted(profile),
    )
    reset = replace(
        ledger.statistical_trials[0],
        lineage_root=_hash("f"),
        family_id="fresh-family",
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        register_statistical_trial(
            ledger=ledger,
            trial=reset,
            trial_family=TrialFamilyDeclaration("fresh-family", (logical,)),
            novelty_evidence=_accepted(profile),
        )

    assert exc_info.value.details["reason_code"] == "search_bridge_lineage_mismatch"


def test_multiple_testing_bridge_reuses_existing_dsr_and_pbo_ledger() -> None:
    logical = _logical("candidate-1", 1)
    profile = _profile(
        candidate_hash=_hash("a"),
        ast_hash=_hash("1"),
        outputs=(1.0, -1.0, 1.0, -1.0),
    )
    family = TrialFamilyDeclaration("family-novelty", (logical,))
    search_ledger = register_statistical_trial(
        ledger=None,
        trial=_trial(logical, candidate_hash=profile.candidate_hash),
        trial_family=family,
        novelty_evidence=_accepted(profile),
    )
    objective = PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(),
        tie_break_order=(),
        baseline_candidate_id=logical.candidate_id,
        economic_rationale="Test one governed search family.",
        trial_family=family,
    )
    net_return = ResearchMetricValue(ResearchMetricId.NET_RETURN, 0.1)
    outcome = TrialOutcome(
        trial=logical,
        status=TrialStatus.COMPLETED,
        metrics={ResearchMetricId.NET_RETURN: net_return},
        holdout_metrics={},
        source_projection_hash=_hash("f"),
        metric_evidence={
            ResearchMetricId.NET_RETURN: MetricEvidenceLineage(
                ("artifact://net-return",),
                (_hash("9"),),
            )
        },
    )

    bridged = build_multiple_testing_ledger(search_ledger, objective, (outcome,))

    assert bridged == build_trial_ledger(objective, (outcome,))
    assert bridged.deflated_sharpe.method
    assert bridged.pbo.method
