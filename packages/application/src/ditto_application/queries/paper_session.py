"""Exact read model for one formal paper session."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.paper.session import PaperSessionStorePort

from ditto_application.exceptions import AppQueryError
from ditto_application.paper_contracts import (
    PaperExecutionInfo,
    PaperReconciliationInfo,
    PaperSessionInfo,
    to_paper_execution_info,
    to_paper_reconciliation_info,
    to_paper_session_info,
)

__all__ = ["GetPaperSessionQuery", "PaperSessionReadModel"]


@dataclass(frozen=True, kw_only=True)
class PaperSessionReadModel:
    """Session state, execution history, and latest EOD evidence."""

    session: PaperSessionInfo
    executions: tuple[PaperExecutionInfo, ...]
    latest_reconciliation: PaperReconciliationInfo | None


class GetPaperSessionQuery:
    """Read persisted state only; never infer a synthetic session."""

    def __init__(self, *, store: PaperSessionStorePort) -> None:
        self._store = store

    def get(self, session_id: str) -> PaperSessionReadModel:
        """Return one exact session or fail closed when it is absent."""
        session = self._store.get_session(session_id)
        if session is None:
            raise AppQueryError(
                "paper session not found",
                code="PAPER_SESSION_NOT_FOUND",
                session_id=session_id,
            )
        latest_reconciliation = self._store.latest_reconciliation(session_id)
        return PaperSessionReadModel(
            session=to_paper_session_info(session),
            executions=tuple(
                to_paper_execution_info(record)
                for record in self._store.list_executions(session_id)
            ),
            latest_reconciliation=(
                to_paper_reconciliation_info(latest_reconciliation)
                if latest_reconciliation is not None
                else None
            ),
        )
