"""Composition adapter for the isolated Analysis ResearchJudgment domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from dishka import Provider, Scope, provide
from ditto_analysis.research.judgments import ResearchJudgment
from ditto_analysis.storage.sqlite.research import SQLiteResearchJudgmentStore
from ditto_application.processes.research.record_research_judgment import (
    RecordResearchJudgment,
)
from ditto_application.queries.research_judgments import (
    ResearchJudgmentQueryService,
)
from ditto_application.research_judgment_contracts import (
    ResearchJudgmentFactory,
    ResearchJudgmentMaterial,
    ResearchJudgmentReader,
    ResearchJudgmentRecorder,
    ResearchJudgmentView,
)

__all__ = [
    "AnalysisResearchJudgmentFactory",
    "ResearchJudgmentCompositionProvider",
]


class AnalysisResearchJudgmentFactory:
    """Adapt application record material to the isolated Analysis contract."""

    def create(self, material: ResearchJudgmentMaterial) -> ResearchJudgmentView:
        """Build a content-addressed ResearchJudgment without leaking Analysis."""
        return ResearchJudgment(
            run_ids=material.run_ids,
            judgment=material.judgment,
            created_at=material.created_at,
            strategy_id=material.strategy_id,
            strategy_version=material.strategy_version,
        )


class AnalysisResearchJudgmentStoreAdapter:
    """Bind the Analysis store to the application-owned persistence ports."""

    def __init__(self, store: SQLiteResearchJudgmentStore) -> None:
        self._store = store

    def save(self, judgment: ResearchJudgmentView) -> ResearchJudgmentView:
        """Persist one saved judgment; replay returns the stored entry."""
        return self._store.save(cast(ResearchJudgment, judgment))

    def get(self, judgment_id: str) -> ResearchJudgmentView | None:
        """Return one exact judgment through the application read port."""
        return self._store.get(judgment_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgmentView, ...]:
        """Return the newest judgments through the application read port."""
        return self._store.list_recent(limit=limit)


class ResearchJudgmentCompositionProvider(Provider):
    """Bind the Analysis implementation to the Application-owned port."""

    scope = Scope.APP

    @provide
    def research_judgment_factory(self) -> ResearchJudgmentFactory:
        """Provide the exact cross-plane adapter at the composition root."""
        return AnalysisResearchJudgmentFactory()

    @provide
    def research_judgment_recorder(
        self, store: SQLiteResearchJudgmentStore
    ) -> ResearchJudgmentRecorder:
        """Bind append-only persistence to the application write port."""
        return AnalysisResearchJudgmentStoreAdapter(store)

    @provide
    def research_judgment_reader(
        self, store: SQLiteResearchJudgmentStore
    ) -> ResearchJudgmentReader:
        """Bind exact judgment reads to the application read port."""
        return AnalysisResearchJudgmentStoreAdapter(store)

    @provide
    def research_judgment_query(
        self, reader: ResearchJudgmentReader
    ) -> ResearchJudgmentQueryService:
        """Provide exact persisted-judgment reads for the research routes."""
        return ResearchJudgmentQueryService(reader)

    @provide
    def record_research_judgment(
        self, factory: ResearchJudgmentFactory, recorder: ResearchJudgmentRecorder
    ) -> RecordResearchJudgment:
        """Provide the recording process with the server wall clock."""
        return RecordResearchJudgment(
            factory=factory,
            recorder=recorder,
            clock=lambda: datetime.now(UTC),
        )
