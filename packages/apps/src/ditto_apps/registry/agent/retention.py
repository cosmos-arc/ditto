"""Apps composition boundary for the Agent retention service lifecycle."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from ditto_agent.retention import AgentRetentionService
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_agent.storage.sqlite.retention import SQLiteRawContentRetentionStore

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.infra.config import load_data_store_settings


class AgentRetentionUnavailable(RuntimeError):
    """The optional retention persistence boundary could not be opened or used."""


@contextmanager
def open_agent_retention_service(
    data_root: Path | None,
) -> Generator[AgentRetentionService]:
    """Own physical adapters and expose only the public retention service."""
    root = load_data_store_settings().data_root if data_root is None else data_root
    try:
        bundle = build_agent_database(root)
    except AgentPersistenceError as exc:
        raise AgentRetentionUnavailable from exc
    try:
        yield AgentRetentionService(
            store=SQLiteRawContentRetentionStore(bundle.database)
        )
    except AgentPersistenceError as exc:
        raise AgentRetentionUnavailable from exc
    finally:
        bundle.close()


__all__ = ["AgentRetentionUnavailable", "open_agent_retention_service"]
