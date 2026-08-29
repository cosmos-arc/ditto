"""Lease-fenced coordination and retention writes for Agent persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.storage.sqlite._codec import epoch_us
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import AgentPersistenceError, LeaseLostError
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import LeaseFence, RetentionMetadata


class AgentCoordinationWriter:
    """Persist lease ownership and retention metadata behind exact fences."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database
        self._reader = AgentStoreReader(database)

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        try:
            with self._database.transaction() as connection:
                yield connection
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent coordination write failed",
                reason_code="agent_write_failed",
            ) from exc

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        category: str,
        subject_id: str,
        action: str,
        payload: object,
        occurred_at: datetime,
    ) -> None:
        append_audit_event(
            connection,
            category=category,
            subject_id=subject_id,
            action=action,
            payload_hash=canonical_sha256(payload),
            occurred_at=occurred_at,
        )

    def try_acquire_lease(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        owner_token: str,
        now: datetime,
        lease_until: datetime,
    ) -> LeaseFence | None:
        """Acquire an absent/expired lease and increment its durable fence."""
        resource_kind = normalized_text(resource_kind, field="resource_kind")
        resource_id = normalized_text(resource_id, field="resource_id")
        owner_token = normalized_text(owner_token, field="owner_token")
        now_us = epoch_us(now, field="lease now")
        lease_until_us = epoch_us(lease_until, field="lease_until")
        if lease_until_us <= now_us:
            raise ValueError("lease_until must be after now")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_leases
                WHERE resource_kind=? AND resource_id=?
                """,
                (resource_kind, resource_id),
            ).fetchone()
            if row is None:
                fence = 1
                revision = 0
                action = "acquired"
                connection.execute(
                    """
                    INSERT INTO agent_leases (
                        resource_kind, resource_id, owner_token, fence,
                        lease_until_us, revision
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resource_kind,
                        resource_id,
                        owner_token,
                        fence,
                        lease_until_us,
                        revision,
                    ),
                )
            elif int(row["lease_until_us"]) > now_us:
                if row["owner_token"] == owner_token:
                    return self._reader.get_lease(resource_kind, resource_id)
                return None
            else:
                fence = int(row["fence"]) + 1
                revision = int(row["revision"]) + 1
                action = "taken_over"
                connection.execute(
                    """
                    UPDATE agent_leases
                    SET owner_token=?, fence=?, lease_until_us=?, revision=?
                    WHERE resource_kind=? AND resource_id=?
                    """,
                    (
                        owner_token,
                        fence,
                        lease_until_us,
                        revision,
                        resource_kind,
                        resource_id,
                    ),
                )
            self._audit(
                connection,
                category="lease",
                subject_id=f"{resource_kind}:{resource_id}",
                action=action,
                payload={
                    "resource_kind": resource_kind,
                    "resource_id": resource_id,
                    "owner_hash": canonical_sha256(owner_token),
                    "fence": fence,
                    "lease_until": lease_until,
                },
                occurred_at=now,
            )
        return self._reader.get_lease(resource_kind, resource_id)

    def renew_lease(
        self,
        lease: LeaseFence,
        *,
        now: datetime,
        lease_until: datetime,
    ) -> LeaseFence:
        """Renew only the exact active owner/fence/revision tuple."""
        now_us = epoch_us(now, field="lease now")
        lease_until_us = epoch_us(lease_until, field="lease_until")
        if lease_until_us <= now_us:
            raise ValueError("lease_until must be after now")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_leases
                WHERE resource_kind=? AND resource_id=?
                """,
                (lease.resource_kind, lease.resource_id),
            ).fetchone()
            if (
                row is None
                or row["owner_token"] != lease.owner_token
                or int(row["fence"]) != lease.fence
                or int(row["revision"]) != lease.revision
                or int(row["lease_until_us"]) <= now_us
            ):
                raise LeaseLostError(
                    "Agent lease ownership has been lost",
                    reason_code="agent_lease_lost",
                )
            revision = lease.revision + 1
            cursor = connection.execute(
                """
                UPDATE agent_leases
                SET lease_until_us=?, revision=?
                WHERE resource_kind=? AND resource_id=? AND owner_token=?
                    AND fence=? AND revision=?
                """,
                (
                    lease_until_us,
                    revision,
                    lease.resource_kind,
                    lease.resource_id,
                    lease.owner_token,
                    lease.fence,
                    lease.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseLostError(
                    "Agent lease renewal lost its ownership fence",
                    reason_code="agent_lease_lost",
                )
            self._audit(
                connection,
                category="lease",
                subject_id=f"{lease.resource_kind}:{lease.resource_id}",
                action="renewed",
                payload={
                    "owner_hash": canonical_sha256(lease.owner_token),
                    "fence": lease.fence,
                    "revision": revision,
                    "lease_until": lease_until,
                },
                occurred_at=now,
            )
        renewed = self._reader.get_lease(lease.resource_kind, lease.resource_id)
        if renewed is None:
            raise LeaseLostError(
                "Renewed Agent lease is not readable",
                reason_code="agent_lease_lost",
            )
        return renewed

    def release_lease(
        self,
        lease: LeaseFence,
        *,
        released_at: datetime,
    ) -> LeaseFence:
        """Expire only the exact active owner/fence/revision tuple."""
        released_at_us = epoch_us(released_at, field="lease released_at")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM agent_leases
                WHERE resource_kind=? AND resource_id=?
                """,
                (lease.resource_kind, lease.resource_id),
            ).fetchone()
            if (
                row is None
                or row["owner_token"] != lease.owner_token
                or int(row["fence"]) != lease.fence
                or int(row["revision"]) != lease.revision
                or int(row["lease_until_us"]) <= released_at_us
            ):
                raise LeaseLostError(
                    "Agent lease ownership has been lost",
                    reason_code="agent_lease_lost",
                )
            revision = lease.revision + 1
            cursor = connection.execute(
                """
                UPDATE agent_leases
                SET lease_until_us=?, revision=?
                WHERE resource_kind=? AND resource_id=? AND owner_token=?
                    AND fence=? AND revision=?
                """,
                (
                    released_at_us,
                    revision,
                    lease.resource_kind,
                    lease.resource_id,
                    lease.owner_token,
                    lease.fence,
                    lease.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseLostError(
                    "Agent lease release lost its ownership fence",
                    reason_code="agent_lease_lost",
                )
            self._audit(
                connection,
                category="lease",
                subject_id=f"{lease.resource_kind}:{lease.resource_id}",
                action="released",
                payload={
                    "owner_hash": canonical_sha256(lease.owner_token),
                    "fence": lease.fence,
                    "revision": revision,
                },
                occurred_at=released_at,
            )
        released = self._reader.get_lease(lease.resource_kind, lease.resource_id)
        if released is None:
            raise LeaseLostError(
                "Released Agent lease is not readable",
                reason_code="agent_lease_lost",
            )
        return released

    def set_retention(self, metadata: RetentionMetadata) -> RetentionMetadata:
        """Upsert typed retention metadata without deleting any target."""
        target_kind = normalized_text(metadata.target_kind, field="target_kind")
        target_id = normalized_text(metadata.target_id, field="target_id")
        retain_until_us = (
            None
            if metadata.retain_until is None
            else epoch_us(metadata.retain_until, field="retain_until")
        )
        updated_at_us = epoch_us(metadata.updated_at, field="retention updated_at")
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO agent_retention (
                    target_kind, target_id, retention_class, retain_until_us,
                    legal_hold, updated_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_kind, target_id) DO UPDATE SET
                    retention_class=excluded.retention_class,
                    retain_until_us=excluded.retain_until_us,
                    legal_hold=excluded.legal_hold,
                    updated_at_us=excluded.updated_at_us
                """,
                (
                    target_kind,
                    target_id,
                    metadata.retention_class.value,
                    retain_until_us,
                    int(metadata.legal_hold),
                    updated_at_us,
                ),
            )
            self._audit(
                connection,
                category="retention",
                subject_id=f"{target_kind}:{target_id}",
                action="metadata_set",
                payload={
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "retention_class": metadata.retention_class,
                    "retain_until": metadata.retain_until,
                    "legal_hold": metadata.legal_hold,
                },
                occurred_at=metadata.updated_at,
            )
        stored = self._reader.get_retention(target_kind, target_id)
        if stored is None:
            raise AgentPersistenceError(
                "Retention metadata is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored


__all__ = ["AgentCoordinationWriter"]
