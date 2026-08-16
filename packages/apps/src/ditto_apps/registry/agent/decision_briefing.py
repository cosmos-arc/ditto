"""Apps-owned lifecycle for the isolated DecisionOpinion shadow store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
    DecisionOpinionWriteError,
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


@dataclass(frozen=True, slots=True)
class DecisionOpinionShadowStoreBundle:
    """Nominal shadow database plus its narrow reader and writer adapters."""

    database: DecisionOpinionShadowDatabase
    reader: DecisionOpinionShadowReader
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
    return DecisionOpinionShadowStoreBundle(
        database=database,
        reader=DecisionOpinionShadowReader(database),
        writer=_DecisionOpinionWriterAdapter(DecisionOpinionShadowWriter(database)),
        feedback_reader=DecisionOutcomeFeedbackShadowReader(database),
        feedback_writer=DecisionOutcomeFeedbackShadowWriter(database),
    )


__all__ = [
    "DecisionOpinionShadowStoreBundle",
    "build_decision_opinion_shadow_store",
]
