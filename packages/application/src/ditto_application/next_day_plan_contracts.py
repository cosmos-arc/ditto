"""Application-owned contract for post-market next-day plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

__all__ = [
    "NextDayPlanFactory",
    "NextDayPlanMaterial",
    "NextDayPlanReader",
    "NextDayPlanRecorder",
    "NextDayPlanView",
    "PlanCandidateNoteView",
    "PlanClock",
]


@dataclass(frozen=True, slots=True)
class NextDayPlanMaterial:
    """Complete immutable material passed to the isolated analysis plane."""

    observation_date: str
    candidate_notes: tuple[tuple[int, str], ...]
    next_day_plan: str
    created_at: datetime


class PlanCandidateNoteView(Protocol):
    """Narrow candidate note shape shared with the analysis plane."""

    @property
    def instrument_id(self) -> int:
        """Return the candidate's instrument identity."""
        ...

    @property
    def reason(self) -> str:
        """Return the recorded reason this candidate stays on the list."""
        ...


class NextDayPlanView(Protocol):
    """Narrow structural result returned by an analysis-plane factory."""

    @property
    def plan_id(self) -> str:
        """Return the immutable next-day-plan identity."""
        ...

    @property
    def observation_date(self) -> date:
        """Return the original observation date the plan was made under."""
        ...

    @property
    def candidate_notes(self) -> tuple[PlanCandidateNoteView, ...]:
        """Return each candidate identity with its recorded reason."""
        ...

    @property
    def next_day_plan(self) -> str:
        """Return the recorded plan text for the next session."""
        ...

    @property
    def created_at(self) -> datetime:
        """Return the server-stamped recording instant."""
        ...

    @property
    def schema_version(self) -> int:
        """Return the plan schema version."""
        ...


class NextDayPlanFactory(Protocol):
    """Port implemented only at the apps composition boundary."""

    def create(self, material: NextDayPlanMaterial) -> NextDayPlanView:
        """Validate and create one immutable analysis-owned plan."""
        ...


class NextDayPlanRecorder(Protocol):
    """Append-only persistence port for recorded plans."""

    def save(self, plan: NextDayPlanView) -> NextDayPlanView:
        """
        Persist one plan and return the authoritative stored entry.

        An exact replay keeps the first-recorded entry (and its timestamp).
        """
        ...


class NextDayPlanReader(Protocol):
    """Exact read port backed by the append-only plan store."""

    def get(self, plan_id: str) -> NextDayPlanView | None:
        """Return one exact plan or None when never recorded."""
        ...

    def list_recent(self, *, limit: int = 20) -> tuple[NextDayPlanView, ...]:
        """Return the most recently recorded plans, newest first."""
        ...

    def list_by_observation(
        self, observation_date: str, *, limit: int = 20
    ) -> tuple[NextDayPlanView, ...]:
        """Return plans recorded under one exact original observation date."""
        ...


PlanClock = Callable[[], datetime]
