"""Source fallback policy state API route tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.source_fallback_policy import (
    ActivateCatalogSourceFallbackPolicyHandler,
    ApproveCatalogSourceFallbackPolicyHandler,
    CatalogSourceFallbackPolicyDraftCommand,
    CatalogSourceFallbackPolicyDraftResult,
    CatalogSourceFallbackPolicyLifecycleCommand,
    CatalogSourceFallbackPolicyLifecycleResult,
    RetireCatalogSourceFallbackPolicyHandler,
)
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
)
from ditto_apps.api.routes import ingestion_source_fallback_policy
from ditto_apps.models.common import APIResponse
from ditto_apps.models.source_fallback import (
    CatalogSourceFallbackPolicyDraftRequest,
    CatalogSourceFallbackPolicyEventResponse,
    CatalogSourceFallbackPolicyLifecycleRequest,
    CatalogSourceFallbackPolicyStateResponse,
)

_PolicyDraftRoute = Callable[
    ...,
    Awaitable[APIResponse[CatalogSourceFallbackPolicyStateResponse]],
]
_PolicyListRoute = Callable[
    ...,
    Awaitable[APIResponse[list[CatalogSourceFallbackPolicyStateResponse]]],
]
_PolicyGetRoute = Callable[
    ...,
    Awaitable[APIResponse[CatalogSourceFallbackPolicyStateResponse]],
]
_PolicyEventListRoute = Callable[
    ...,
    Awaitable[APIResponse[list[CatalogSourceFallbackPolicyEventResponse]]],
]
_PolicyLifecycleRoute = Callable[
    ...,
    Awaitable[APIResponse[CatalogSourceFallbackPolicyStateResponse]],
]
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _inline_source_fallback_policy_route_thread_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(
        ingestion_source_fallback_policy,
        "run_blocking",
        run_inline,
    )


def _policy(*, status: str = "draft") -> CatalogSourceFallbackPolicy:
    return CatalogSourceFallbackPolicy(
        policy_id="fallback-policy-001",
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="tushare",
        selected_source="fred",
        recommended_source="fred",
        status=status,
        created_by="architecture-review",
        created_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
        recommended_actions=("review_source_failover",),
        reason_codes=("default_source_stale",),
        fallback_sources=("fred",),
        unsupported_sources=("tdx",),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=True,
        execution_allowed=True,
        notes="persist dry-run fallback decision",
    )


async def _call_policy_draft(
    handler: object,
    request: CatalogSourceFallbackPolicyDraftRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    route = cast(
        _PolicyDraftRoute,
        getattr(
            ingestion_source_fallback_policy.draft_catalog_source_fallback_policy,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.draft_catalog_source_fallback_policy,
        ),
    )
    return await route(handler=handler, request=request)


async def _call_policy_list(
    facade: object,
    *,
    dataset_id: str | None = None,
    status: str | None = None,
) -> APIResponse[list[CatalogSourceFallbackPolicyStateResponse]]:
    route = cast(
        _PolicyListRoute,
        getattr(
            ingestion_source_fallback_policy.list_catalog_source_fallback_policies,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.list_catalog_source_fallback_policies,
        ),
    )
    return await route(facade=facade, dataset_id=dataset_id, status=status)


async def _call_policy_get(
    facade: object,
    *,
    policy_id: str,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    route = cast(
        _PolicyGetRoute,
        getattr(
            ingestion_source_fallback_policy.get_catalog_source_fallback_policy,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.get_catalog_source_fallback_policy,
        ),
    )
    return await route(facade=facade, policy_id=policy_id)


async def _call_policy_event_list(
    facade: object,
    *,
    policy_id: str,
) -> APIResponse[list[CatalogSourceFallbackPolicyEventResponse]]:
    route = cast(
        _PolicyEventListRoute,
        getattr(
            ingestion_source_fallback_policy.list_catalog_source_fallback_policy_events,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.list_catalog_source_fallback_policy_events,
        ),
    )
    return await route(facade=facade, policy_id=policy_id)


async def _call_policy_approve(
    handler: ApproveCatalogSourceFallbackPolicyHandler,
    *,
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    route = cast(
        _PolicyLifecycleRoute,
        getattr(
            ingestion_source_fallback_policy.approve_catalog_source_fallback_policy,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.approve_catalog_source_fallback_policy,
        ),
    )
    return await route(handler=handler, policy_id=policy_id, request=request)


async def _call_policy_activate(
    handler: ActivateCatalogSourceFallbackPolicyHandler,
    *,
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    route = cast(
        _PolicyLifecycleRoute,
        getattr(
            ingestion_source_fallback_policy.activate_catalog_source_fallback_policy,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.activate_catalog_source_fallback_policy,
        ),
    )
    return await route(handler=handler, policy_id=policy_id, request=request)


async def _call_policy_retire(
    handler: RetireCatalogSourceFallbackPolicyHandler,
    *,
    policy_id: str,
    request: CatalogSourceFallbackPolicyLifecycleRequest,
) -> APIResponse[CatalogSourceFallbackPolicyStateResponse]:
    route = cast(
        _PolicyLifecycleRoute,
        getattr(
            ingestion_source_fallback_policy.retire_catalog_source_fallback_policy,
            "__dishka_orig_func__",
            ingestion_source_fallback_policy.retire_catalog_source_fallback_policy,
        ),
    )
    return await route(handler=handler, policy_id=policy_id, request=request)


class TestCatalogSourceFallbackPolicyStateRoutes:
    """Source fallback policy state FastAPI contracts."""

    async def test_drafts_source_fallback_policy_without_activation(self) -> None:
        handler = MagicMock()
        handler.handle.return_value = CatalogSourceFallbackPolicyDraftResult(
            policy=_policy(),
        )
        request = CatalogSourceFallbackPolicyDraftRequest(
            dataset_id="stock_daily",
            namespace="market",
            trade_date="2026-06-01",
            default_source="tushare",
            selected_source="fred",
            recommended_source="fred",
            created_by="architecture-review",
            recommended_actions=["review_source_failover"],
            reason_codes=["default_source_stale"],
            fallback_sources=["fred"],
            unsupported_sources=["tdx"],
            source_selection_status="ready",
            source_selection_blockers=[],
            approval_required=True,
            execution_allowed=True,
            notes="persist dry-run fallback decision",
        )

        response = await _call_policy_draft(handler, request)

        handler.handle.assert_called_once_with(
            CatalogSourceFallbackPolicyDraftCommand(
                dataset_id="stock_daily",
                namespace="market",
                trade_date="2026-06-01",
                default_source="tushare",
                selected_source="fred",
                recommended_source="fred",
                created_by="architecture-review",
                recommended_actions=("review_source_failover",),
                reason_codes=("default_source_stale",),
                fallback_sources=("fred",),
                unsupported_sources=("tdx",),
                source_selection_status="ready",
                source_selection_blockers=(),
                approval_required=True,
                execution_allowed=True,
                notes="persist dry-run fallback decision",
            )
        )
        assert response.data.policy_id == "fallback-policy-001"
        assert response.data.status == "draft"
        assert response.data.created_at == "2026-06-10T09:00:00+00:00"
        assert response.data.recommended_actions == ["review_source_failover"]
        assert response.data.authority_hash == _policy().authority_hash
        assert response.data.authority_payload["action"] == "approval"

    async def test_lists_source_fallback_policy_state(self) -> None:
        facade = MagicMock()
        facade.list_source_fallback_policies.return_value = (_policy(),)

        response = await _call_policy_list(
            facade,
            dataset_id="stock_daily",
            status="draft",
        )

        facade.list_source_fallback_policies.assert_called_once_with(
            dataset_id="stock_daily",
            status="draft",
        )
        assert [item.policy_id for item in response.data] == ["fallback-policy-001"]
        assert response.data[0].dataset_id == "stock_daily"

    async def test_gets_source_fallback_policy_state_by_id(self) -> None:
        facade = MagicMock()
        facade.get_source_fallback_policy.return_value = _policy()

        response = await _call_policy_get(facade, policy_id="fallback-policy-001")

        facade.get_source_fallback_policy.assert_called_once_with("fallback-policy-001")
        assert response.data.policy_id == "fallback-policy-001"
        assert response.data.notes == "persist dry-run fallback decision"

    async def test_lists_source_fallback_policy_audit_events(self) -> None:
        facade = MagicMock()
        facade.list_source_fallback_policy_events.return_value = (
            CatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="drafted",
                actor="architecture-review",
                action_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
                status="draft",
                notes="persist dry-run fallback decision",
            ),
        )

        response = await _call_policy_event_list(
            facade,
            policy_id="fallback-policy-001",
        )

        facade.list_source_fallback_policy_events.assert_called_once_with(
            "fallback-policy-001"
        )
        assert len(response.data) == 1
        assert response.data[0].action == "drafted"
        assert response.data[0].action_at == "2026-06-10T09:00:00+00:00"

    async def test_approves_source_fallback_policy_without_activation(self) -> None:
        handler = MagicMock(spec=ApproveCatalogSourceFallbackPolicyHandler)
        handler.handle.return_value = CatalogSourceFallbackPolicyLifecycleResult(
            policy=_policy(status="approved"),
        )
        request = CatalogSourceFallbackPolicyLifecycleRequest(
            authority_hash="a" * 64,
            actor="lead-reviewer",
            notes="approved for controlled fallback activation",
        )

        response = await _call_policy_approve(
            handler,
            policy_id="fallback-policy-001",
            request=request,
        )

        handler.handle.assert_called_once_with(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash="a" * 64,
                actor="lead-reviewer",
                notes="approved for controlled fallback activation",
            )
        )
        assert response.data.policy_id == "fallback-policy-001"
        assert response.data.status == "approved"

    async def test_activates_source_fallback_policy_resource_only(self) -> None:
        handler = MagicMock(spec=ActivateCatalogSourceFallbackPolicyHandler)
        handler.handle.return_value = CatalogSourceFallbackPolicyLifecycleResult(
            policy=_policy(status="active"),
        )
        request = CatalogSourceFallbackPolicyLifecycleRequest(
            authority_hash="a" * 64,
            actor="ops-runner",
            notes="activate policy resource only",
        )

        response = await _call_policy_activate(
            handler,
            policy_id="fallback-policy-001",
            request=request,
        )

        handler.handle.assert_called_once_with(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash="a" * 64,
                actor="ops-runner",
                notes="activate policy resource only",
            )
        )
        assert response.data.status == "active"

    async def test_retires_source_fallback_policy_resource_only(self) -> None:
        handler = MagicMock(spec=RetireCatalogSourceFallbackPolicyHandler)
        handler.handle.return_value = CatalogSourceFallbackPolicyLifecycleResult(
            policy=_policy(status="retired"),
        )
        request = CatalogSourceFallbackPolicyLifecycleRequest(
            authority_hash="a" * 64,
            actor="ops-runner",
            notes="retire policy after review",
        )

        response = await _call_policy_retire(
            handler,
            policy_id="fallback-policy-001",
            request=request,
        )

        handler.handle.assert_called_once_with(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash="a" * 64,
                actor="ops-runner",
                notes="retire policy after review",
            )
        )
        assert response.data.status == "retired"
