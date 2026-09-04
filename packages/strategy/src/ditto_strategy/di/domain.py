"""Stateless strategy-domain service providers."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.selection.pipeline import SelectionPipeline

__all__ = ["StrategyDomainProvider"]


class StrategyDomainProvider(Provider):
    """Provide deterministic strategy-owned domain services."""

    scope = Scope.APP

    @provide
    def industry_rotation_service(self) -> IndustryRotationService:
        """Provide the versioned industry-rotation scorer."""
        return IndustryRotationService()

    @provide
    def selection_pipeline(self) -> SelectionPipeline:
        """Provide the deterministic stock/ETF selection pipeline."""
        return SelectionPipeline()
