"""Nominal dedicated database wrapper for the R3 experiment control-plane."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import cast

from ditto_platform.foundation import SQLitePool

from ditto_analysis.errors import (
    ExperimentDatabaseClosedError,
    ExperimentSchemaError,
)
from ditto_analysis.storage.sqlite.experiments import schema

_INITIALIZE_LOCK = Lock()
_MARKER_COUNT = 2


def _schema_error(
    message: str, reason_code: str, **details: object
) -> ExperimentSchemaError:
    return ExperimentSchemaError(
        message,
        details={"reason_code": reason_code, **details},
    )


class ResearchExperimentDatabase:
    """
    Own a private SQLite pool fixed to ``data_root/research/research.sqlite``.

    The nominal wrapper is the DI boundary. Its private pool is never registered
    as a bare ``SQLitePool`` or ``SQLiteClient`` and cannot collide with metadata.
    """

    def __init__(self, data_root: Path) -> None:
        if not isinstance(cast("object", data_root), Path):
            raise TypeError("data_root must be pathlib.Path")
        self._path = data_root / "research" / "research.sqlite"
        self._pool = SQLitePool(str(self._path))
        self._state_lock = Lock()
        self._closed = False

    @property
    def path(self) -> Path:
        """Return the only database path this wrapper may open."""
        return self._path

    def _ensure_open(self) -> None:
        with self._state_lock:
            if self._closed:
                raise ExperimentDatabaseClosedError(
                    "research experiment database has been permanently closed",
                    details={"reason_code": "research_database_closed"},
                )

    def get_connection(self) -> sqlite3.Connection:
        """Get a thread-local connection with both required pragmas proven on."""
        self._ensure_open()
        connection = self._pool.get_connection()
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA recursive_triggers=ON")
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        recursive_triggers = connection.execute("PRAGMA recursive_triggers").fetchone()[
            0
        ]
        if foreign_keys != 1 or recursive_triggers != 1:
            raise _schema_error(
                "required SQLite integrity pragmas could not be enabled",
                "research_database_pragma_disabled",
                foreign_keys=foreign_keys,
                recursive_triggers=recursive_triggers,
            )
        return connection

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """Yield the current thread's proven research-only connection."""
        yield self.get_connection()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run one immediate transaction, rolling back on every exception."""
        connection = self.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def initialize(self) -> None:
        """Create or verify the exact approved schema while holding a write lock."""
        with _INITIALIZE_LOCK:
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        """Serialize first WAL connection setup, then apply the SQL lock protocol."""
        self._ensure_open()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            rows = schema.schema_rows(connection)

            if application_id == 0 and user_version == 0 and not rows:
                sql = schema.load_schema_sql()
                statements = schema.iter_schema_statements(sql)
                application_marker = f"PRAGMA application_id = {schema.APPLICATION_ID};"
                version_marker = f"PRAGMA user_version = {schema.USER_VERSION};"
                if (
                    len(statements) < _MARKER_COUNT
                    or not statements[-2].endswith(application_marker)
                    or statements[-1] != version_marker
                ):
                    raise _schema_error(
                        "approved schema markers are absent or not last",
                        "research_schema_marker_order_invalid",
                    )
                for statement in statements[:-2]:
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
        except ExperimentSchemaError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _schema_error(
                "research schema initialization failed and was rolled back",
                "research_schema_initialization_failed",
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
    ) -> ExperimentSchemaError:
        if application_id == 0 and user_version == 0 and has_objects:
            reason = "research_schema_unmarked_nonempty"
        elif application_id not in (0, schema.APPLICATION_ID):
            reason = "research_schema_unknown_application"
        elif (
            application_id == schema.APPLICATION_ID
            and user_version > schema.USER_VERSION
        ):
            reason = "research_schema_future_version"
        else:
            reason = "research_schema_invalid_marker_combination"
        return _schema_error(
            "research database markers are not an approved schema state",
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
                "research database markers are current but schema has drifted",
                "research_schema_drift",
                expected_fingerprint=schema.SCHEMA_FINGERPRINT,
                actual_fingerprint=fingerprint,
                expected_rows=schema.SCHEMA_ROW_COUNT,
                actual_rows=len(rows),
            )
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if (application_id, user_version) != (
            schema.APPLICATION_ID,
            schema.USER_VERSION,
        ):
            raise _schema_error(
                "research schema markers changed during verification",
                "research_schema_invalid_marker_combination",
            )

    def close_all(self) -> None:
        """Permanently close every thread connection and forbid resurrection."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._pool.close_all()
