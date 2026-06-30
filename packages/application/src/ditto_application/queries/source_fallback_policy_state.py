"""Source fallback policy state query facade."""

from __future__ import annotations

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyReader,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyStatus as DataCatalogSourceFallbackPolicyStatus,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyStatus,
    to_catalog_source_fallback_policy,
    to_catalog_source_fallback_policy_event,
)

__all__ = ["CatalogSourceFallbackPolicyQueryFacade"]


class CatalogSourceFallbackPolicyQueryFacade:
    """Expose current source fallback policy state and audit events."""

    def __init__(self, policy_reader: CatalogSourceFallbackPolicyReader) -> None:
        self._policy_reader = policy_reader

    def get_source_fallback_policy(
        self,
        policy_id: str,
    ) -> CatalogSourceFallbackPolicy:
        """Return one source fallback policy state by ID."""
        policy = self._policy_reader.get_source_fallback_policy(policy_id)
        if policy is None:
            raise AppQueryError(
                f"Catalog source fallback policy not found: {policy_id}"
            )
        return to_catalog_source_fallback_policy(policy)

    def list_source_fallback_policies(
        self,
        *,
        dataset_id: str | None = None,
        status: CatalogSourceFallbackPolicyStatus | None = None,
    ) -> tuple[CatalogSourceFallbackPolicy, ...]:
        """Return source fallback policies filtered by dataset or status."""
        data_status: DataCatalogSourceFallbackPolicyStatus | None = status
        return tuple(
            to_catalog_source_fallback_policy(item)
            for item in self._policy_reader.list_source_fallback_policies(
                dataset_id=dataset_id,
                status=data_status,
            )
        )

    def list_source_fallback_policy_events(
        self,
        policy_id: str,
    ) -> tuple[CatalogSourceFallbackPolicyEvent, ...]:
        """Return append-only events for one source fallback policy."""
        return tuple(
            to_catalog_source_fallback_policy_event(item)
            for item in self._policy_reader.list_source_fallback_policy_events(
                policy_id
            )
        )
