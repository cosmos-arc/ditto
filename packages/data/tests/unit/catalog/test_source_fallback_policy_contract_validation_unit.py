"""Validation tests for source fallback policy state contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyEventAction,
    CatalogSourceFallbackPolicyStatus,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _policy() -> CatalogSourceFallbackPolicy:
    return CatalogSourceFallbackPolicy(
        policy_id="fallback-001",
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-09-04",
        default_source="wind",
        selected_source="tushare",
        recommended_source="tushare",
        status="draft",
        created_by="operator",
        created_at=_NOW,
        recommended_actions=("review_source_failover",),
        reason_codes=("PRIMARY_SOURCE_STALE",),
        fallback_sources=("tushare",),
        unsupported_sources=(),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=True,
        execution_allowed=False,
    )


def test_fallback_policy_allows_no_recommended_source() -> None:
    policy = replace(_policy(), recommended_source=None)

    assert policy.recommended_source is None


def test_fallback_policy_rejects_blank_identity_text() -> None:
    with pytest.raises(ValueError, match="Invalid policy_id"):
        replace(_policy(), policy_id=" fallback-001")


def test_fallback_policy_rejects_unknown_status() -> None:
    invalid_status = cast(CatalogSourceFallbackPolicyStatus, "pending")

    with pytest.raises(ValueError, match="Invalid source fallback policy status"):
        replace(_policy(), status=invalid_status)


def test_fallback_policy_event_rejects_unknown_action() -> None:
    invalid_action = cast(CatalogSourceFallbackPolicyEventAction, "revoked")

    with pytest.raises(ValueError, match="Invalid source fallback policy event action"):
        CatalogSourceFallbackPolicyEvent(
            policy_id="fallback-001",
            action=invalid_action,
            actor="operator",
            action_at=_NOW,
            status="active",
        )
