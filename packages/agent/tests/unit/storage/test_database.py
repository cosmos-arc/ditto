from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from ditto_agent.storage.sqlite import schema
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentDatabaseClosedError,
    AgentPersistenceError,
    AgentSchemaError,
)


def _insert_session_then_fail(database: AgentDatabase) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO agent_sessions (
                session_id, created_at_us, retention_class
            ) VALUES (?, ?, ?)
            """,
            ("session-rollback", 1, "standard"),
        )
        raise RuntimeError("force rollback")


def test_agent_database_initializes_reopens_and_restores_exact_schema(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "primary"
    database = AgentDatabase(data_root)

    database.initialize()

    assert database.path == data_root / "agent" / "agent.sqlite"
    with database.connection() as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == (
            schema.APPLICATION_ID
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            schema.USER_VERSION
        )
        rows = schema.schema_rows(connection)
        assert len(rows) == schema.SCHEMA_ROW_COUNT
        assert schema.schema_fingerprint(rows) == schema.SCHEMA_FINGERPRINT

    database.close_all()
    reopened = AgentDatabase(data_root)
    reopened.initialize()

    backup_path = tmp_path / "backups" / "agent.sqlite"
    assert reopened.backup_to(backup_path) == backup_path
    restore_root = tmp_path / "restored"
    restored_path = restore_root / "agent" / "agent.sqlite"
    restored_path.parent.mkdir(parents=True)
    shutil.copy2(backup_path, restored_path)
    restored = AgentDatabase(restore_root)
    restored.initialize()


@pytest.mark.parametrize(
    ("setup", "reason_code"),
    [
        ("unmarked", "agent_schema_unmarked_nonempty"),
        ("future", "agent_schema_future_version"),
        ("drift", "agent_schema_drift"),
    ],
)
def test_agent_database_fails_closed_on_unapproved_schema_states(
    tmp_path: Path,
    setup: str,
    reason_code: str,
) -> None:
    database = AgentDatabase(tmp_path)
    database.path.parent.mkdir(parents=True)
    if setup == "unmarked":
        with sqlite3.connect(database.path) as connection:
            connection.execute("CREATE TABLE foreign_table (id INTEGER PRIMARY KEY)")
    else:
        database.initialize()
        with database.connection() as connection:
            if setup == "future":
                connection.execute(f"PRAGMA user_version={schema.USER_VERSION + 1}")
            else:
                connection.execute("DROP TABLE agent_retention")
            connection.commit()

    with pytest.raises(AgentSchemaError) as exc_info:
        database.initialize()

    assert exc_info.value.reason_code == reason_code


def test_agent_database_transaction_rolls_back_and_close_is_permanent(
    tmp_path: Path,
) -> None:
    database = AgentDatabase(tmp_path)
    database.initialize()

    with pytest.raises(RuntimeError, match="force rollback"):
        _insert_session_then_fail(database)

    with database.connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM agent_sessions").fetchone()[0]
    assert count == 0

    database.close_all()
    database.close_all()
    with pytest.raises(AgentDatabaseClosedError):
        database.get_connection()


def test_agent_database_backup_rejects_foreign_key_orphans_and_cleans_target(
    tmp_path: Path,
) -> None:
    database = AgentDatabase(tmp_path / "source")
    database.initialize()
    connection = database.get_connection()
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        "INSERT INTO agent_runs(run_id, session_id, status, objective_hash, "
        "authority_hash, max_model_tokens, max_model_spend_usd, model_profile, "
        "manifest_hash, created_at_us, revision) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run-orphan",
            "session-missing",
            "queued",
            "a" * 64,
            "b" * 64,
            1,
            "0",
            "balanced",
            "c" * 64,
            1,
            0,
        ),
    )
    connection.commit()
    connection.execute("PRAGMA foreign_keys=ON")
    destination = tmp_path / "backup" / "agent.sqlite"

    with pytest.raises(AgentPersistenceError) as exc_info:
        database.backup_to(destination)

    assert exc_info.value.reason_code == "agent_database_integrity_failed"
    assert not destination.exists()
