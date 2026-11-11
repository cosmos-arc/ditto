"""Composition adapter for the isolated Analysis ResearchCase domain."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from dishka import Provider, Scope, provide
from ditto_analysis.research.cases import ResearchCase
from ditto_analysis.storage.sqlite.research import SQLiteResearchCaseStore
from ditto_application.research_case_contracts import (
    ResearchCaseFactory,
    ResearchCaseMaterial,
    ResearchCaseReader,
    ResearchCaseRecorder,
    ResearchCaseView,
)

__all__ = [
    "AnalysisResearchCaseFactory",
    "ResearchCaseCompositionProvider",
]


class AnalysisResearchCaseFactory:
    """Adapt application handoff material to the isolated Analysis contract."""

    def create(self, material: ResearchCaseMaterial) -> ResearchCaseView:
        """Build a content-addressed ResearchCase without leaking Analysis inward."""
        return ResearchCase(**asdict(material))


class AnalysisResearchCaseStoreAdapter:
    """Bind the Analysis store to the application-owned persistence ports."""

    def __init__(self, store: SQLiteResearchCaseStore) -> None:
        self._store = store

    def save(self, case: ResearchCaseView) -> None:
        """Persist one handed-off case; replay keeps content addressing."""
        self._store.save(cast(ResearchCase, case))

    def get(self, case_id: str) -> ResearchCaseView | None:
        """Return one exact case through the application read port."""
        return self._store.get(case_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchCaseView, ...]:
        """Return the newest cases through the application read port."""
        return self._store.list_recent(limit=limit)

    def list_by_run(
        self, selection_run_id: str, *, limit: int = 20
    ) -> tuple[ResearchCaseView, ...]:
        """Return one run's cases through the application read port."""
        return self._store.list_by_run(selection_run_id, limit=limit)


class ResearchCaseCompositionProvider(Provider):
    """Bind the Analysis implementation to the Application-owned port."""

    scope = Scope.APP

    @provide
    def research_case_factory(self) -> ResearchCaseFactory:
        """Provide the exact cross-plane adapter at the composition root."""
        return AnalysisResearchCaseFactory()

    @provide
    def research_case_recorder(
        self, store: SQLiteResearchCaseStore
    ) -> ResearchCaseRecorder:
        """Bind append-only persistence to the application write port."""
        return AnalysisResearchCaseStoreAdapter(store)

    @provide
    def research_case_reader(
        self, store: SQLiteResearchCaseStore
    ) -> ResearchCaseReader:
        """Bind exact case reads to the application read port."""
        return AnalysisResearchCaseStoreAdapter(store)
