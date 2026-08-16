"""Approved Agent SQLite v1 resource and deterministic schema identity."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib.resources import files

from ditto_agent.storage.sqlite.errors import AgentSchemaError

APPLICATION_ID = 1_146_372_423
USER_VERSION = 1
DDL_SHA256 = "b929ba78672f7c3eab83f502fdfad9e522d367b46021d7163aa3227078a5dc99"
SCHEMA_FINGERPRINT = "c88a91fe672be70ab679435da07ae989d07160d3a5ffce3186c9fcd51e495bdb"
SCHEMA_ROW_COUNT = 17

_MARKER_COUNT = 2
_APPLICATION_MARKER = f"PRAGMA application_id = {APPLICATION_ID};"
_VERSION_MARKER = f"PRAGMA user_version = {USER_VERSION};"


def _schema_error(
    message: str, reason_code: str, **details: object
) -> AgentSchemaError:
    return AgentSchemaError(message, reason_code=reason_code, details=details)


def load_schema_sql() -> str:
    """Read and authenticate the package-local immutable SQL artifact."""
    payload = files(__package__).joinpath("schema_v1.sql").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != DDL_SHA256:
        raise _schema_error(
            "Agent schema resource checksum does not match its approved artifact",
            "agent_schema_resource_hash_mismatch",
            expected_hash=DDL_SHA256,
            actual_hash=digest,
        )
    return payload.decode("utf-8")


def iter_schema_statements(sql: str) -> tuple[str, ...]:
    """Split SQL only at boundaries accepted by SQLite itself."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise _schema_error(
            "Agent schema ends with an incomplete SQL statement",
            "agent_schema_incomplete_statement",
        )
    return tuple(statements)


def schema_body_statements(sql: str) -> tuple[str, ...]:
    """Return DDL while proving application/version markers are last."""
    statements = iter_schema_statements(sql)
    if (
        len(statements) < _MARKER_COUNT
        or not statements[-2].endswith(_APPLICATION_MARKER)
        or statements[-1] != _VERSION_MARKER
    ):
        raise _schema_error(
            "Approved Agent schema markers are absent or not last",
            "agent_schema_marker_order_invalid",
        )
    return statements[:-2]


def schema_rows(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Return stable SQLite catalog rows authenticated by the fingerprint."""
    return tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
    )


def schema_fingerprint(rows: tuple[tuple[object, ...], ...]) -> str:
    """Hash deterministic JSON catalog rows without platform-specific spacing."""
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "APPLICATION_ID",
    "DDL_SHA256",
    "SCHEMA_FINGERPRINT",
    "SCHEMA_ROW_COUNT",
    "USER_VERSION",
    "iter_schema_statements",
    "load_schema_sql",
    "schema_body_statements",
    "schema_fingerprint",
    "schema_rows",
]
