"""Canonical schema evidence for the strategy-governance SQLite slice."""

from __future__ import annotations

import hashlib
import json
import sqlite3

APPLICATION_ID = 0
USER_VERSION = 0
SCHEMA_FINGERPRINT = "31fae35fab8c77daa028b31e5e2c3c8d9d706f0fff11d50eb7860e04da529b90"
REQUIRED_TABLES = (
    "strategy_activation_event",
    "strategy_active_pointer",
    "strategy_decision_event",
    "strategy_version",
    "strategy_version_state",
)
SCHEMA_ROW_COUNT = len(REQUIRED_TABLES)


def schema_rows(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Return the governance-owned schema rows in stable fingerprint order."""
    return tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE tbl_name IN (?, ?, ?, ?, ?)
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """,
            REQUIRED_TABLES,
        )
    )


def schema_fingerprint(rows: tuple[tuple[object, ...], ...]) -> str:
    """Hash canonical governance schema rows using compact JSON."""
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()
