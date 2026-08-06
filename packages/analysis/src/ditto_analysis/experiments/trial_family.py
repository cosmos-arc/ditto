"""Immutable declarations for logical multiple-testing trial families."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
)

__all__ = [
    "LogicalTrialIdentity",
    "TrialFamilyDeclaration",
    "TrialKind",
]


def _family_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


class TrialKind(StrEnum):
    """Whether a declared logical trial predates or belongs to this launch."""

    PRIOR = "prior"
    CURRENT = "current"


@dataclass(frozen=True, slots=True)
class LogicalTrialIdentity:
    """Attempt-independent identity of one member of a trial family."""

    origin_experiment_id: ExperimentId
    candidate_id: CandidateId
    ordinal: int
    parameter_hash: ContentHash
    kind: TrialKind

    def __post_init__(self) -> None:
        """Validate every nominal identity and the positive family ordinal."""
        typed_fields = (
            (self.origin_experiment_id, ExperimentId, "origin_experiment_id"),
            (self.candidate_id, CandidateId, "candidate_id"),
            (self.parameter_hash, ContentHash, "parameter_hash"),
            (self.kind, TrialKind, "kind"),
        )
        for value, expected, field_name in typed_fields:
            if not isinstance(cast("object", value), expected):
                raise _family_error(
                    f"{field_name} must be {expected.__name__}",
                    "invalid_logical_trial_identity",
                    field=field_name,
                )
        if type(self.ordinal) is not int or self.ordinal <= 0:
            raise _family_error(
                "logical trial ordinal must be a positive integer",
                "invalid_logical_trial_ordinal",
                ordinal=self.ordinal,
            )

    @property
    def identity_key(
        self,
    ) -> tuple[ExperimentId, CandidateId, int, ContentHash]:
        """Return logical identity without the prior/current classification."""
        return (
            self.origin_experiment_id,
            self.candidate_id,
            self.ordinal,
            self.parameter_hash,
        )


def _member_sort_key(
    member: LogicalTrialIdentity,
) -> tuple[int, str, int, str, str]:
    kind_rank = 0 if member.kind is TrialKind.PRIOR else 1
    return (
        kind_rank,
        str(member.origin_experiment_id),
        member.ordinal,
        str(member.candidate_id),
        str(member.parameter_hash),
    )


@dataclass(frozen=True, slots=True)
class TrialFamilyDeclaration:
    """Canonical, complete set of logical trials counted for multiplicity."""

    family_id: str
    members: Sequence[LogicalTrialIdentity]

    def __post_init__(self) -> None:
        """Defensively freeze and canonically order the exact declaration."""
        if (
            type(self.family_id) is not str
            or not self.family_id.strip()
            or self.family_id != self.family_id.strip()
        ):
            raise _family_error(
                "trial family id must be a non-empty unpadded string",
                "invalid_trial_family_id",
            )
        raw_member_value = cast("object", self.members)
        if not isinstance(raw_member_value, Sequence) or isinstance(
            raw_member_value, (str, bytes, bytearray)
        ):
            raise _family_error(
                "trial family members must be an ordered sequence",
                "invalid_trial_family_members",
            )
        raw_members = tuple(cast("Sequence[object]", raw_member_value))
        if not raw_members or any(
            not isinstance(member, LogicalTrialIdentity) for member in raw_members
        ):
            raise _family_error(
                "trial family must contain logical trial identities",
                "invalid_trial_family_members",
            )
        members = cast("tuple[LogicalTrialIdentity, ...]", raw_members)
        identity_keys = tuple(member.identity_key for member in members)
        if len(set(identity_keys)) != len(identity_keys):
            raise _family_error(
                "trial family cannot repeat a logical trial",
                "duplicate_logical_trial",
            )
        candidate_bindings: dict[
            tuple[ExperimentId, CandidateId],
            tuple[int, ContentHash],
        ] = {}
        ordinal_bindings: dict[tuple[ExperimentId, int], CandidateId] = {}
        for member in members:
            candidate_key = (member.origin_experiment_id, member.candidate_id)
            candidate_binding = (member.ordinal, member.parameter_hash)
            existing_candidate = candidate_bindings.get(candidate_key)
            if (
                existing_candidate is not None
                and existing_candidate != candidate_binding
            ):
                raise _family_error(
                    "one origin candidate must have one ordinal and parameter hash",
                    "ambiguous_trial_candidate_identity",
                )
            candidate_bindings[candidate_key] = candidate_binding
            ordinal_key = (member.origin_experiment_id, member.ordinal)
            existing_ordinal = ordinal_bindings.get(ordinal_key)
            if existing_ordinal is not None and existing_ordinal != member.candidate_id:
                raise _family_error(
                    "one origin ordinal must identify one candidate",
                    "ambiguous_trial_ordinal",
                )
            ordinal_bindings[ordinal_key] = member.candidate_id
        if not any(member.kind is TrialKind.CURRENT for member in members):
            raise _family_error(
                "trial family must declare at least one current trial",
                "current_trial_family_empty",
            )
        object.__setattr__(
            self,
            "members",
            tuple(sorted(members, key=_member_sort_key)),
        )

    @property
    def prior_members(self) -> tuple[LogicalTrialIdentity, ...]:
        """Return the canonical historical subset."""
        return tuple(
            member for member in self.members if member.kind is TrialKind.PRIOR
        )

    @property
    def current_members(self) -> tuple[LogicalTrialIdentity, ...]:
        """Return the canonical subset bound to the current launch."""
        return tuple(
            member for member in self.members if member.kind is TrialKind.CURRENT
        )

    @property
    def declared_trial_count(self) -> int:
        """Count prior and current logical trials exactly once."""
        return len(self.members)
