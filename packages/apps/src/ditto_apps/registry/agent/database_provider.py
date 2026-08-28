"""Apps-owned lifecycle composition for the dedicated Agent database."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.episode_store import (
    AgentEpisodeReader,
    AgentEpisodeWriter,
)
from ditto_agent.storage.sqlite.presentation_store import (
    AgentPresentationDatabase,
    AgentPresentationProjector,
    AgentPresentationReader,
    AgentPresentationWriter,
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
    presentation_database: AgentPresentationDatabase
    presentation_reader: AgentPresentationReader
    presentation_writer: AgentPresentationWriter
    presentation_projector: AgentPresentationProjector

    def close(self) -> None:
        """Permanently close the bundle's owned database connections."""
        self.database.close_all()
        self.presentation_database.close_all()

    def backup_to(self, destination_root: Path) -> tuple[Path, Path]:
        """Back up authoritative and readable Agent stores as one recovery unit."""
        if destination_root.exists():
            raise FileExistsError(destination_root)
        destination_root.mkdir(parents=True)
        primary = destination_root / "agent.sqlite"
        presentation = destination_root / "agent-presentation.sqlite3"
        try:
            self.database.backup_to(primary)
            self.presentation_database.backup_to(presentation)
        except BaseException:
            shutil.rmtree(destination_root)
            raise
        return primary, presentation


def build_agent_database(data_root: Path) -> AgentDatabaseBundle:
    """Initialize and compose the sole Agent SQLite lifecycle boundary."""
    database = AgentDatabase(data_root)
    database.initialize()
    presentation_database = AgentPresentationDatabase(data_root)
    try:
        presentation_database.initialize()
    except BaseException:
        database.close_all()
        presentation_database.close_all()
        raise
    presentation_reader = AgentPresentationReader(presentation_database)
    presentation_writer = AgentPresentationWriter(presentation_database)
    return AgentDatabaseBundle(
        database=database,
        reader=AgentStoreReader(database),
        writer=AgentStoreWriter(database),
        episode_reader=AgentEpisodeReader(database),
        episode_writer=AgentEpisodeWriter(database),
        presentation_database=presentation_database,
        presentation_reader=presentation_reader,
        presentation_writer=presentation_writer,
        presentation_projector=AgentPresentationProjector(
            reader=presentation_reader,
            writer=presentation_writer,
        ),
    )


def restore_agent_database(
    backup_root: Path,
    destination_root: Path,
) -> AgentDatabaseBundle:
    """Restore and authenticate both Agent stores into one new data root."""
    if destination_root.exists():
        raise FileExistsError(destination_root)
    primary = backup_root / "agent.sqlite"
    presentation = backup_root / "agent-presentation.sqlite3"
    if not primary.is_file() or not presentation.is_file():
        raise FileNotFoundError("Agent backup unit is incomplete")
    destination_agent = destination_root / "agent"
    destination_agent.mkdir(parents=True)
    try:
        shutil.copy2(primary, destination_agent / "agent.sqlite")
        shutil.copy2(
            presentation,
            destination_agent / "agent-presentation.sqlite3",
        )
        return build_agent_database(destination_root)
    except BaseException:
        shutil.rmtree(destination_root)
        raise


__all__ = [
    "AgentDatabaseBundle",
    "build_agent_database",
    "restore_agent_database",
]
