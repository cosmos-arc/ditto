"""Exact Research Case reads for reopening handed-off research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_strategy.selection.store import SelectionRunReader

from ditto_application.exceptions import AppQueryError
from ditto_application.research_case_contracts import (
    ResearchCaseReader,
    ResearchCaseView,
)

__all__ = [
    "ResearchCaseQueryService",
    "ResearchCaseSummary",
]


@dataclass(frozen=True, slots=True)
class ResearchCaseSummary:
    """Compact handoff summary for research-entry lists."""

    case_id: str
    objective: str
    selection_run_id: str
    asset_kind: str
    as_of: datetime
    selection_status: str
    candidate_count: int


class ResearchCaseQueryService:
    """Read only exact persisted cases; never consult live selection state."""

    def __init__(self, reader: ResearchCaseReader, runs: SelectionRunReader) -> None:
        self._reader = reader
        self._runs = runs

    def get(self, case_id: str) -> ResearchCaseView:
        """Return one exact persisted case or a typed query-boundary error."""
        if not case_id.strip():
            raise AppQueryError(
                "research case case_id must be non-empty",
                details={"reason": "invalid_research_case_id"},
            )
        value = self._reader.get(case_id)
        if value is None:
            raise AppQueryError(
                f"research case not found: {case_id}",
                details={"reason": "research_case_not_found", "case_id": case_id},
            )
        return value

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchCaseSummary, ...]:
        """List the newest handed-off cases as research-entry summaries."""
        return tuple(
            _summary(item) for item in self._reader.list_recent(limit=_limit(limit))
        )

    def list_by_run(
        self, selection_run_id: str, *, limit: int = 20
    ) -> tuple[ResearchCaseSummary, ...]:
        """List cases handed off from one exact SelectionRun."""
        if not selection_run_id.strip():
            raise AppQueryError(
                "selection run_id must be non-empty",
                details={"reason": "invalid_selection_run_id"},
            )
        # 未知 run 返回 404 而不是空列表：空列表会被误读为「该 run 尚无
        # 用例」，只有真实存在的 run 才有可信的空集。
        if self._runs.get(selection_run_id) is None:
            raise AppQueryError(
                f"selection run not found: {selection_run_id}",
                details={
                    "reason": "selection_run_not_found",
                    "run_id": selection_run_id,
                },
            )
        return tuple(
            _summary(item)
            for item in self._reader.list_by_run(selection_run_id, limit=_limit(limit))
        )


def _summary(value: ResearchCaseView) -> ResearchCaseSummary:
    return ResearchCaseSummary(
        case_id=value.case_id,
        objective=value.objective,
        selection_run_id=value.selection_run_id,
        asset_kind=value.asset_kind,
        as_of=value.as_of,
        selection_status=value.selection_status,
        candidate_count=len(value.candidate_instrument_ids),
    )


def _limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        raise AppQueryError(
            "research case list limit must be a positive integer",
            details={"reason": "invalid_research_case_limit"},
        )
    return limit
