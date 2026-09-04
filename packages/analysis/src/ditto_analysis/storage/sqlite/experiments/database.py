"""Nominal dedicated database wrapper for the R3 experiment control-plane."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import cast

from ditto_platform.foundation import SQLitePool
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    backup_database,
)

from ditto_analysis.errors import (
    ExperimentDatabaseClosedError,
    ExperimentPersistenceError,
    ExperimentSchemaError,
)
from ditto_analysis.storage.sqlite.experiments import schema

_INITIALIZE_LOCK = Lock()


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

    @property
    def artifact_root(self) -> Path:
        """Return the sole canonical filesystem root for indexed artifacts."""
        return (self._path.parent / "artifacts").resolve()

    def _ensure_open(self) -> None:
        with self._state_lock:
            self._raise_if_closed()

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise ExperimentDatabaseClosedError(
                "research experiment database has been permanently closed",
                details={"reason_code": "research_database_closed"},
            )

    def get_connection(self) -> sqlite3.Connection:
        """Get a thread-local connection with both required pragmas proven on."""
        with self._state_lock:
            self._raise_if_closed()
            connection = self._pool.get_connection()
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA recursive_triggers=ON")
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            recursive_triggers = connection.execute(
                "PRAGMA recursive_triggers"
            ).fetchone()[0]
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
        """Create, migrate, or verify the approved schema under a write lock."""
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
                for statement in schema.fresh_schema_body_statements():
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={schema.USER_VERSION}")
                self._verify_current_schema(connection)
                connection.commit()
                return

            if (
                application_id == schema.APPLICATION_ID
                and user_version == schema.V1_USER_VERSION
            ):
                self._verify_v1_schema(connection)
                self._apply_v2_migration(connection)
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
    def _apply_v2_migration(connection: sqlite3.Connection) -> None:
        try:
            statements = schema.migration_body_statements(schema.load_migration_sql())
            for statement in statements:
                connection.execute(statement)
        except ExperimentSchemaError:
            raise
        except sqlite3.Error as exc:
            raise _schema_error(
                "research schema migration failed and was rolled back",
                "research_schema_migration_failed",
                sqlite_error=type(exc).__name__,
            ) from exc

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
    def _verify_v1_schema(connection: sqlite3.Connection) -> None:
        rows = schema.schema_rows(connection)
        fingerprint = schema.schema_fingerprint(rows)
        if (
            len(rows) != schema.V1_SCHEMA_ROW_COUNT
            or fingerprint != schema.V1_SCHEMA_FINGERPRINT
        ):
            raise _schema_error(
                "research database v1 markers are valid but schema has drifted",
                "research_schema_v1_drift",
                expected_fingerprint=schema.V1_SCHEMA_FINGERPRINT,
                actual_fingerprint=fingerprint,
                expected_rows=schema.V1_SCHEMA_ROW_COUNT,
                actual_rows=len(rows),
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

    @staticmethod
    def _verify_database_integrity(connection: sqlite3.Connection) -> None:
        integrity_rows = tuple(
            str(row[0]) for row in connection.execute("PRAGMA integrity_check")
        )
        if integrity_rows != ("ok",):
            raise _schema_error(
                "research database failed SQLite integrity verification",
                "research_database_integrity_failed",
                integrity_results=integrity_rows,
            )
        foreign_key_rows = tuple(
            tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
        )
        if foreign_key_rows:
            raise _schema_error(
                "research database contains broken foreign-key references",
                "research_database_foreign_key_violation",
                violation_count=len(foreign_key_rows),
            )

    def backup_to(self, destination: Path) -> Path:
        """Create one verified, non-overwriting online backup of schema v2."""
        if not isinstance(cast("object", destination), Path):
            raise TypeError("destination must be pathlib.Path")
        if destination.resolve(strict=False) == self._path.resolve(strict=False):
            raise ValueError("backup destination must differ from the live database")
        if destination.exists():
            raise FileExistsError(destination)
        source = self.get_connection()
        self._verify_current_schema(source)
        self._verify_database_integrity(source)
        try:
            backup_database(self._path, destination)
        except SQLiteBackupError as exc:
            raise ExperimentPersistenceError(
                "research database backup failed",
                details={"reason_code": "research_database_backup_failed"},
            ) from exc
        try:
            with sqlite3.connect(destination) as verified:
                self._verify_current_schema(verified)
                self._verify_database_integrity(verified)
        except BaseException:
            for suffix in ("", "-wal", "-shm", "-journal"):
                destination.with_name(f"{destination.name}{suffix}").unlink(
                    missing_ok=True
                )
            raise
        return destination

    def close_all(self) -> None:
        """Permanently close every thread connection and forbid resurrection."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._pool.close_all()
