"""Composition adapter for the isolated Analysis NextDayPlan domain."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

from dishka import Provider, Scope, provide
from ditto_analysis.research.plans import NextDayPlan, PlanCandidateNote
from ditto_analysis.storage.sqlite.research import SQLiteNextDayPlanStore
from ditto_application.next_day_plan_contracts import (
    NextDayPlanFactory,
    NextDayPlanMaterial,
    NextDayPlanReader,
    NextDayPlanRecorder,
    NextDayPlanView,
)
from ditto_application.processes.markets.record_next_day_plan import (
    RecordNextDayPlan,
)
from ditto_application.queries.next_day_plans import NextDayPlanQueryService
from ditto_kernel.identity import InstrumentId

__all__ = [
    "AnalysisNextDayPlanFactory",
    "NextDayPlanCompositionProvider",
]


class AnalysisNextDayPlanFactory:
    """Adapt application record material to the isolated Analysis contract."""

    def create(self, material: NextDayPlanMaterial) -> NextDayPlanView:
        """Build a content-addressed NextDayPlan without leaking Analysis inward."""
        return NextDayPlan(
            observation_date=date.fromisoformat(material.observation_date),
            candidate_notes=tuple(
                PlanCandidateNote(
                    instrument_id=InstrumentId(instrument_id), reason=reason
                )
                for instrument_id, reason in material.candidate_notes
            ),
            next_day_plan=material.next_day_plan,
            created_at=material.created_at,
        )


class AnalysisNextDayPlanStoreAdapter:
    """Bind the Analysis store to the application-owned persistence ports."""

    def __init__(self, store: SQLiteNextDayPlanStore) -> None:
        self._store = store

    def save(self, plan: NextDayPlanView) -> NextDayPlanView:
        """Persist one recorded plan; replay returns the stored entry."""
        return self._store.save(cast(NextDayPlan, plan))

    def get(self, plan_id: str) -> NextDayPlanView | None:
        """Return one exact plan through the application read port."""
        return self._store.get(plan_id)

    def list_recent(self, *, limit: int = 20) -> tuple[NextDayPlanView, ...]:
        """Return the newest plans through the application read port."""
        return self._store.list_recent(limit=limit)

    def list_by_observation(
        self, observation_date: str, *, limit: int = 20
    ) -> tuple[NextDayPlanView, ...]:
        """Return one observation date's plans through the application read port."""
        return self._store.list_by_observation(observation_date, limit=limit)


class NextDayPlanCompositionProvider(Provider):
    """Bind the Analysis implementation to the Application-owned port."""

    scope = Scope.APP

    @provide
    def next_day_plan_factory(self) -> NextDayPlanFactory:
        """Provide the exact cross-plane adapter at the composition root."""
        return AnalysisNextDayPlanFactory()

    @provide
    def next_day_plan_recorder(
        self, store: SQLiteNextDayPlanStore
    ) -> NextDayPlanRecorder:
        """Bind append-only persistence to the application write port."""
        return AnalysisNextDayPlanStoreAdapter(store)

    @provide
    def next_day_plan_reader(self, store: SQLiteNextDayPlanStore) -> NextDayPlanReader:
        """Bind exact plan reads to the application read port."""
        return AnalysisNextDayPlanStoreAdapter(store)

    @provide
    def next_day_plan_query(self, reader: NextDayPlanReader) -> NextDayPlanQueryService:
        """Provide exact persisted-plan reads for the market routes."""
        return NextDayPlanQueryService(reader)

    @provide
    def record_next_day_plan(
        self, factory: NextDayPlanFactory, recorder: NextDayPlanRecorder
    ) -> RecordNextDayPlan:
        """Provide the recording process with the server wall clock."""
        return RecordNextDayPlan(
            factory=factory,
            recorder=recorder,
            clock=lambda: datetime.now(UTC),
        )
