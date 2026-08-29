"""Apps-owned lifecycle for the isolated DecisionOpinion shadow store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ditto_agent.storage.sqlite.decision_opinion_store import (
    DecisionOpinionShadowDatabase,
    DecisionOpinionShadowReader,
    DecisionOpinionShadowWriter,
)
from ditto_agent.storage.sqlite.decision_outcome_feedback_store import (
    DecisionOutcomeFeedbackShadowReader,
    DecisionOutcomeFeedbackShadowWriter,
)
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
    DecisionOpinionWriteError,
)
from ditto_application.queries.decision_opinion import (
    DecisionOpinionReaderPort,
    DecisionOpinionStoredView,
)


class _DecisionOpinionWriterAdapter:
    """Translate physical failures into the application shadow refusal contract."""

    def __init__(self, writer: DecisionOpinionShadowWriter) -> None:
        self._writer = writer

    def append_opinion(self, record: DecisionOpinionRecord) -> bool:
        try:
            return self._writer.append_opinion(record)
        except AgentPersistenceError as exc:
            raise DecisionOpinionWriteError(
                "DecisionOpinion shadow persistence is unavailable"
            ) from exc


class _DecisionOpinionReaderAdapter:
    """Translate physical failures into the application query boundary."""

    def __init__(self, reader: DecisionOpinionShadowReader) -> None:
        self._reader = reader

    def get_latest_by_v3_artifact_id(
        self, v3_artifact_id: str
    ) -> DecisionOpinionStoredView | None:
        try:
            return cast(
                "DecisionOpinionStoredView | None",
                self._reader.get_latest_by_v3_artifact_id(v3_artifact_id),
            )
        except AgentPersistenceError as exc:
            raise AppQueryError(
                "DecisionOpinion shadow query is unavailable",
                details={"code": "DECISION_OPINION_STORE_UNAVAILABLE"},
            ) from exc


@dataclass(frozen=True, slots=True)
class DecisionOpinionShadowStoreBundle:
    """Nominal shadow database plus its narrow reader and writer adapters."""

    database: DecisionOpinionShadowDatabase
    reader: DecisionOpinionShadowReader
    query_reader: DecisionOpinionReaderPort
    writer: _DecisionOpinionWriterAdapter
    feedback_reader: DecisionOutcomeFeedbackShadowReader
    feedback_writer: DecisionOutcomeFeedbackShadowWriter

    def close(self) -> None:
        """Permanently close this explicit shadow-only lifecycle."""
        self.database.close_all()


def build_decision_opinion_shadow_store(
    data_root: Path,
) -> DecisionOpinionShadowStoreBundle:
    """Build an explicitly requested store without touching core databases."""
    database = DecisionOpinionShadowDatabase(data_root)
    database.initialize()
    reader = DecisionOpinionShadowReader(database)
    return DecisionOpinionShadowStoreBundle(
        database=database,
        reader=reader,
        query_reader=_DecisionOpinionReaderAdapter(reader),
        writer=_DecisionOpinionWriterAdapter(DecisionOpinionShadowWriter(database)),
        feedback_reader=DecisionOutcomeFeedbackShadowReader(database),
        feedback_writer=DecisionOutcomeFeedbackShadowWriter(database),
    )


__all__ = [
    "DecisionOpinionShadowStoreBundle",
    "build_decision_opinion_shadow_store",
]
