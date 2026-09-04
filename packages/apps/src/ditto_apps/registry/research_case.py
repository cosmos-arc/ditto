"""Composition adapter for the isolated Analysis ResearchCase domain."""

from __future__ import annotations

from dataclasses import asdict

from dishka import Provider, Scope, provide
from ditto_analysis.research.cases import ResearchCase
from ditto_application.research_case_contracts import (
    ResearchCaseFactory,
    ResearchCaseMaterial,
    ResearchCaseView,
)

__all__ = ["AnalysisResearchCaseFactory", "ResearchCaseCompositionProvider"]


class AnalysisResearchCaseFactory:
    """Adapt application handoff material to the isolated Analysis contract."""

    def create(self, material: ResearchCaseMaterial) -> ResearchCaseView:
        """Build a content-addressed ResearchCase without leaking Analysis inward."""
        return ResearchCase(**asdict(material))


class ResearchCaseCompositionProvider(Provider):
    """Bind the Analysis implementation to the Application-owned port."""

    scope = Scope.APP

    @provide
    def research_case_factory(self) -> ResearchCaseFactory:
        """Provide the exact cross-plane adapter at the composition root."""
        return AnalysisResearchCaseFactory()
