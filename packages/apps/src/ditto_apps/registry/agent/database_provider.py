"""Apps-owned lifecycle composition for the dedicated Agent database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.episode_store import (
    AgentEpisodeReader,
    AgentEpisodeWriter,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.writer import AgentStoreWriter


@dataclass(frozen=True, slots=True)
class AgentDatabaseBundle:
    """Nominal database and its typed adapters; the pool remains private."""

    database: AgentDatabase
    reader: AgentStoreReader
    writer: AgentStoreWriter
    episode_reader: AgentEpisodeReader
    episode_writer: AgentEpisodeWriter

    def close(self) -> None:
        """Permanently close the bundle's owned database connections."""
        self.database.close_all()


def build_agent_database(data_root: Path) -> AgentDatabaseBundle:
    """Initialize and compose the sole Agent SQLite lifecycle boundary."""
    database = AgentDatabase(data_root)
    database.initialize()
    return AgentDatabaseBundle(
        database=database,
        reader=AgentStoreReader(database),
        writer=AgentStoreWriter(database),
        episode_reader=AgentEpisodeReader(database),
        episode_writer=AgentEpisodeWriter(database),
    )


__all__ = ["AgentDatabaseBundle", "build_agent_database"]
