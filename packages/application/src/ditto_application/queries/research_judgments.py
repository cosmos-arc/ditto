"""Exact research judgment reads for reopening saved comparison conclusions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_application.exceptions import AppQueryError
from ditto_application.research_judgment_contracts import (
    ResearchJudgmentReader,
    ResearchJudgmentView,
)

__all__ = ["ResearchJudgmentQueryService", "ResearchJudgmentSummary"]


@dataclass(frozen=True, slots=True)
class ResearchJudgmentSummary:
    """Compact judgment summary for the reopen list."""

    judgment_id: str
    run_ids: tuple[str, ...]
    created_at: datetime
    judgment: str
    strategy_id: str | None
    strategy_version: int | None


class ResearchJudgmentQueryService:
    """Read only exact persisted judgments; never consult run artifacts."""

    def __init__(self, reader: ResearchJudgmentReader) -> None:
        self._reader = reader

    def get(self, judgment_id: str) -> ResearchJudgmentView:
        """Return one exact persisted judgment or a typed query error."""
        if not judgment_id.strip():
            raise AppQueryError(
                "research judgment judgment_id must be non-empty",
                details={"reason": "invalid_research_judgment_id"},
            )
        value = self._reader.get(judgment_id)
        if value is None:
            raise AppQueryError(
                f"research judgment not found: {judgment_id}",
                details={
                    "reason": "research_judgment_not_found",
                    "judgment_id": judgment_id,
                },
            )
        return value

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgmentSummary, ...]:
        """List the newest saved judgments as reopen summaries."""
        return tuple(
            _summary(item) for item in self._reader.list_recent(limit=_limit(limit))
        )


def _summary(item: ResearchJudgmentView) -> ResearchJudgmentSummary:
    return ResearchJudgmentSummary(
        judgment_id=item.judgment_id,
        run_ids=item.run_ids,
        created_at=item.created_at,
        judgment=item.judgment,
        strategy_id=item.strategy_id,
        strategy_version=item.strategy_version,
    )


def _limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        raise AppQueryError(
            "research judgment list limit must be positive",
            details={"reason": "invalid_research_judgment_limit"},
        )
    return limit
