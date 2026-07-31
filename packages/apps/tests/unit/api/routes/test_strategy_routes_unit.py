"""Unit tests for strategy route error handling and governance endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import (
    ApproveReviewHandler,
    DeprecateStrategyHandler,
    ReactivateStrategyHandler,
    RejectReviewHandler,
    SubmitReviewHandler,
)
from ditto_application.contracts import (
    SpecChange,
    StrategyActiveInfo,
    StrategyActivePointerInfo,
    StrategyGovernanceEventInfo,
    StrategySpecInfo,
    StrategySpecValidationInfo,
    StrategyVersionDetailInfo,
    StrategyVersionDiffInfo,
    StrategyVersionInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError, AppQueryError
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.strategy import (
    approve_strategy_review,
    deprecate_strategy_version,
    diff_strategy_version,
    get_active_strategy,
    get_strategy_version_detail,
    list_strategy_governance_events,
    list_strategy_versions,
    reactivate_strategy_version,
    reject_strategy_review,
    router,
    submit_strategy_review,
    update_strategy,
    validate_strategy_version,
)
from ditto_apps.models import strategy as strategy_models
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import (
    GovernanceDecisionRequest,
    ReactivateStrategyRequest,
    SpecChangeResponse,
    StrategyActivePointerResponse,
    StrategyActiveResponse,
    StrategyGovernanceEventResponse,
    StrategyResponse,
    StrategySpecValidateRequest,
    StrategySpecValidationResponse,
    StrategyVersionDetailResponse,
    StrategyVersionDiffResponse,
    StrategyVersionResponse,
    StrategyVersionStateResponse,
    SubmitReviewRequest,
    UpdateStrategyRequest,
)
from fastapi import FastAPI
from pydantic import ValidationError

pytestmark = pytest.mark.asyncio


async def test_router_registers_only_evidence_gated_publish() -> None:
    """The public strategy API must not expose the seed/system publish fast-path."""
    publish_paths = {
        route.path
        for route in router.routes
        if "POST" in getattr(route, "methods", set())
        and route.path.endswith("/publish")
    }

    assert publish_paths == {"/strategies/{strategy_id}/versions/{version}/publish"}


async def test_router_registers_exact_version_detail_operation() -> None:
    """Immutable version detail is a dedicated read-only operation."""
    matches = [
        route
        for route in router.routes
        if getattr(route, "path", None)
        == "/strategies/{strategy_id}/versions/{version}"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(matches) == 1
    assert matches[0].operation_id == "design_strategy_version_detail"


async def test_router_registers_exact_governance_events_operation() -> None:
    """Append-only governance events use the frozen read-only operation id."""
    matches = [
        route
        for route in router.routes
        if getattr(route, "path", None) == "/strategies/{strategy_id}/events"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(matches) == 1
    assert matches[0].operation_id == "design_strategy_events"


async def test_governance_event_contract_has_exact_fields_and_bounded_limit() -> None:
    """The event DTO exposes no fabricated evidence/pointer fields."""
    response_model = getattr(strategy_models, "StrategyGovernanceEventResponse", None)
    assert response_model is not None
    assert tuple(response_model.model_fields) == (
        "event_id",
        "strategy_id",
        "event_type",
        "target_version",
        "decision_or_activation_kind",
        "actor",
        "reason",
        "occurred_at",
    )
    forbidden = {
        "bundle_hash",
        "evidence_hash",
        "previous_version",
        "pointer_revision",
    }
    assert forbidden.isdisjoint(response_model.model_fields)
    assert response_model.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        response_model(
            event_id="event-1",
            strategy_id="s1",
            event_type="decision",
            target_version=1,
            decision_or_activation_kind="approve",
            actor="alice",
            reason="ok",
            occurred_at="2026-07-31T00:00:00Z",
            bundle_hash="forbidden",
        )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    operation = app.openapi()["paths"]["/api/v1/strategies/{strategy_id}/events"]["get"]
    limit = next(item for item in operation["parameters"] if item["name"] == "limit")
    assert limit["schema"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 20,
        "title": "Limit",
    }
    detail_version = next(
        item
        for item in app.openapi()["paths"][
            "/api/v1/strategies/{strategy_id}/versions/{version}"
        ]["get"]["parameters"]
        if item["name"] == "version"
    )
    assert detail_version["schema"]["minimum"] == 1


_UpdateRoute = Callable[..., Awaitable[APIResponse[StrategyResponse]]]
_ListVersionsRoute = Callable[
    ..., Awaitable[APIResponse[list[StrategyVersionResponse]]]
]
_GetActiveRoute = Callable[..., Awaitable[APIResponse[StrategyActiveResponse]]]
_VersionDetailRoute = Callable[
    ..., Awaitable[APIResponse[StrategyVersionDetailResponse]]
]
_GovernanceEventsRoute = Callable[
    ..., Awaitable[APIResponse[list[StrategyGovernanceEventResponse]]]
]
_StateRoute = Callable[..., Awaitable[APIResponse[StrategyVersionStateResponse]]]
_ReactivateRoute = Callable[..., Awaitable[APIResponse[StrategyActivePointerResponse]]]


@pytest.fixture
def mock_update_handler() -> MagicMock:
    return MagicMock(spec=UpdateStrategyHandler)


@pytest.fixture
def mock_create_handler() -> MagicMock:
    return MagicMock(spec=CreateStrategyHandler)


@pytest.fixture
def mock_query_facade() -> MagicMock:
    return MagicMock(spec=StrategyQueryFacade)


@pytest.fixture
def mock_submit_handler() -> MagicMock:
    return MagicMock(spec=SubmitReviewHandler)


@pytest.fixture
def mock_approve_handler() -> MagicMock:
    return MagicMock(spec=ApproveReviewHandler)


@pytest.fixture
def mock_reject_handler() -> MagicMock:
    return MagicMock(spec=RejectReviewHandler)


@pytest.fixture
def mock_deprecate_handler() -> MagicMock:
    return MagicMock(spec=DeprecateStrategyHandler)


@pytest.fixture
def mock_reactivate_handler() -> MagicMock:
    return MagicMock(spec=ReactivateStrategyHandler)


@pytest.fixture(autouse=True)
def _inline_strategy_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr("ditto_apps.api.routes.strategy.run_blocking", run_inline)


def _unwrap(route: Callable[..., object]) -> Callable[..., object]:
    """Return the raw route callable behind the dishka @inject wrapper."""
    return cast(Callable[..., object], getattr(route, "__dishka_orig_func__", route))


async def _call_update(
    strategy_id: str,
    request: UpdateStrategyRequest,
    handler: UpdateStrategyHandler,
) -> APIResponse[StrategyResponse]:
    route = cast(_UpdateRoute, _unwrap(update_strategy))
    return await route(
        strategy_id=strategy_id,
        request=request,
        handler=handler,
        idempotency_key="unit.update-001",
    )


async def _call_list_versions(
    strategy_id: str,
    facade: StrategyQueryFacade,
) -> APIResponse[list[StrategyVersionResponse]]:
    route = cast(_ListVersionsRoute, _unwrap(list_strategy_versions))
    return await route(strategy_id=strategy_id, facade=facade)


async def _call_get_active(
    strategy_id: str,
    facade: StrategyQueryFacade,
) -> APIResponse[StrategyActiveResponse]:
    route = cast(_GetActiveRoute, _unwrap(get_active_strategy))
    return await route(strategy_id=strategy_id, facade=facade)


async def _call_version_detail(
    strategy_id: str,
    version: int,
    facade: StrategyQueryFacade,
) -> APIResponse[StrategyVersionDetailResponse]:
    route = cast(_VersionDetailRoute, _unwrap(get_strategy_version_detail))
    return await route(strategy_id=strategy_id, version=version, facade=facade)


async def _call_governance_events(
    strategy_id: str,
    facade: StrategyQueryFacade,
    *,
    after_event_id: str | None = None,
    limit: int = 20,
) -> APIResponse[list[StrategyGovernanceEventResponse]]:
    route = cast(_GovernanceEventsRoute, _unwrap(list_strategy_governance_events))
    return await route(
        strategy_id=strategy_id,
        facade=facade,
        after_event_id=after_event_id,
        limit=limit,
    )


def _state_info(
    *,
    strategy_id: str = "s1",
    version: int = 1,
    state: str = "review",
    review_outcome: str = "pending",
) -> StrategyVersionStateInfo:
    return StrategyVersionStateInfo(
        strategy_id=strategy_id,
        version=version,
        state=state,
        review_outcome=review_outcome,
    )


def _version_info(version: int = 2) -> StrategyVersionInfo:
    return StrategyVersionInfo(
        strategy_id="s1",
        version=version,
        parent_version=1,
        spec_hash="a" * 64,
        state="published",
        review_outcome="approved",
        created_at="2026-07-25T00:00:00Z",
    )


def _active_info() -> StrategyActiveInfo:
    return StrategyActiveInfo(
        strategy_id="s1",
        active_version=2,
        pointer_revision=3,
        spec=StrategySpecInfo(
            strategy_id="s1",
            name="Test",
            spec_json={},
            version=2,
            status="active",
        ),
    )


async def _call_submit_review(
    strategy_id: str,
    version: int,
    request: SubmitReviewRequest,
    handler: SubmitReviewHandler,
) -> APIResponse[StrategyVersionStateResponse]:
    route = cast(_StateRoute, _unwrap(submit_strategy_review))
    return await route(
        strategy_id=strategy_id,
        version=version,
        request=request,
        handler=handler,
        idempotency_key="unit.submit-review-001",
    )


async def _call_decision(
    route_fn: Callable[..., object],
    *,
    strategy_id: str,
    version: int,
    request: GovernanceDecisionRequest,
    handler: object,
) -> APIResponse[StrategyVersionStateResponse]:
    route = cast(_StateRoute, _unwrap(route_fn))
    return await route(
        strategy_id=strategy_id,
        version=version,
        request=request,
        handler=handler,
        idempotency_key="unit.governance-decision-001",
    )


async def _call_reactivate(
    strategy_id: str,
    version: int,
    request: ReactivateStrategyRequest,
    handler: ReactivateStrategyHandler,
) -> APIResponse[StrategyActivePointerResponse]:
    route = cast(_ReactivateRoute, _unwrap(reactivate_strategy_version))
    return await route(
        strategy_id=strategy_id,
        version=version,
        request=request,
        handler=handler,
        idempotency_key="unit.reactivate-001",
    )


class TestUpdateStrategyErrorMapping:
    """PUT /strategies/{id} — ValueError 错误映射."""

    async def test_update_not_found_returns_404(
        self,
        mock_update_handler: MagicMock,
    ) -> None:
        """策略不存在 -> 404."""
        mock_update_handler.handle.side_effect = AppCommandError(
            "Strategy not found: missing"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_update(
                "missing",
                UpdateStrategyRequest(name="x", spec_json={}, version=1, tags=[]),
                mock_update_handler,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    async def test_update_version_conflict_returns_409(
        self,
        mock_update_handler: MagicMock,
    ) -> None:
        """版本冲突 -> 409."""
        mock_update_handler.handle.side_effect = AppCommandError(
            "Version conflict for strategy s1: expected 2, got 3"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_update(
                "s1",
                UpdateStrategyRequest(name="x", spec_json={}, version=3, tags=[]),
                mock_update_handler,
            )
        assert exc_info.value.status_code == 409
        assert "conflict" in exc_info.value.message.lower()


class TestListStrategyVersions:
    """GET /strategies/{id}/versions — governance 版本历史."""

    async def test_returns_version_responses(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.list_versions.return_value = [
            _version_info(2),
            _version_info(1),
        ]

        result = await _call_list_versions("s1", mock_query_facade)

        assert result.data == [
            StrategyVersionResponse(
                strategy_id="s1",
                version=2,
                parent_version=1,
                spec_hash="a" * 64,
                state="published",
                review_outcome="approved",
                created_at="2026-07-25T00:00:00Z",
            ),
            StrategyVersionResponse(
                strategy_id="s1",
                version=1,
                parent_version=1,
                spec_hash="a" * 64,
                state="published",
                review_outcome="approved",
                created_at="2026-07-25T00:00:00Z",
            ),
        ]
        mock_query_facade.list_versions.assert_called_once_with("s1")

    async def test_returns_empty_list(self, mock_query_facade: MagicMock) -> None:
        mock_query_facade.list_versions.return_value = []

        result = await _call_list_versions("s1", mock_query_facade)

        assert result.data == []


class TestGetActiveStrategy:
    """GET /strategies/{id}/active — active pointer + payload."""

    async def test_returns_active_response(self, mock_query_facade: MagicMock) -> None:
        mock_query_facade.get_active.return_value = _active_info()

        result = await _call_get_active("s1", mock_query_facade)

        assert result.data == StrategyActiveResponse(
            strategy_id="s1",
            active_version=2,
            pointer_revision=3,
            spec=StrategyResponse(
                strategy_id="s1",
                name="Test",
                spec_json={},
                version=2,
                status="active",
            ),
        )
        mock_query_facade.get_active.assert_called_once_with("s1")

    async def test_returns_404_when_no_active_pointer(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.get_active.return_value = None

        with pytest.raises(APIError) as exc_info:
            await _call_get_active("s1", mock_query_facade)

        assert exc_info.value.status_code == 404


class TestStrategyVersionDetail:
    """GET immutable version detail maps the application DTO and exact 404."""

    async def test_returns_canonical_detail(self, mock_query_facade: MagicMock) -> None:
        mock_query_facade.get_version_detail.return_value = StrategyVersionDetailInfo(
            strategy_id="s1",
            version=2,
            canonical_spec={"selector": {"top_k": 5}},
            spec_hash="a" * 64,
            parent_version=1,
            state="review",
            review_outcome="approved",
            created_at="2026-07-31T00:00:00Z",
        )

        result = await _call_version_detail("s1", 2, mock_query_facade)

        assert result.data == StrategyVersionDetailResponse(
            strategy_id="s1",
            version=2,
            canonical_spec={"selector": {"top_k": 5}},
            spec_hash="a" * 64,
            parent_version=1,
            state="review",
            review_outcome="approved",
            created_at="2026-07-31T00:00:00Z",
        )

    async def test_missing_version_is_exact_404(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.get_version_detail.return_value = None

        with pytest.raises(APIError) as info:
            await _call_version_detail("s1", 99, mock_query_facade)

        assert info.value.status_code == 404
        assert info.value.error_code == "STRATEGY_VERSION_NOT_FOUND"


class TestStrategyGovernanceEvents:
    """GET governance events preserves stable cursor and typed errors."""

    async def test_returns_exact_append_only_projection(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.list_governance_events.return_value = [
            StrategyGovernanceEventInfo(
                event_id="event-1",
                strategy_id="s1",
                event_type="decision",
                target_version=2,
                decision_or_activation_kind="approve",
                actor="alice",
                reason="ok",
                occurred_at="2026-07-31T00:00:00Z",
            )
        ]

        result = await _call_governance_events(
            "s1", mock_query_facade, after_event_id="event-0", limit=10
        )

        assert result.data == [
            StrategyGovernanceEventResponse(
                event_id="event-1",
                strategy_id="s1",
                event_type="decision",
                target_version=2,
                decision_or_activation_kind="approve",
                actor="alice",
                reason="ok",
                occurred_at="2026-07-31T00:00:00Z",
            )
        ]
        mock_query_facade.list_governance_events.assert_called_once_with(
            "s1", after_event_id="event-0", limit=10
        )

    @pytest.mark.parametrize(
        ("code", "status"),
        [("INVALID_EVENT_CURSOR", 422), ("STRATEGY_NOT_FOUND", 404)],
    )
    async def test_maps_typed_query_errors(
        self,
        mock_query_facade: MagicMock,
        code: str,
        status: int,
    ) -> None:
        mock_query_facade.list_governance_events.side_effect = AppQueryError(
            code, details={"code": code}
        )

        with pytest.raises(APIError) as info:
            await _call_governance_events("s1", mock_query_facade)

        assert info.value.status_code == status
        assert info.value.error_code == code


class TestSubmitStrategyReview:
    """POST /strategies/{id}/versions/{v}/submit-review — state-machine + 错误映射."""

    async def test_returns_state_response(self, mock_submit_handler: MagicMock) -> None:
        mock_submit_handler.handle.return_value = _state_info()

        result = await _call_submit_review(
            "s1",
            1,
            SubmitReviewRequest(bundle_hash="a" * 64, actor="alice", reason="ok"),
            mock_submit_handler,
        )

        assert result.data == StrategyVersionStateResponse(
            strategy_id="s1", version=1, state="review", review_outcome="pending"
        )

    async def test_not_found_returns_404(self, mock_submit_handler: MagicMock) -> None:
        mock_submit_handler.handle.side_effect = AppCommandError(
            "Strategy version not found: s1 v1"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_submit_review(
                "s1",
                1,
                SubmitReviewRequest(bundle_hash="a" * 64, actor="alice", reason="ok"),
                mock_submit_handler,
            )
        assert exc_info.value.status_code == 404

    async def test_revision_conflict_returns_409(
        self, mock_submit_handler: MagicMock
    ) -> None:
        mock_submit_handler.handle.side_effect = AppCommandError(
            "Strategy revision conflict for s1 v1: CAS missed"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_submit_review(
                "s1",
                1,
                SubmitReviewRequest(bundle_hash="a" * 64, actor="alice", reason="ok"),
                mock_submit_handler,
            )
        assert exc_info.value.status_code == 409

    async def test_invalid_transition_returns_400(
        self, mock_submit_handler: MagicMock
    ) -> None:
        mock_submit_handler.handle.side_effect = AppCommandError(
            "Invalid governance transition for s1 v1: requires draft/pending"
        )
        with pytest.raises(APIError) as exc_info:
            await _call_submit_review(
                "s1",
                1,
                SubmitReviewRequest(bundle_hash="a" * 64, actor="alice", reason="ok"),
                mock_submit_handler,
            )
        assert exc_info.value.status_code == 400


class TestOtherGovernanceDecisions:
    """approve / reject / deprecate share the submit-review route shape."""

    async def test_approve_returns_state(self, mock_approve_handler: MagicMock) -> None:
        mock_approve_handler.handle.return_value = _state_info(
            state="review", review_outcome="approved"
        )
        result = await _call_decision(
            approve_strategy_review,
            strategy_id="s1",
            version=1,
            request=GovernanceDecisionRequest(actor="bob", reason="lgtg"),
            handler=mock_approve_handler,
        )
        assert result.data.review_outcome == "approved"

    async def test_reject_returns_state(self, mock_reject_handler: MagicMock) -> None:
        mock_reject_handler.handle.return_value = _state_info(
            state="review", review_outcome="rejected"
        )
        result = await _call_decision(
            reject_strategy_review,
            strategy_id="s1",
            version=1,
            request=GovernanceDecisionRequest(actor="bob", reason="no"),
            handler=mock_reject_handler,
        )
        assert result.data.review_outcome == "rejected"

    async def test_deprecate_returns_state(
        self, mock_deprecate_handler: MagicMock
    ) -> None:
        mock_deprecate_handler.handle.return_value = _state_info(
            state="deprecated", review_outcome="approved"
        )
        result = await _call_decision(
            deprecate_strategy_version,
            strategy_id="s1",
            version=1,
            request=GovernanceDecisionRequest(actor="bob", reason="retire"),
            handler=mock_deprecate_handler,
        )
        assert result.data.state == "deprecated"


class TestReactivateStrategyVersion:
    """POST /strategies/{id}/versions/{v}/reactivate — expected pointer CAS."""

    async def test_request_strips_reason_and_impact_but_not_confirmation(self) -> None:
        request = ReactivateStrategyRequest(
            actor="carol",
            reason="  rollback  ",
            confirmation=" exact confirmation ",
            impact_summary="  restore prior production behavior  ",
            expected_pointer_revision=3,
        )

        assert request.reason == "rollback"
        assert request.impact_summary == "restore prior production behavior"
        assert request.confirmation == " exact confirmation "

    @pytest.mark.parametrize(
        ("reason", "impact_summary"),
        [(" ", "restore prior behavior"), ("rollback", "\t")],
    )
    async def test_request_rejects_blank_reason_or_impact(
        self,
        reason: str,
        impact_summary: str,
    ) -> None:
        with pytest.raises(ValidationError):
            ReactivateStrategyRequest(
                actor="carol",
                reason=reason,
                confirmation="strategy:reactivate:s1@2:pointer-revision:3:confirm",
                impact_summary=impact_summary,
                expected_pointer_revision=3,
            )

    async def test_passes_expected_pointer_revision(
        self, mock_reactivate_handler: MagicMock
    ) -> None:
        mock_reactivate_handler.handle.return_value = StrategyActivePointerInfo(
            strategy_id="s1",
            active_version=2,
            pointer_revision=4,
        )

        result = await _call_reactivate(
            "s1",
            2,
            ReactivateStrategyRequest(
                actor="carol",
                reason="rollback",
                confirmation="strategy:reactivate:s1@2:pointer-revision:3:confirm",
                impact_summary="restore prior production behavior",
                expected_pointer_revision=3,
            ),
            mock_reactivate_handler,
        )

        assert result.data == StrategyActivePointerResponse(
            strategy_id="s1", active_version=2, pointer_revision=4
        )
        cmd = mock_reactivate_handler.handle.call_args.args[0]
        assert cmd.expected_pointer_revision == 3
        assert cmd.actor == "carol"
        assert cmd.confirmation == (
            "strategy:reactivate:s1@2:pointer-revision:3:confirm"
        )
        assert cmd.impact_summary == "restore prior production behavior"

    async def test_stale_pointer_conflict_returns_409(
        self, mock_reactivate_handler: MagicMock
    ) -> None:
        mock_reactivate_handler.handle.side_effect = AppCommandError(
            "Strategy revision conflict for s1 v2: pointer CAS missed",
            details={"code": "STRATEGY_REVISION_CONFLICT"},
        )
        with pytest.raises(APIError) as exc_info:
            await _call_reactivate(
                "s1",
                2,
                ReactivateStrategyRequest(
                    actor="carol",
                    reason="rollback",
                    confirmation=(
                        "strategy:reactivate:s1@2:pointer-revision:3:confirm"
                    ),
                    impact_summary="restore prior production behavior",
                    expected_pointer_revision=3,
                ),
                mock_reactivate_handler,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.error_code == "STRATEGY_REVISION_CONFLICT"

    @pytest.mark.parametrize(
        ("code", "expected_status"),
        [
            ("STRATEGY_REACTIVATION_CONFIRMATION_MISMATCH", 422),
            ("STRATEGY_REACTIVATION_INPUT_INVALID", 422),
            ("STRATEGY_INVALID_TRANSITION", 422),
            ("STRATEGY_VERSION_NOT_FOUND", 404),
        ],
    )
    async def test_maps_typed_reactivation_failures(
        self,
        mock_reactivate_handler: MagicMock,
        code: str,
        expected_status: int,
    ) -> None:
        mock_reactivate_handler.handle.side_effect = AppCommandError(
            f"reactivation failed: {code}",
            details={"code": code},
        )

        with pytest.raises(APIError) as exc_info:
            await _call_reactivate(
                "s1",
                2,
                ReactivateStrategyRequest(
                    actor="carol",
                    reason="rollback",
                    confirmation=(
                        "strategy:reactivate:s1@2:pointer-revision:3:confirm"
                    ),
                    impact_summary="restore prior production behavior",
                    expected_pointer_revision=3,
                ),
                mock_reactivate_handler,
            )

        assert exc_info.value.status_code == expected_status
        if expected_status == 422:
            assert exc_info.value.error_code == code


_ValidateRoute = Callable[..., Awaitable[APIResponse[StrategySpecValidationResponse]]]
_DiffRoute = Callable[..., Awaitable[APIResponse[StrategyVersionDiffResponse]]]


def _validation_info(
    *,
    valid: bool = True,
    changed: bool = False,
) -> StrategySpecValidationInfo:
    return StrategySpecValidationInfo(
        strategy_id="s1",
        version=2,
        canonical_hash="c" * 64 if valid else "",
        base_spec_hash="a" * 64,
        changed=changed,
        valid=valid,
        errors=() if valid else ("bad spec",),
    )


def _diff_info(
    *,
    parent: int | None = 1,
    changed: bool = True,
) -> StrategyVersionDiffInfo:
    return StrategyVersionDiffInfo(
        strategy_id="s1",
        version=2,
        parent_version=parent,
        base_spec_hash="p" * 64 if parent is not None else "",
        target_spec_hash="c" * 64,
        changed=changed,
        changes=(
            SpecChange(
                path="pipeline.nodes[0].config.k",
                op="changed",
                old_value=5,
                new_value=10,
            ),
        )
        if changed
        else (),
    )


async def _call_validate(
    strategy_id: str,
    version: int,
    request: StrategySpecValidateRequest,
    facade: StrategyQueryFacade,
) -> APIResponse[StrategySpecValidationResponse]:
    route = cast(_ValidateRoute, _unwrap(validate_strategy_version))
    return await route(
        strategy_id=strategy_id, version=version, request=request, facade=facade
    )


async def _call_diff(
    strategy_id: str,
    version: int,
    facade: StrategyQueryFacade,
) -> APIResponse[StrategyVersionDiffResponse]:
    route = cast(_DiffRoute, _unwrap(diff_strategy_version))
    return await route(strategy_id=strategy_id, version=version, facade=facade)


class TestValidateStrategyVersion:
    """POST /strategies/{id}/versions/{v}/validate — candidate spec pre-save 校验."""

    async def test_valid_candidate_returns_validation_response(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.validate_spec.return_value = _validation_info(
            valid=True, changed=True
        )

        result = await _call_validate(
            "s1",
            2,
            StrategySpecValidateRequest(spec_json={"template": "etf_rotation"}),
            mock_query_facade,
        )

        assert result.data == StrategySpecValidationResponse(
            strategy_id="s1",
            version=2,
            canonical_hash="c" * 64,
            base_spec_hash="a" * 64,
            changed=True,
            valid=True,
            errors=[],
        )
        mock_query_facade.validate_spec.assert_called_once_with(
            "s1", 2, {"template": "etf_rotation"}
        )

    async def test_invalid_candidate_returns_valid_false(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.validate_spec.return_value = _validation_info(
            valid=False, changed=False
        )

        result = await _call_validate(
            "s1",
            2,
            StrategySpecValidateRequest(spec_json={"template": "x"}),
            mock_query_facade,
        )

        assert result.data.valid is False
        assert result.data.changed is False
        assert result.data.canonical_hash == ""
        assert result.data.errors == ["bad spec"]

    async def test_version_not_found_returns_404(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.validate_spec.return_value = None

        with pytest.raises(APIError) as exc_info:
            await _call_validate(
                "s1",
                99,
                StrategySpecValidateRequest(spec_json={}),
                mock_query_facade,
            )

        assert exc_info.value.status_code == 404


class TestDiffStrategyVersion:
    """GET /strategies/{id}/versions/{v}/diff — version vs parent spec diff."""

    async def test_returns_diff_response_with_changes(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.diff_version.return_value = _diff_info(parent=1, changed=True)

        result = await _call_diff("s1", 2, mock_query_facade)

        assert result.data == StrategyVersionDiffResponse(
            strategy_id="s1",
            version=2,
            parent_version=1,
            base_spec_hash="p" * 64,
            target_spec_hash="c" * 64,
            changed=True,
            changes=[
                SpecChangeResponse(
                    path="pipeline.nodes[0].config.k",
                    op="changed",
                    old=5,
                    new=10,
                ),
            ],
        )
        mock_query_facade.diff_version.assert_called_once_with("s1", 2)

    async def test_first_version_returns_empty_changes(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.diff_version.return_value = _diff_info(
            parent=None, changed=False
        )

        result = await _call_diff("s1", 1, mock_query_facade)

        assert result.data.parent_version is None
        assert result.data.changes == []
        assert result.data.changed is False

    async def test_version_not_found_returns_404(
        self, mock_query_facade: MagicMock
    ) -> None:
        mock_query_facade.diff_version.return_value = None

        with pytest.raises(APIError) as exc_info:
            await _call_diff("s1", 99, mock_query_facade)

        assert exc_info.value.status_code == 404
