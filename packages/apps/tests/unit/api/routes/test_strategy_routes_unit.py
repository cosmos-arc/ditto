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
    StrategyActiveInfo,
    StrategyActivePointerInfo,
    StrategySpecInfo,
    StrategyVersionInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.strategy import (
    approve_strategy_review,
    deprecate_strategy_version,
    get_active_strategy,
    list_strategy_versions,
    reactivate_strategy_version,
    reject_strategy_review,
    router,
    submit_strategy_review,
    update_strategy,
)
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import (
    GovernanceDecisionRequest,
    ReactivateStrategyRequest,
    StrategyActivePointerResponse,
    StrategyActiveResponse,
    StrategyResponse,
    StrategyVersionResponse,
    StrategyVersionStateResponse,
    UpdateStrategyRequest,
)
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


_UpdateRoute = Callable[..., Awaitable[APIResponse[StrategyResponse]]]
_ListVersionsRoute = Callable[
    ..., Awaitable[APIResponse[list[StrategyVersionResponse]]]
]
_GetActiveRoute = Callable[..., Awaitable[APIResponse[StrategyActiveResponse]]]
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
    return await route(strategy_id=strategy_id, request=request, handler=handler)


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
    request: GovernanceDecisionRequest,
    handler: SubmitReviewHandler,
) -> APIResponse[StrategyVersionStateResponse]:
    route = cast(_StateRoute, _unwrap(submit_strategy_review))
    return await route(
        strategy_id=strategy_id, version=version, request=request, handler=handler
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
        strategy_id=strategy_id, version=version, request=request, handler=handler
    )


async def _call_reactivate(
    strategy_id: str,
    version: int,
    request: ReactivateStrategyRequest,
    handler: ReactivateStrategyHandler,
) -> APIResponse[StrategyActivePointerResponse]:
    route = cast(_ReactivateRoute, _unwrap(reactivate_strategy_version))
    return await route(
        strategy_id=strategy_id, version=version, request=request, handler=handler
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


class TestSubmitStrategyReview:
    """POST /strategies/{id}/versions/{v}/submit-review — state-machine + 错误映射."""

    async def test_returns_state_response(self, mock_submit_handler: MagicMock) -> None:
        mock_submit_handler.handle.return_value = _state_info()

        result = await _call_submit_review(
            "s1",
            1,
            GovernanceDecisionRequest(actor="alice", reason="ok"),
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
                GovernanceDecisionRequest(actor="alice", reason="ok"),
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
                GovernanceDecisionRequest(actor="alice", reason="ok"),
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
                GovernanceDecisionRequest(actor="alice", reason="ok"),
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
