"""Catalog remediation approval query facade."""

from __future__ import annotations

from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalReader,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalStatus as DataCatalogRemediationApprovalStatus,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.remediation_approval import (
    CatalogRemediationApproval,
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalStatus,
    to_catalog_remediation_approval,
    to_catalog_remediation_approval_event,
)

__all__ = ["CatalogRemediationApprovalQueryFacade"]


class CatalogRemediationApprovalQueryFacade:
    """Expose current remediation approval state and audit events."""

    def __init__(self, approval_reader: CatalogRemediationApprovalReader) -> None:
        self._approval_reader = approval_reader

    def get_remediation_approval(
        self,
        approval_id: str,
    ) -> CatalogRemediationApproval:
        """Return one remediation approval state by ID."""
        approval = self._approval_reader.get_remediation_approval(approval_id)
        if approval is None:
            raise AppQueryError(
                f"Catalog remediation approval not found: {approval_id}"
            )
        return to_catalog_remediation_approval(approval)

    def list_remediation_approvals(
        self,
        *,
        item_id: str | None = None,
        status: CatalogRemediationApprovalStatus | None = None,
    ) -> tuple[CatalogRemediationApproval, ...]:
        """Return remediation approval states filtered by item or status."""
        data_status: DataCatalogRemediationApprovalStatus | None = status
        return tuple(
            to_catalog_remediation_approval(item)
            for item in self._approval_reader.list_remediation_approvals(
                item_id=item_id,
                status=data_status,
            )
        )

    def list_remediation_approval_events(
        self,
        approval_id: str,
    ) -> tuple[CatalogRemediationApprovalEvent, ...]:
        """Return append-only events for one remediation approval."""
        return tuple(
            to_catalog_remediation_approval_event(item)
            for item in self._approval_reader.list_remediation_approval_events(
                approval_id
            )
        )
