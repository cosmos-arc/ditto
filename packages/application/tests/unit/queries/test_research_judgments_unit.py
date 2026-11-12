"""Exact research judgment reads for reopening saved comparison conclusions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.research_judgments import (
    ResearchJudgmentQueryService,
    ResearchJudgmentSummary,
)
from ditto_application.research_judgment_contracts import ResearchJudgmentView

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)


@dataclass(frozen=True)
class _StubView:
    judgment_id: str
    run_ids: tuple[str, ...]
    judgment: str
    created_at: datetime
    strategy_id: str | None = None
    strategy_version: int | None = None

    @property
    def schema_version(self) -> int:
        return 1


_VIEWS = (
    _StubView(
        judgment_id="research-judgment:sha256:" + "1" * 64,
        run_ids=("sys-fx-nav-001", "sys-fx-nav-002"),
        judgment="同口径可比; 001 回撤更浅",
        created_at=_CREATED,
    ),
    _StubView(
        judgment_id="research-judgment:sha256:" + "2" * 64,
        run_ids=("sys-fx-nav-003",),
        judgment="转入策略版本验证",
        created_at=datetime(2026, 11, 11, 15, 5, tzinfo=UTC),
        strategy_id="sys-fx-etf-rotation",
        strategy_version=2,
    ),
)


class _Reader:
    def get(self, judgment_id: str) -> ResearchJudgmentView | None:
        for view in _VIEWS:
            if view.judgment_id == judgment_id:
                return view
        return None

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgmentView, ...]:
        return _VIEWS[:limit]


def test_get_returns_one_exact_judgment() -> None:
    service = ResearchJudgmentQueryService(_Reader())

    view = service.get("research-judgment:sha256:" + "2" * 64)

    assert isinstance(view, _StubView)
    assert view.strategy_id == "sys-fx-etf-rotation"


def test_get_raises_a_typed_error_for_unknown_judgments() -> None:
    service = ResearchJudgmentQueryService(_Reader())

    with pytest.raises(AppQueryError) as excinfo:
        service.get("research-judgment:sha256:" + "0" * 64)

    assert excinfo.value.details["reason"] == "research_judgment_not_found"


def test_get_rejects_blank_identities() -> None:
    service = ResearchJudgmentQueryService(_Reader())

    with pytest.raises(AppQueryError) as excinfo:
        service.get("  ")

    assert excinfo.value.details["reason"] == "invalid_research_judgment_id"


def test_list_recent_returns_reopen_summaries() -> None:
    service = ResearchJudgmentQueryService(_Reader())

    summaries = service.list_recent(limit=10)

    assert summaries == (
        ResearchJudgmentSummary(
            judgment_id="research-judgment:sha256:" + "1" * 64,
            run_ids=("sys-fx-nav-001", "sys-fx-nav-002"),
            created_at=_CREATED,
            judgment="同口径可比; 001 回撤更浅",
            strategy_id=None,
            strategy_version=None,
        ),
        ResearchJudgmentSummary(
            judgment_id="research-judgment:sha256:" + "2" * 64,
            run_ids=("sys-fx-nav-003",),
            created_at=datetime(2026, 11, 11, 15, 5, tzinfo=UTC),
            judgment="转入策略版本验证",
            strategy_id="sys-fx-etf-rotation",
            strategy_version=2,
        ),
    )


def test_list_recent_rejects_non_positive_limits() -> None:
    service = ResearchJudgmentQueryService(_Reader())

    with pytest.raises(AppQueryError) as excinfo:
        service.list_recent(limit=0)

    assert excinfo.value.details["reason"] == "invalid_research_judgment_limit"
