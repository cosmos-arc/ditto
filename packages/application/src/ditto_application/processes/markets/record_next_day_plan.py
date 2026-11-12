"""Record one post-market candidate-reason and next-day-plan revision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_application.exceptions import AppCommandError
from ditto_application.next_day_plan_contracts import (
    NextDayPlanFactory,
    NextDayPlanMaterial,
    NextDayPlanRecorder,
    NextDayPlanView,
    PlanClock,
)

__all__ = ["RecordNextDayPlan", "RecordNextDayPlanRequest"]


@dataclass(frozen=True, slots=True)
class RecordNextDayPlanRequest:
    """Exact user record: one observation date, reasons and the next plan."""

    observation_date: str
    candidate_notes: tuple[tuple[int, str], ...]
    next_day_plan: str


class RecordNextDayPlan:
    """Validate one record, stamp the server clock and append it."""

    def __init__(
        self,
        *,
        factory: NextDayPlanFactory,
        recorder: NextDayPlanRecorder,
        clock: PlanClock,
    ) -> None:
        self._factory = factory
        self._recorder = recorder
        self._clock = clock

    def record(self, request: RecordNextDayPlanRequest) -> NextDayPlanView:
        """Persist one immutable plan revision and return its exact view."""
        observation_date = _observation_date(request.observation_date)
        notes = _candidate_notes(request.candidate_notes)
        plan_text = _text(request.next_day_plan, field_name="next_day_plan")
        view = self._factory.create(
            NextDayPlanMaterial(
                observation_date=observation_date,
                candidate_notes=notes,
                next_day_plan=plan_text,
                created_at=self._clock(),
            )
        )
        return self._recorder.save(view)


def _observation_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AppCommandError("observation_date must be an ISO calendar date") from exc
    if parsed.isoformat() != value:
        raise AppCommandError("observation_date must be a canonical ISO date")
    return value


def _candidate_notes(
    values: tuple[tuple[int, str], ...],
) -> tuple[tuple[int, str], ...]:
    if not values:
        raise AppCommandError("candidate reasons are required")
    notes = tuple(
        (instrument_id, _text(reason, field_name="candidate reason"))
        for instrument_id, reason in values
    )
    ids = [item[0] for item in notes]
    if any(value <= 0 for value in ids) or len(set(ids)) != len(ids):
        raise AppCommandError("candidates must be unique positive identities")
    return notes


def _text(value: str, *, field_name: str) -> str:
    if not value or value != value.strip():
        raise AppCommandError(f"{field_name} must be a non-empty unpadded text")
    return value
