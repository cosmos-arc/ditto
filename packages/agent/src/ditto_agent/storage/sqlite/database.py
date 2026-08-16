"""Nominal wrapper for the dedicated Agent runtime database."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import cast

from ditto_platform.foundation.db.sqlite_pool import SQLitePool

from ditto_agent.storage.sqlite import schema
from ditto_agent.storage.sqlite.errors import (
    AgentDatabaseClosedError,
    AgentPersistenceError,
    AgentSchemaError,
)

_INITIALIZE_LOCK = Lock()


def _schema_error(
    message: str, reason_code: str, **details: object
) -> AgentSchemaError:
    return AgentSchemaError(message, reason_code=reason_code, details=details)


class AgentDatabase:
    """Own the sole ``data_root/agent/agent.sqlite`` connection pool."""

    def __init__(self, data_root: Path) -> None:
        if not isinstance(cast(object, data_root), Path):
            raise TypeError("data_root must be pathlib.Path")
        self._path = data_root / "agent" / "agent.sqlite"
        self._pool = SQLitePool(str(self._path))
        self._state_lock = Lock()
        self._closed = False

    @property
    def path(self) -> Path:
        """Return the only database path the wrapper may open."""
        return self._path

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise AgentDatabaseClosedError(
                "Agent database has been permanently closed",
                reason_code="agent_database_closed",
            )

    def get_connection(self) -> sqlite3.Connection:
        """Return a thread-local connection with integrity pragmas proven on."""
        with self._state_lock:
            self._raise_if_closed()
            connection = self._pool.get_connection()
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA recursive_triggers=ON")
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        recursive_triggers = connection.execute("PRAGMA recursive_triggers").fetchone()[
            0
        ]
        if foreign_keys != 1 or recursive_triggers != 1:
            raise _schema_error(
                "Required SQLite integrity pragmas could not be enabled",
                "agent_database_pragma_disabled",
                foreign_keys=foreign_keys,
                recursive_triggers=recursive_triggers,
            )
        return connection

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """Yield the current thread's proven Agent-only connection."""
        yield self.get_connection()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run one immediate transaction and roll back every exception."""
        connection = self.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def initialize(self) -> None:
        """Create or verify exactly the approved v1 schema."""
        with _INITIALIZE_LOCK:
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            rows = schema.schema_rows(connection)
            if application_id == 0 and user_version == 0 and not rows:
                for statement in schema.schema_body_statements(
                    schema.load_schema_sql()
                ):
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={schema.USER_VERSION}")
                self._verify_current_schema(connection)
                connection.commit()
                return
            if (
                application_id == schema.APPLICATION_ID
                and user_version == schema.USER_VERSION
            ):
                self._verify_current_schema(connection)
                connection.commit()
                return
            raise self._marker_error(application_id, user_version, bool(rows))
        except AgentSchemaError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _schema_error(
                "Agent schema initialization failed and was rolled back",
                "agent_schema_initialization_failed",
                sqlite_error=type(exc).__name__,
            ) from exc
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _marker_error(
        application_id: int,
        user_version: int,
        has_objects: bool,
    ) -> AgentSchemaError:
        if application_id == 0 and user_version == 0 and has_objects:
            reason = "agent_schema_unmarked_nonempty"
        elif application_id not in (0, schema.APPLICATION_ID):
            reason = "agent_schema_unknown_application"
        elif (
            application_id == schema.APPLICATION_ID
            and user_version > schema.USER_VERSION
        ):
            reason = "agent_schema_future_version"
        else:
            reason = "agent_schema_invalid_marker_combination"
        return _schema_error(
            "Agent database markers are not an approved schema state",
            reason,
            application_id=application_id,
            user_version=user_version,
        )

    @staticmethod
    def _verify_current_schema(connection: sqlite3.Connection) -> None:
        rows = schema.schema_rows(connection)
        fingerprint = schema.schema_fingerprint(rows)
        if (
            len(rows) != schema.SCHEMA_ROW_COUNT
            or fingerprint != schema.SCHEMA_FINGERPRINT
        ):
            raise _schema_error(
                "Agent database markers are current but schema has drifted",
                "agent_schema_drift",
                expected_fingerprint=schema.SCHEMA_FINGERPRINT,
                actual_fingerprint=fingerprint,
                expected_rows=schema.SCHEMA_ROW_COUNT,
                actual_rows=len(rows),
            )
        markers = (
            connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0],
        )
        if markers != (schema.APPLICATION_ID, schema.USER_VERSION):
            raise _schema_error(
                "Agent schema markers changed during verification",
                "agent_schema_invalid_marker_combination",
            )

    def backup_to(self, destination: Path) -> Path:
        """Create one non-overwriting SQLite backup after schema verification."""
        if not isinstance(cast(object, destination), Path):
            raise TypeError("destination must be pathlib.Path")
        if destination == self._path:
            raise ValueError("backup destination must differ from the live database")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = self.get_connection()
        self._verify_current_schema(source)
        try:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent database backup failed",
                reason_code="agent_database_backup_failed",
            ) from exc
        with sqlite3.connect(destination) as verified:
            self._verify_current_schema(verified)
        return destination

    def close_all(self) -> None:
        """Permanently close all connections and forbid resurrection."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._pool.close_all()


__all__ = ["AgentDatabase"]
