"""Append-only tamper-evident audit chain for Agent persistence actions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import sha256_hex
from ditto_agent.storage.sqlite._codec import datetime_from_epoch_us, epoch_us, text
from ditto_agent.storage.sqlite.errors import AuditChainError


@dataclass(frozen=True, slots=True)
class AuditVerification:
    """Verified chain length and current immutable head hash."""

    event_count: int
    head_hash: str | None


def _event_hash(
    *,
    audit_id: int,
    category: str,
    subject_id: str,
    action: str,
    payload_hash: str,
    occurred_at: datetime,
    prev_hash: str | None,
) -> str:
    return canonical_sha256(
        {
            "audit_id": audit_id,
            "category": category,
            "subject_id": subject_id,
            "action": action,
            "payload_hash": payload_hash,
            "occurred_at": occurred_at,
            "prev_hash": prev_hash,
        }
    )


def append_audit_event(
    connection: sqlite3.Connection,
    *,
    category: str,
    subject_id: str,
    action: str,
    payload_hash: str,
    occurred_at: datetime,
) -> str:
    """Append one event inside the caller's immediate transaction."""
    category = text(category, field="audit category")
    subject_id = text(subject_id, field="audit subject_id")
    action = text(action, field="audit action")
    payload_hash = sha256_hex(payload_hash, field="audit payload_hash")
    occurred_at_us = epoch_us(occurred_at, field="audit occurred_at")
    row = connection.execute(
        """
        SELECT audit_id, event_hash
        FROM agent_audit_events
        ORDER BY audit_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        audit_id = 1
        prev_hash = None
    else:
        audit_id = int(row["audit_id"]) + 1
        prev_hash = str(row["event_hash"])
    event_hash = _event_hash(
        audit_id=audit_id,
        category=category,
        subject_id=subject_id,
        action=action,
        payload_hash=payload_hash,
        occurred_at=occurred_at,
        prev_hash=prev_hash,
    )
    connection.execute(
        """
        INSERT INTO agent_audit_events (
            audit_id, category, subject_id, action, payload_hash,
            occurred_at_us, prev_hash, event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            category,
            subject_id,
            action,
            payload_hash,
            occurred_at_us,
            prev_hash,
            event_hash,
        ),
    )
    return event_hash


def verify_audit_chain(connection: sqlite3.Connection) -> AuditVerification:
    """Verify every link and fail closed at the first durable mismatch."""
    rows = connection.execute(
        """
        SELECT audit_id, category, subject_id, action, payload_hash,
               occurred_at_us, prev_hash, event_hash
        FROM agent_audit_events
        ORDER BY audit_id
        """
    ).fetchall()
    previous: str | None = None
    expected_id = 1
    for row in rows:
        audit_id = int(row["audit_id"])
        occurred_at = datetime_from_epoch_us(
            int(row["occurred_at_us"]), field="audit occurred_at"
        )
        actual_prev = None if row["prev_hash"] is None else str(row["prev_hash"])
        actual_hash = str(row["event_hash"])
        expected_hash = _event_hash(
            audit_id=audit_id,
            category=str(row["category"]),
            subject_id=str(row["subject_id"]),
            action=str(row["action"]),
            payload_hash=str(row["payload_hash"]),
            occurred_at=occurred_at,
            prev_hash=actual_prev,
        )
        if (
            audit_id != expected_id
            or actual_prev != previous
            or actual_hash != expected_hash
        ):
            raise AuditChainError(
                "Agent audit hash chain verification failed",
                reason_code="agent_audit_chain_invalid",
                details={"audit_id": audit_id},
            )
        previous = actual_hash
        expected_id += 1
    return AuditVerification(event_count=len(rows), head_hash=previous)


__all__ = ["AuditVerification", "append_audit_event", "verify_audit_chain"]
