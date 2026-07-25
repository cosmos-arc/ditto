"""Tests for strategy governance command handlers — state-machine boundary.

The handlers are thin seams over :class:`GovernanceService`: they mint a stable
event id / decided_at timestamp, forward the typed decision, map the three
governance failure modes (unknown version, CAS conflict, illegal transition)
into a single typed :class:`AppCommandError` so the API layer can map status
codes from the message, and return an application-owned read model so capability
types never leak past the boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.strategy_governance import (
    ApproveReviewCommand,
    ApproveReviewHandler,
    DeprecateStrategyCommand,
    DeprecateStrategyHandler,
    ReactivateStrategyCommand,
    ReactivateStrategyHandler,
    RejectReviewCommand,
    RejectReviewHandler,
    SubmitReviewCommand,
    SubmitReviewHandler,
)
from ditto_application.contracts import (
    StrategyActivePointerInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError
from ditto_strategy.governance.models import (
    ReviewOutcome,
    StrategyActivePointer,
    StrategyDecision,
    StrategyVersionState,
    StrategyVersionStateRecord,
)
from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    StrategyGovernanceCasConflict,
)


def _state_record() -> StrategyVersionStateRecord:
    return StrategyVersionStateRecord(
        strategy_id="s1",
        version=1,
        state=StrategyVersionState.REVIEW,
        review_outcome=ReviewOutcome.PENDING,
        state_revision=1,
    )


def _state_info() -> StrategyVersionStateInfo:
    """Application projection of ``_state_record`` (what the handler returns)."""
    return StrategyVersionStateInfo(
        strategy_id="s1",
        version=1,
        state="review",
        review_outcome="pending",
    )


def _pointer() -> StrategyActivePointer:
    return StrategyActivePointer(
        strategy_id="s1",
        active_version=1,
        pointer_revision=1,
        activation_event_id="e1",
    )


def _pointer_info() -> StrategyActivePointerInfo:
    """Application projection of ``_pointer`` (what the handler returns)."""
    return StrategyActivePointerInfo(
        strategy_id="s1",
        active_version=1,
        pointer_revision=1,
    )


_ErrorFactory = Callable[[], Exception]


@pytest.mark.parametrize(
    ("exc_factory", "keyword"),
    [
        (lambda: StrategyGovernanceError("governance version not found"), "not found"),
        (
            lambda: StrategyGovernanceCasConflict("pointer CAS missed revision"),
            "conflict",
        ),
        (lambda: ValueError("requires published/approved"), "transition"),
    ],
    ids=["not_found", "cas_conflict", "invalid_transition"],
)
def test_submit_review_maps_governance_errors(
    exc_factory: _ErrorFactory,
    keyword: str,
) -> None:
    """All three governance failure modes become a typed AppCommandError."""
    governance = MagicMock(spec=GovernanceService)
    governance.submit_review.side_effect = exc_factory()
    handler = SubmitReviewHandler(governance)

    with pytest.raises(AppCommandError) as info:
        handler.handle(
            SubmitReviewCommand(strategy_id="s1", version=1, actor="alice", reason="ok")
        )

    assert keyword in str(info.value).lower()


class TestSubmitReviewHandler:
    """submit_review forwards actor/reason with a stable event id."""

    def test_success_returns_application_state_info(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.submit_review.return_value = _state_record()
        handler = SubmitReviewHandler(governance)

        result = handler.handle(
            SubmitReviewCommand(strategy_id="s1", version=1, actor="alice", reason="ok")
        )

        assert result == _state_info()
        call = governance.submit_review.call_args
        assert call.args == ("s1", 1)
        assert call.kwargs["actor"] == "alice"
        assert call.kwargs["reason"] == "ok"
        assert call.kwargs["event_id"].startswith("s1:1:submit_review:")
        assert call.kwargs["decided_at"]


class TestApproveReviewHandler:
    """approve forwards to GovernanceService.approve."""

    def test_success_returns_application_state_info(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.approve.return_value = _state_record()
        handler = ApproveReviewHandler(governance)

        result = handler.handle(
            ApproveReviewCommand(
                strategy_id="s1", version=1, actor="bob", reason="lgtg"
            )
        )

        assert result == _state_info()
        call = governance.approve.call_args
        assert call.args == ("s1", 1)
        assert call.kwargs["actor"] == "bob"
        assert call.kwargs["event_id"].startswith("s1:1:approve:")


class TestRejectReviewHandler:
    """reject forwards to GovernanceService.reject."""

    def test_success_returns_application_state_info(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.reject.return_value = _state_record()
        handler = RejectReviewHandler(governance)

        result = handler.handle(
            RejectReviewCommand(strategy_id="s1", version=1, actor="bob", reason="no")
        )

        assert result == _state_info()
        call = governance.reject.call_args
        assert call.args == ("s1", 1)
        assert call.kwargs["actor"] == "bob"
        assert call.kwargs["event_id"].startswith("s1:1:reject:")


class TestDeprecateStrategyHandler:
    """deprecate forwards to GovernanceService.deprecate."""

    def test_success_returns_application_state_info(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.deprecate.return_value = _state_record()
        handler = DeprecateStrategyHandler(governance)

        result = handler.handle(
            DeprecateStrategyCommand(
                strategy_id="s1", version=1, actor="bob", reason="retire"
            )
        )

        assert result == _state_info()
        call = governance.deprecate.call_args
        assert call.args == ("s1", 1)
        assert call.kwargs["actor"] == "bob"
        assert call.kwargs["event_id"].startswith("s1:1:deprecate:")


class TestReactivateStrategyHandler:
    """reactivate forwards expected_pointer_revision for optimistic-pointer CAS."""

    def test_success_returns_application_pointer_info(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.activate.return_value = _pointer()
        handler = ReactivateStrategyHandler(governance)

        result = handler.handle(
            ReactivateStrategyCommand(
                strategy_id="s1",
                version=2,
                actor="carol",
                reason="rollback",
                expected_pointer_revision=3,
            )
        )

        assert result == _pointer_info()
        call = governance.activate.call_args
        assert call.args[0] == "s1"
        assert call.args[1] == 2
        assert call.kwargs["expected_pointer_revision"] == 3
        event = call.args[2]
        assert event.event_id.startswith("s1:2:reactivate:")
        assert event.actor == "carol"
        assert event.activation_kind is StrategyDecision.REACTIVATE

    def test_stale_pointer_conflict_is_mapped(self) -> None:
        governance = MagicMock(spec=GovernanceService)
        governance.activate.side_effect = StrategyGovernanceCasConflict("stale")
        handler = ReactivateStrategyHandler(governance)

        with pytest.raises(AppCommandError) as info:
            handler.handle(
                ReactivateStrategyCommand(
                    strategy_id="s1",
                    version=2,
                    actor="carol",
                    reason="rollback",
                    expected_pointer_revision=3,
                )
            )

        assert "conflict" in str(info.value).lower()
