"""Authenticated SQLite v1 schema for the isolated DecisionOpinion store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib.resources import files

from ditto_agent.storage.sqlite.errors import AgentSchemaError

APPLICATION_ID = 1_146_373_976
USER_VERSION = 2
DDL_SHA256 = "2a978e04405d0418d50e3cc88b301c1c3329281af282521b538ccfed22e6b33d"
SCHEMA_FINGERPRINT = "8a018fb51b4fa5ec2ff0412e34b0dc2e53092f2317f58e928acee76227d20f1a"
SCHEMA_ROW_COUNT = 13

_DDL_SHA256_BY_VERSION = {
    1: "e5d393b3e9329cd9c991449dc7cad705ee03289308213026978872ea7b0feb64",
    2: DDL_SHA256,
}
_SCHEMA_BY_VERSION = {
    1: (
        6,
        "cbe03af9d41a50577b203f7da79e4a4f4391096d8f7b015ea97a561b0ffe8603",
    ),
    2: (SCHEMA_ROW_COUNT, SCHEMA_FINGERPRINT),
}

_MARKER_COUNT = 2
_APPLICATION_MARKER = f"PRAGMA application_id = {APPLICATION_ID};"


def _schema_error(
    message: str, reason_code: str, **details: object
) -> AgentSchemaError:
    return AgentSchemaError(message, reason_code=reason_code, details=details)


def load_schema_sql(*, version: int = USER_VERSION) -> str:
    """Read and authenticate one approved shadow schema artifact."""
    expected_hash = _DDL_SHA256_BY_VERSION.get(version)
    if expected_hash is None:
        raise _schema_error(
            "DecisionOpinion schema version is not approved",
            "decision_opinion_schema_version_unknown",
            version=version,
        )
    payload = (
        files(__package__)
        .joinpath(f"decision_opinion_schema_v{version}.sql")
        .read_bytes()
    )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_hash:
        raise _schema_error(
            "DecisionOpinion schema checksum is not approved",
            "decision_opinion_schema_resource_hash_mismatch",
            expected_hash=expected_hash,
            actual_hash=digest,
            version=version,
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


def schema_body_statements(sql: str, *, version: int = USER_VERSION) -> tuple[str, ...]:
    """Return DDL after proving application/version markers are last."""
    if version not in _DDL_SHA256_BY_VERSION:
        raise _schema_error(
            "DecisionOpinion schema version is not approved",
            "decision_opinion_schema_version_unknown",
            version=version,
        )
    statements = iter_schema_statements(sql)
    version_marker = f"PRAGMA user_version = {version};"
    if (
        len(statements) < _MARKER_COUNT
        or not statements[-2].endswith(_APPLICATION_MARKER)
        or statements[-1] != version_marker
    ):
        raise _schema_error(
            "DecisionOpinion schema markers are absent or not last",
            "decision_opinion_schema_marker_order_invalid",
        )
    return statements[:-2]


def expected_schema(version: int) -> tuple[int, str]:
    """Return the authenticated catalog size/fingerprint for one version."""
    expected = _SCHEMA_BY_VERSION.get(version)
    if expected is None:
        raise _schema_error(
            "DecisionOpinion schema version is not approved",
            "decision_opinion_schema_version_unknown",
            version=version,
        )
    return expected


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
    "expected_schema",
    "load_schema_sql",
    "schema_body_statements",
    "schema_fingerprint",
    "schema_rows",
]
