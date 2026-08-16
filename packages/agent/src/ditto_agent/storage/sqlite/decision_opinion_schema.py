"""Authenticated SQLite v1 schema for the isolated DecisionOpinion store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib.resources import files

from ditto_agent.storage.sqlite.errors import AgentSchemaError

APPLICATION_ID = 1_146_373_976
USER_VERSION = 1
DDL_SHA256 = "e5d393b3e9329cd9c991449dc7cad705ee03289308213026978872ea7b0feb64"
SCHEMA_FINGERPRINT = "cbe03af9d41a50577b203f7da79e4a4f4391096d8f7b015ea97a561b0ffe8603"
SCHEMA_ROW_COUNT = 6

_MARKER_COUNT = 2
_APPLICATION_MARKER = f"PRAGMA application_id = {APPLICATION_ID};"
_VERSION_MARKER = f"PRAGMA user_version = {USER_VERSION};"


def _schema_error(
    message: str, reason_code: str, **details: object
) -> AgentSchemaError:
    return AgentSchemaError(message, reason_code=reason_code, details=details)


def load_schema_sql() -> str:
    """Read and authenticate the package-local shadow schema artifact."""
    payload = files(__package__).joinpath("decision_opinion_schema_v1.sql").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != DDL_SHA256:
        raise _schema_error(
            "DecisionOpinion schema checksum is not approved",
            "decision_opinion_schema_resource_hash_mismatch",
            expected_hash=DDL_SHA256,
            actual_hash=digest,
        )
    return payload.decode("utf-8")


def iter_schema_statements(sql: str) -> tuple[str, ...]:
    """Split SQL only at boundaries recognized by SQLite."""
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
            "DecisionOpinion schema has an incomplete statement",
            "decision_opinion_schema_incomplete_statement",
        )
    return tuple(statements)


def schema_body_statements(sql: str) -> tuple[str, ...]:
    """Return DDL after proving application/version markers are last."""
    statements = iter_schema_statements(sql)
    if (
        len(statements) < _MARKER_COUNT
        or not statements[-2].endswith(_APPLICATION_MARKER)
        or statements[-1] != _VERSION_MARKER
    ):
        raise _schema_error(
            "DecisionOpinion schema markers are absent or not last",
            "decision_opinion_schema_marker_order_invalid",
        )
    return statements[:-2]


def schema_rows(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Return deterministic catalog rows for schema authentication."""
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
    """Hash catalog rows without platform-specific JSON whitespace."""
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
    "load_schema_sql",
    "schema_body_statements",
    "schema_fingerprint",
    "schema_rows",
]
