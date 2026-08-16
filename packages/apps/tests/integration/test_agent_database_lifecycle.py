from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_agent.contracts.runtime import AgentSession, RetentionClass
from ditto_agent.storage.sqlite.errors import AgentDatabaseClosedError
from ditto_apps.registry.agent.database_provider import build_agent_database


def test_apps_owns_agent_database_lifecycle_without_exposing_pool(
    tmp_path: Path,
) -> None:
    bundle = build_agent_database(tmp_path)
    session = AgentSession(
        session_id="session-001",
        created_at=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
        retention_class=RetentionClass.STANDARD,
    )

    bundle.writer.create_session(session)

    assert bundle.reader.get_session(session.session_id) == session
    assert bundle.database.path == tmp_path / "agent" / "agent.sqlite"
    assert not hasattr(bundle, "pool")

    bundle.close()
    with pytest.raises(AgentDatabaseClosedError):
        bundle.reader.get_session(session.session_id)
