"""Governed registration bridge for novelty, attempts, and trial evidence."""

from __future__ import annotations

from collections.abc import Iterable

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.candidate_novelty import CandidateNoveltyEvidence
from ditto_analysis.experiments.promotion_models import PromotionObjective
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    SearchLedger,
    StatisticalTrial,
)
from ditto_analysis.experiments.trial_family import TrialFamilyDeclaration
from ditto_analysis.experiments.trial_ledger import (
    TrialLedger,
    TrialOutcome,
    build_trial_ledger,
)

__all__ = [
    "build_multiple_testing_ledger",
    "record_operational_attempt",
    "register_statistical_trial",
]


def _error(reason_code: str, message: str) -> ExperimentSpecError:
    return ExperimentSpecError(message, details={"reason_code": reason_code})


def _validate_bridge_identity(
    ledger: SearchLedger | None,
    trial: StatisticalTrial,
    family: TrialFamilyDeclaration,
) -> None:
    if (
        type(trial) is not StatisticalTrial
        or type(family) is not TrialFamilyDeclaration
    ):
        raise _error(
            "invalid_search_bridge_registration",
            "search registration requires typed trial and family values",
        )
    if trial.family_id != family.family_id:
        raise _error(
            "search_bridge_lineage_mismatch",
            "statistical trial cannot reset its family counter",
        )
    if ledger is not None and (
        type(ledger) is not SearchLedger
        or trial.lineage_root != ledger.lineage_root
        or trial.family_id != ledger.trial_family.family_id
        or family.family_id != ledger.trial_family.family_id
    ):
        raise _error(
            "search_bridge_lineage_mismatch",
            "statistical trial cannot reset lineage or family counter",
        )


def _require_novelty(
    trial: StatisticalTrial,
    evidence: CandidateNoveltyEvidence | None,
) -> None:
    if (
        type(evidence) is not CandidateNoveltyEvidence
        or not evidence.verify_integrity()
        or evidence.candidate_hash != trial.candidate_hash
        or evidence.validation_protocol_hash != trial.validation_protocol_hash
        or evidence.lineage_root != trial.lineage_root
    ):
        raise _error(
            "candidate_novelty_evidence_invalid",
            "candidate novelty evidence does not bind the statistical trial",
        )
    if not evidence.accepted:
        raise _error(
            "candidate_not_novel",
            "non-novel candidate cannot register another same-protocol trial",
        )


def register_statistical_trial(
    *,
    ledger: SearchLedger | None,
    trial: StatisticalTrial,
    trial_family: TrialFamilyDeclaration,
    novelty_evidence: CandidateNoveltyEvidence | None,
) -> SearchLedger:
    """Register one candidate/protocol comparison or replay it exactly."""
    _validate_bridge_identity(ledger, trial, trial_family)
    if ledger is None:
        _require_novelty(trial, novelty_evidence)
        return SearchLedger(
            lineage_root=trial.lineage_root,
            trial_family=trial_family,
            statistical_trials=(trial,),
            operational_attempts=(),
        )

    same_key = tuple(
        item
        for item in ledger.statistical_trials
        if item.statistical_key == trial.statistical_key
    )
    if same_key:
        if (
            len(same_key) == 1
            and same_key[0] == trial
            and ledger.trial_family == trial_family
        ):
            return ledger
        raise _error(
            "search_bridge_statistical_trial_conflict",
            "candidate/protocol identity is already bound to another logical trial",
        )
    changed_protocol = any(
        item.candidate_hash == trial.candidate_hash
        and item.validation_protocol_hash != trial.validation_protocol_hash
        for item in ledger.statistical_trials
    )
    if not changed_protocol:
        _require_novelty(trial, novelty_evidence)
    return SearchLedger(
        lineage_root=ledger.lineage_root,
        trial_family=trial_family,
        statistical_trials=(*ledger.statistical_trials, trial),
        operational_attempts=ledger.operational_attempts,
    )


def record_operational_attempt(
    ledger: SearchLedger,
    attempt: OperationalAttempt,
) -> SearchLedger:
    """Append or replay an execution attempt without changing trial count."""
    if type(ledger) is not SearchLedger or type(attempt) is not OperationalAttempt:
        raise _error(
            "invalid_search_bridge_attempt",
            "attempt registration requires typed ledger values",
        )
    existing = tuple(
        item
        for item in ledger.operational_attempts
        if item.attempt_id == attempt.attempt_id
    )
    if existing:
        if len(existing) == 1 and existing[0] == attempt:
            return ledger
        raise _error(
            "search_bridge_attempt_conflict",
            "attempt identity is already bound to another execution",
        )
    return SearchLedger(
        lineage_root=ledger.lineage_root,
        trial_family=ledger.trial_family,
        statistical_trials=ledger.statistical_trials,
        operational_attempts=(*ledger.operational_attempts, attempt),
    )


def build_multiple_testing_ledger(
    search_ledger: SearchLedger,
    objective: PromotionObjective,
    outcomes: Iterable[TrialOutcome],
) -> TrialLedger:
    """Reuse the existing DSR/PBO builder for one complete search family."""
    if (
        type(search_ledger) is not SearchLedger
        or type(objective) is not PromotionObjective
    ):
        raise _error(
            "search_bridge_multiple_testing_invalid",
            "multiple-testing bridge requires typed search and objective values",
        )
    registered = frozenset(
        trial.logical_trial for trial in search_ledger.statistical_trials
    )
    if search_ledger.trial_family != objective.trial_family or registered != frozenset(
        objective.trial_family.members
    ):
        raise _error(
            "search_bridge_trial_family_mismatch",
            "multiple-testing evidence requires the exact registered trial family",
        )
    return build_trial_ledger(objective, outcomes)
