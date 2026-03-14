"""Unified derived query service contract."""

from __future__ import annotations

from typing import NoReturn

import polars as pl

from ditto_datahub.services.derived.queries import (
    DerivedCompareQuery,
    DerivedLatestQuery,
    DerivedSeriesQuery,
    DerivedSourceScope,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService

__all__ = ["DerivedQueryService"]


class DerivedQueryService:
    """Phase 2 contract-first query service for unified derived access."""

    def __init__(self, catalog_service: DerivedCatalogService) -> None:
        self._catalog_service = catalog_service

    def find_latest(self, query: DerivedLatestQuery) -> pl.DataFrame:
        """Validate latest query inputs before Phase 3 backends land."""
        resolved_versions = self._resolve_versions(query.derived_ids, query.version)
        self._ensure_query_backend_ready(
            query_name="latest",
            source_scope=query.source_scope,
            resolved_versions=resolved_versions,
        )

    def find_series(self, query: DerivedSeriesQuery) -> pl.DataFrame:
        """Validate series query inputs before Phase 3 backends land."""
        resolved_versions = self._resolve_versions(query.derived_ids, query.version)
        self._ensure_query_backend_ready(
            query_name="series",
            source_scope=query.source_scope,
            resolved_versions=resolved_versions,
        )

    def compare_sources(self, query: DerivedCompareQuery) -> pl.DataFrame:
        """Validate compare inputs before Phase 3 backends land."""
        resolved_versions = self._resolve_versions(query.derived_ids, query.version)
        for source_scope in query.compare_sources:
            self._validate_source_scope(source_scope)
        scopes = [scope.value for scope in query.compare_sources]
        message = (
            "Phase 3 backend not ready: "
            + f"compare_sources compare_sources={scopes} "
            + f"resolved_versions={resolved_versions}"
        )
        raise NotImplementedError(message)

    def _ensure_query_backend_ready(
        self,
        *,
        query_name: str,
        source_scope: DerivedSourceScope,
        resolved_versions: dict[str, int],
    ) -> NoReturn:
        self._validate_source_scope(source_scope)
        message = (
            f"Phase 3 backend not ready: {query_name} "
            + f"source_scope={source_scope.value} "
            + f"resolved_versions={resolved_versions}"
        )
        raise NotImplementedError(message)

    def _resolve_versions(
        self,
        derived_ids: tuple[str, ...],
        requested_version: int | None,
    ) -> dict[str, int]:
        resolved: dict[str, int] = {}
        for derived_id in derived_ids:
            version = requested_version or self._resolve_active_version(derived_id)
            spec = self._catalog_service.get_spec(derived_id, version)
            if spec is None:
                msg = (
                    "derived spec not found for "
                    f"derived_id={derived_id} version={version}"
                )
                raise KeyError(msg)
            version_record = self._catalog_service.get_version(derived_id, version)
            if version_record is None:
                msg = (
                    "derived version not found for "
                    f"derived_id={derived_id} version={version}"
                )
                raise KeyError(msg)
            resolved[derived_id] = version
        return resolved

    def _resolve_active_version(self, derived_id: str) -> int:
        state = self._catalog_service.get_state(derived_id)
        if state is None or state.active_version is None:
            raise KeyError(f"active version not found for derived_id={derived_id}")
        return state.active_version

    def _validate_source_scope(self, source_scope: DerivedSourceScope) -> None:
        if source_scope not in (
            DerivedSourceScope.SERVING,
            DerivedSourceScope.OFFLINE,
        ):
            raise ValueError(f"unsupported source_scope: {source_scope}")
