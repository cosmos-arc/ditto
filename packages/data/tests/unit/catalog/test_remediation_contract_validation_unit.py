"""Validation tests for remediation approval state contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_data.catalog.remediation import (
    CatalogRemediationApproval,
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalEventAction,
    CatalogRemediationApprovalStatus,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _approval() -> CatalogRemediationApproval:
    return CatalogRemediationApproval(
        approval_id="approval-001",
        item_id="source_health:stock_daily:2026-09-04",
        action="repair_catalog_freshness",
        status="requested",
        requested_by="operator",
        requested_at=_NOW,
        intent_type="write",
        method="POST",
        path="/api/v1/ingestion/stock_daily/2026-09-04",
        request_payload={"force": True},
    )


def test_remediation_approval_accepts_an_intent_without_http_metadata() -> None:
    approval = replace(_approval(), method=None, path=None)

    assert approval.method is None
    assert approval.path is None


def test_remediation_approval_rejects_blank_identity_text() -> None:
    with pytest.raises(ValueError, match="Invalid approval_id"):
        replace(_approval(), approval_id=" ")


def test_remediation_approval_rejects_unknown_status() -> None:
    invalid_status = cast(CatalogRemediationApprovalStatus, "pending")

    with pytest.raises(ValueError, match="Invalid remediation approval status"):
        replace(_approval(), status=invalid_status)


def test_remediation_event_rejects_unknown_action() -> None:
    invalid_action = cast(CatalogRemediationApprovalEventAction, "executed")

    with pytest.raises(ValueError, match="Invalid remediation approval event action"):
        CatalogRemediationApprovalEvent(
            approval_id="approval-001",
            action=invalid_action,
            actor="operator",
            action_at=_NOW,
            status="approved",
        )
