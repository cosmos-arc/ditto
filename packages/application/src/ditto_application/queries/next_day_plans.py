"""Exact next-day plan reads for reopening saved post-market records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ditto_application.exceptions import AppQueryError
from ditto_application.next_day_plan_contracts import (
    NextDayPlanReader,
    NextDayPlanView,
)

__all__ = ["NextDayPlanQueryService", "NextDayPlanSummary"]


@dataclass(frozen=True, slots=True)
class NextDayPlanSummary:
    """Compact record summary for the plan list."""

    plan_id: str
    observation_date: date
    created_at: datetime
    candidate_count: int
    next_day_plan: str
    source_judgment_id: str | None = None


class NextDayPlanQueryService:
    """Read only exact persisted plans; never consult live market state."""

    def __init__(self, reader: NextDayPlanReader) -> None:
        self._reader = reader

    def get(self, plan_id: str) -> NextDayPlanView:
        """Return one exact persisted plan or a typed query-boundary error."""
        if not plan_id.strip():
            raise AppQueryError(
                "next-day plan plan_id must be non-empty",
                details={"reason": "invalid_next_day_plan_id"},
            )
        value = self._reader.get(plan_id)
        if value is None:
            raise AppQueryError(
                f"next-day plan not found: {plan_id}",
                details={"reason": "next_day_plan_not_found", "plan_id": plan_id},
            )
        return value

    def list_recent(self, *, limit: int = 20) -> tuple[NextDayPlanSummary, ...]:
        """List the newest recorded plans as reopen summaries."""
        return tuple(
            _summary(item) for item in self._reader.list_recent(limit=_limit(limit))
        )

    def list_by_observation(
        self, observation_date: str, *, limit: int = 20
    ) -> tuple[NextDayPlanSummary, ...]:
        """List plans recorded under one exact original observation date."""
        return tuple(
            _summary(item)
            for item in self._reader.list_by_observation(
                observation_date, limit=_limit(limit)
            )
        )


def _summary(item: NextDayPlanView) -> NextDayPlanSummary:
    return NextDayPlanSummary(
        plan_id=item.plan_id,
        observation_date=item.observation_date,
        created_at=item.created_at,
        candidate_count=len(item.candidate_notes),
        next_day_plan=item.next_day_plan,
        source_judgment_id=item.source_judgment_id,
    )


def _limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        raise AppQueryError(
            "next-day plan list limit must be positive",
            details={"reason": "invalid_next_day_plan_limit"},
        )
    return limit
