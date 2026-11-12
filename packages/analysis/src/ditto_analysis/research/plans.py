"""Immutable post-market candidate reasons and next-day plans."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId

__all__ = ["NextDayPlan", "PlanCandidateNote"]

_SCHEMA_VERSION = 1


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty unpadded string")
    return value


def _utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _observation_date(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError("observation_date must be a plain calendar date")
    return value


def _candidate_notes(values: object) -> tuple[PlanCandidateNote, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("candidate_notes must be a non-empty tuple")
    raw_values = cast("tuple[object, ...]", values)
    notes = tuple(
        _candidate_note(item, index=index) for index, item in enumerate(raw_values)
    )
    ids = [int(note.instrument_id) for note in notes]
    if len(set(ids)) != len(ids) or any(value <= 0 for value in ids):
        raise ValueError("candidate_notes must reference unique positive identities")
    return notes


def _candidate_note(value: object, *, index: int) -> PlanCandidateNote:
    if not isinstance(value, PlanCandidateNote):
        raise ValueError(f"candidate_notes[{index}] must be a PlanCandidateNote")
    return value


@dataclass(frozen=True, slots=True)
class PlanCandidateNote:
    """One candidate's identity with the reason it stayed on tomorrow's list."""

    instrument_id: InstrumentId
    reason: str

    def __post_init__(self) -> None:
        """Wrap a positive integer identity and reject padded empty reasons."""
        # 与 ResearchCase._candidate_ids 同语义：接受正整数并包装为域身份。
        if type(self.instrument_id) is not int or self.instrument_id <= 0:
            raise ValueError("instrument_id must be a positive integer")
        object.__setattr__(self, "instrument_id", InstrumentId(self.instrument_id))
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="candidate reason"),
        )


@dataclass(frozen=True, slots=True)
class NextDayPlan:
    """
    One post-market record: candidate reasons and the plan for next session.

    The plan keeps its own observation date, so reopening never rewrites the
    record under a later global date; revisions are separate entries.
    """

    observation_date: date
    candidate_notes: tuple[PlanCandidateNote, ...]
    next_day_plan: str
    created_at: datetime
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Fail closed on erased dates, candidates, reasons, or plan text."""
        if (
            type(self.schema_version) is not int
            or self.schema_version != _SCHEMA_VERSION
        ):
            raise ValueError("unsupported Next Day Plan schema_version")
        object.__setattr__(
            self, "observation_date", _observation_date(self.observation_date)
        )
        object.__setattr__(
            self, "candidate_notes", _candidate_notes(self.candidate_notes)
        )
        object.__setattr__(
            self,
            "next_day_plan",
            _text(self.next_day_plan, field_name="next_day_plan"),
        )
        object.__setattr__(
            self, "created_at", _utc(self.created_at, field_name="created_at")
        )

    @property
    def canonical_payload(self) -> dict[str, object]:
        """
        Return the complete deterministic record preimage.

        created_at stays out of the preimage: one exact user record keeps one
        identity regardless of when the retry landed, while an edited plan is
        new content and therefore a new entry.
        """
        return {
            "schema_version": self.schema_version,
            "observation_date": self.observation_date.isoformat(),
            # 候选顺序是记录者组织的阅读顺序，按输入原序冻结。
            "candidate_notes": [
                {
                    "instrument_id": int(note.instrument_id),
                    "reason": note.reason,
                }
                for note in self.candidate_notes
            ],
            "next_day_plan": self.next_day_plan,
        }

    @property
    def content_hash(self) -> str:
        """Return the full SHA-256 hash of the canonical record payload."""
        encoded = orjson.dumps(self.canonical_payload, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(encoded).hexdigest()

    @property
    def plan_id(self) -> str:
        """Return the stable content-addressed Next Day Plan identity."""
        return f"next-day-plan:sha256:{self.content_hash}"
