"""Exact next-day plan reads for reopening saved post-market records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.next_day_plan_contracts import (
    NextDayPlanMaterial,
    PlanCandidateNoteView,
)
from ditto_application.queries.next_day_plans import (
    NextDayPlanQueryService,
    NextDayPlanSummary,
)

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)


@dataclass(frozen=True)
class _StubNote:
    instrument_id: int
    reason: str


@dataclass(frozen=True)
class _StubView:
    material: NextDayPlanMaterial

    @property
    def plan_id(self) -> str:
        digest = len(self.material.next_day_plan)
        return f"next-day-plan:sha256:{self.material.observation_date}:{digest}"

    @property
    def observation_date(self) -> date:
        return date.fromisoformat(self.material.observation_date)

    @property
    def candidate_notes(self) -> tuple[PlanCandidateNoteView, ...]:
        return tuple(_StubNote(i, r) for i, r in self.material.candidate_notes)

    @property
    def next_day_plan(self) -> str:
        return self.material.next_day_plan

    @property
    def created_at(self) -> datetime:
        return self.material.created_at

    @property
    def schema_version(self) -> int:
        return 1

    @property
    def source_judgment_id(self) -> str | None:
        return self.material.source_judgment_id


def _view(
    plan_id_suffix: str,
    *,
    observation_date: str = "2026-11-10",
    created_at: datetime = _CREATED,
) -> _StubView:
    view = _StubView(
        NextDayPlanMaterial(
            observation_date=observation_date,
            candidate_notes=((600779, "缩量回踩"), (510888, "跟随大盘")),
            next_day_plan="次日开盘观察放量",
            created_at=created_at,
        )
    )
    return _StubView(view.material) if plan_id_suffix else view


class _Reader:
    def __init__(self, plans: tuple[_StubView, ...]) -> None:
        self._plans = plans

    def get(self, plan_id: str) -> _StubView | None:
        return next((item for item in self._plans if item.plan_id == plan_id), None)

    def list_recent(self, *, limit: int = 20) -> tuple[_StubView, ...]:
        return self._plans[:limit]

    def list_by_observation(
        self, observation_date: str, *, limit: int = 20
    ) -> tuple[_StubView, ...]:
        return tuple(
            item
            for item in self._plans
            if item.observation_date.isoformat() == observation_date
        )[:limit]


def test_get_returns_the_exact_recorded_plan() -> None:
    view = _view("a")
    service = NextDayPlanQueryService(_Reader((view,)))

    assert service.get(view.plan_id) is view


def test_get_fails_closed_for_an_unknown_or_blank_identity() -> None:
    service = NextDayPlanQueryService(_Reader((_view("a"),)))

    with pytest.raises(AppQueryError) as missing:
        service.get("next-day-plan:sha256:" + "0" * 64)
    assert missing.value.details["reason"] == "next_day_plan_not_found"
    with pytest.raises(AppQueryError):
        service.get("  ")


def test_list_recent_summarizes_without_live_market_state() -> None:
    view = _view("a")
    service = NextDayPlanQueryService(_Reader((view,)))

    summaries = service.list_recent(limit=10)

    assert summaries == (
        NextDayPlanSummary(
            plan_id=view.plan_id,
            observation_date=view.observation_date,
            created_at=view.created_at,
            candidate_count=2,
            next_day_plan="次日开盘观察放量",
            source_judgment_id=None,
        ),
    )


def test_list_recent_exposes_the_source_judgment_reference() -> None:
    sourced = _StubView(
        NextDayPlanMaterial(
            observation_date="2026-11-10",
            candidate_notes=((600779, "缩量回踩"),),
            next_day_plan="按判断结论执行观察",
            created_at=_CREATED,
            source_judgment_id="research-judgment:sha256:" + "4" * 64,
        )
    )
    service = NextDayPlanQueryService(_Reader((sourced,)))

    summaries = service.list_recent(limit=10)

    assert summaries[0].source_judgment_id == "research-judgment:sha256:" + "4" * 64
