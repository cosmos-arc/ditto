"""Authenticated schema resource for the independent presentation database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib.resources import files

from ditto_agent.presentation import AgentPresentationError

APPLICATION_ID = 1_146_376_274
USER_VERSION = 1
DDL_SHA256 = "ff10c96daa28dc505ea443d7c92e207324e1bf01b52bb32bf38e9b3cf2a2818f"
SCHEMA_FINGERPRINT = "4878dc730226f6f2783154d75a2ded72cd6e1241a722b323403d31761d7e4d7f"
SCHEMA_ROW_COUNT = 2
_MARKER_COUNT = 2


def _error(message: str, reason_code: str) -> AgentPresentationError:
    return AgentPresentationError(message, reason_code=reason_code)


def load_schema_sql() -> str:
    """Read the package-local schema only when its digest is approved."""
    payload = files(__package__).joinpath("presentation_schema_v1.sql").read_bytes()
    if hashlib.sha256(payload).hexdigest() != DDL_SHA256:
        raise _error(
            "Agent presentation schema resource is not authenticated",
            "agent_presentation_schema_resource_invalid",
        )
    return payload.decode("utf-8")


def iter_schema_statements(sql: str) -> tuple[str, ...]:
    """Split the fixed schema at SQLite-recognized statement boundaries."""
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
        raise _error(
            "Agent presentation schema is incomplete",
            "agent_presentation_schema_incomplete",
        )
    return tuple(statements)


def schema_body_statements(sql: str) -> tuple[str, ...]:
    """Return DDL after proving the two markers are last."""
    statements = iter_schema_statements(sql)
    if (
        len(statements) < _MARKER_COUNT
        or statements[-2] != f"PRAGMA application_id = {APPLICATION_ID};"
        or statements[-1] != f"PRAGMA user_version = {USER_VERSION};"
    ):
        raise _error(
            "Agent presentation schema markers are invalid",
            "agent_presentation_schema_markers_invalid",
        )
    return statements[:-2]


def schema_rows(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Return stable application-owned catalog rows."""
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
    """Authenticate the deterministic SQLite catalog representation."""
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
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
