"""Approved Research Schema v2 resources and deterministic inspection helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from importlib.resources import files

from ditto_analysis.errors import ExperimentSchemaError

APPLICATION_ID = 1_146_376_755
V1_USER_VERSION = 1
USER_VERSION = 2
V1_DDL_SHA256 = "697d10854fb12e324ddcff349bad55b9b442425b244cb5f1852d7192cfb7a8fd"
DDL_SHA256 = V1_DDL_SHA256
MIGRATION_DDL_SHA256 = (
    "34916eab0f426dc6a2c0401a76f8abc2b610e0e4c8a2c5fffb81919b7c7f0b78"
)
V1_SCHEMA_FINGERPRINT = (
    "b4e0c52b7ef2f844987ecd65cc96ece5c5f75a3d19dc15e380c4ffdf10adc39a"
)
V1_SCHEMA_ROW_COUNT = 50
SCHEMA_FINGERPRINT = "7b4a6d03f4ba879ca54fd47220b7d28728bcb58c87cdca3cdfe27a5466cd51e0"
SCHEMA_ROW_COUNT = 95
V2_TABLE_NAMES = frozenset(
    {
        "research_campaign",
        "research_campaign_event",
        "research_candidate_lineage",
        "research_code_artifact",
        "research_feedback",
        "research_knowledge",
        "research_knowledge_status_event",
        "research_operational_attempt",
        "research_statistical_trial",
        "sandbox_execution_manifest",
    }
)
_MARKER_COUNT = 2

_APPLICATION_MARKER = f"PRAGMA application_id = {APPLICATION_ID};"
_V1_VERSION_MARKER = f"PRAGMA user_version = {V1_USER_VERSION};"
_VERSION_MARKER = f"PRAGMA user_version = {USER_VERSION};"


def _schema_error(
    message: str, reason_code: str, **details: object
) -> ExperimentSchemaError:
    return ExperimentSchemaError(
        message,
        details={"reason_code": reason_code, **details},
    )


def load_v1_schema_sql() -> str:
    """Read and checksum the immutable R3 schema used as the migration base."""
    payload = files(__package__).joinpath("schema_v1.sql").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != V1_DDL_SHA256:
        raise _schema_error(
            "packaged research v1 schema checksum does not match the approved artifact",
            "research_schema_resource_hash_mismatch",
            expected_hash=V1_DDL_SHA256,
            actual_hash=digest,
        )
    return payload.decode("utf-8")


def load_schema_sql() -> str:
    """Return the v1 base resource retained for compatibility and fresh setup."""
    return load_v1_schema_sql()


def load_migration_sql() -> str:
    """Read and checksum the sole approved forward migration resource."""
    payload = files(__package__).joinpath("migration_v1_to_v2.sql").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != MIGRATION_DDL_SHA256:
        raise _schema_error(
            "packaged research migration checksum does not match the approved artifact",
            "research_schema_resource_hash_mismatch",
            expected_hash=MIGRATION_DDL_SHA256,
            actual_hash=digest,
        )
    return payload.decode("utf-8")


def iter_schema_statements(sql: str) -> tuple[str, ...]:
    """Split SQL only at boundaries accepted by ``sqlite3.complete_statement``."""
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
            "approved research schema ends with an incomplete SQL statement",
            "research_schema_incomplete_statement",
        )
    return tuple(statements)


def schema_body_statements(sql: str) -> tuple[str, ...]:
    """Return DDL statements while proving the two markers are last."""
    statements = iter_schema_statements(sql)
    if (
        len(statements) < _MARKER_COUNT
        or not statements[-2].endswith(_APPLICATION_MARKER)
        or statements[-1] != _V1_VERSION_MARKER
    ):
        raise _schema_error(
            "approved schema markers are absent or not last",
            "research_schema_marker_order_invalid",
        )
    return statements[:-2]


def migration_body_statements(sql: str) -> tuple[str, ...]:
    """Return migration DDL while proving the v2 version marker is last."""
    statements = iter_schema_statements(sql)
    if not statements or statements[-1] != _VERSION_MARKER:
        raise _schema_error(
            "approved research migration version marker is absent or not last",
            "research_schema_marker_order_invalid",
        )
    return statements[:-1]


def schema_rows(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Return the approved fingerprint input in its exact stable order."""
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
    """Compute the approved schema fingerprint over JSON-encoded rows."""
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
