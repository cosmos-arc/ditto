"""Pure campaign search ledger separating trials from execution attempts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import AttemptId, ContentHash
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
)

__all__ = [
    "OperationalAttempt",
    "SearchLedger",
    "StatisticalTrial",
]


def _ledger_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _family_id(value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _ledger_error(
            "family_id must be a non-empty unpadded string",
            "invalid_search_family_id",
        )
    return value


@dataclass(frozen=True, slots=True)
class StatisticalTrial:
    """One unique candidate-content and validation-protocol comparison."""

    logical_trial: LogicalTrialIdentity
    candidate_hash: ContentHash
    validation_protocol_hash: ContentHash
    lineage_root: ContentHash
    family_id: str

    def __post_init__(self) -> None:
        """Bind the statistical key to the existing logical trial identity."""
        for value, expected, field in (
            (self.logical_trial, LogicalTrialIdentity, "logical_trial"),
            (self.candidate_hash, ContentHash, "candidate_hash"),
            (
                self.validation_protocol_hash,
                ContentHash,
                "validation_protocol_hash",
            ),
            (self.lineage_root, ContentHash, "lineage_root"),
        ):
            if type(value) is not expected:
                raise _ledger_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_statistical_trial",
                    field=field,
                )
        _family_id(self.family_id)

    @property
    def statistical_key(self) -> tuple[ContentHash, ContentHash]:
        """Return the exact multiple-testing identity."""
        return (self.candidate_hash, self.validation_protocol_hash)


@dataclass(frozen=True, slots=True)
class OperationalAttempt:
    """One retry/recovery execution of an immutable logical trial."""

    attempt_id: AttemptId
    logical_trial: LogicalTrialIdentity
    ordinal: int
    parent_attempt_id: AttemptId | None
    lineage_root: ContentHash
    family_id: str

    def __post_init__(self) -> None:
        """Require nominal identities and explicit attempt lineage."""
        for value, expected, field in (
            (self.attempt_id, AttemptId, "attempt_id"),
            (self.logical_trial, LogicalTrialIdentity, "logical_trial"),
            (self.lineage_root, ContentHash, "lineage_root"),
        ):
            if type(value) is not expected:
                raise _ledger_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_operational_attempt",
                    field=field,
                )
        if type(self.ordinal) is not int or self.ordinal <= 0:
            raise _ledger_error(
                "attempt ordinal must be a positive integer",
                "invalid_operational_attempt",
                field="ordinal",
            )
        if (
            self.parent_attempt_id is not None
            and type(self.parent_attempt_id) is not AttemptId
        ):
            raise _ledger_error(
                "parent_attempt_id must be AttemptId when present",
                "invalid_operational_attempt",
                field="parent_attempt_id",
            )
        if self.parent_attempt_id == self.attempt_id:
            raise _ledger_error(
                "attempt cannot be its own parent",
                "invalid_operational_attempt_lineage",
            )
        _family_id(self.family_id)


def _freeze_trials(value: object) -> tuple[StatisticalTrial, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _ledger_error(
            "statistical_trials must be an ordered sequence",
            "invalid_statistical_trial_sequence",
        )
    raw = tuple(cast("Sequence[object]", value))
    if any(type(item) is not StatisticalTrial for item in raw):
        raise _ledger_error(
            "statistical_trials must contain StatisticalTrial values",
            "invalid_statistical_trial_sequence",
        )
    typed = cast("tuple[StatisticalTrial, ...]", raw)
    return tuple(
        sorted(
            typed,
            key=lambda item: (
                item.logical_trial.ordinal,
                str(item.logical_trial.candidate_id),
                str(item.validation_protocol_hash),
            ),
        )
    )


def _freeze_attempts(value: object) -> tuple[OperationalAttempt, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _ledger_error(
            "operational_attempts must be an ordered sequence",
            "invalid_operational_attempt_sequence",
        )
    raw = tuple(cast("Sequence[object]", value))
    if any(type(item) is not OperationalAttempt for item in raw):
        raise _ledger_error(
            "operational_attempts must contain OperationalAttempt values",
            "invalid_operational_attempt_sequence",
        )
    typed = cast("tuple[OperationalAttempt, ...]", raw)
    return tuple(
        sorted(
            typed,
            key=lambda item: (
                item.logical_trial.ordinal,
                item.ordinal,
                str(item.attempt_id),
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class SearchLedger:
    """One lineage-rooted projection of search trials and their attempts."""

    lineage_root: ContentHash
    trial_family: TrialFamilyDeclaration
    statistical_trials: Sequence[StatisticalTrial]
    operational_attempts: Sequence[OperationalAttempt]

    def __post_init__(self) -> None:
        """Prevent retry, fork, and protocol changes from resetting trial counts."""
        if type(self.lineage_root) is not ContentHash:
            raise _ledger_error(
                "lineage_root must be ContentHash",
                "invalid_search_lineage",
            )
        if type(self.trial_family) is not TrialFamilyDeclaration:
            raise _ledger_error(
                "trial_family must reuse TrialFamilyDeclaration",
                "invalid_search_trial_family",
            )
        trials = _freeze_trials(self.statistical_trials)
        attempts = _freeze_attempts(self.operational_attempts)
        object.__setattr__(self, "statistical_trials", trials)
        object.__setattr__(self, "operational_attempts", attempts)

        if any(item.lineage_root != self.lineage_root for item in (*trials, *attempts)):
            raise _ledger_error(
                "all search records must retain the ledger lineage root",
                "search_lineage_mismatch",
            )
        if any(
            item.family_id != self.trial_family.family_id
            for item in (*trials, *attempts)
        ):
            raise _ledger_error(
                "all search records must retain the declared family counter",
                "search_family_mismatch",
            )
        statistical_keys = tuple(item.statistical_key for item in trials)
        if len(set(statistical_keys)) != len(statistical_keys):
            raise _ledger_error(
                "candidate_hash and validation_protocol_hash must be unique",
                "duplicate_statistical_trial",
            )
        logical_trials = tuple(item.logical_trial for item in trials)
        if len(set(logical_trials)) != len(logical_trials):
            raise _ledger_error(
                "one logical trial cannot represent multiple statistical trials",
                "duplicate_logical_search_trial",
            )
        declared = frozenset(self.trial_family.members)
        if not frozenset(logical_trials).issubset(declared):
            raise _ledger_error(
                "statistical trials must belong to the declared trial family",
                "search_trial_family_mismatch",
            )
        attempt_ids = tuple(item.attempt_id for item in attempts)
        if len(set(attempt_ids)) != len(attempt_ids):
            raise _ledger_error(
                "operational attempt identities must be unique",
                "duplicate_operational_attempt",
            )
        statistical_identities = frozenset(logical_trials)
        if any(item.logical_trial not in statistical_identities for item in attempts):
            raise _ledger_error(
                "attempt must reference a registered statistical trial",
                "undeclared_operational_attempt",
            )
        self._validate_attempt_lineage(attempts)

    @staticmethod
    def _validate_attempt_lineage(
        attempts: tuple[OperationalAttempt, ...],
    ) -> None:
        by_trial: dict[LogicalTrialIdentity, list[OperationalAttempt]] = {}
        for attempt in attempts:
            by_trial.setdefault(attempt.logical_trial, []).append(attempt)
        for trial_attempts in by_trial.values():
            ordered = sorted(trial_attempts, key=lambda item: item.ordinal)
            if tuple(item.ordinal for item in ordered) != tuple(
                range(1, len(ordered) + 1)
            ):
                raise _ledger_error(
                    "attempt ordinals must be contiguous from one per trial",
                    "invalid_operational_attempt_lineage",
                )
            known: set[AttemptId] = set()
            for attempt in ordered:
                expected_parent = None if attempt.ordinal == 1 else known
                if (
                    expected_parent is None and attempt.parent_attempt_id is not None
                ) or (
                    expected_parent is not None
                    and attempt.parent_attempt_id not in expected_parent
                ):
                    raise _ledger_error(
                        "retry must reference an earlier attempt of the same trial",
                        "invalid_operational_attempt_lineage",
                    )
                known.add(attempt.attempt_id)

    @property
    def statistical_trial_count(self) -> int:
        """Count candidate/protocol comparisons, independent of retries."""
        return len(self.statistical_trials)

    @property
    def operational_attempt_count(self) -> int:
        """Count actual execution attempts."""
        return len(self.operational_attempts)
