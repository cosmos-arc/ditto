from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ditto_agent.contracts.runtime import AgentSession, RetentionClass
from ditto_agent.storage.sqlite.audit import verify_audit_chain
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import AuditChainError, LeaseLostError
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

NOW = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _writer(tmp_path: Path) -> tuple[AgentDatabase, AgentStoreWriter]:
    database = AgentDatabase(tmp_path)
    database.initialize()
    return database, AgentStoreWriter(database)


def test_lease_takeover_uses_monotonic_fence_and_rejects_lost_owner(
    tmp_path: Path,
) -> None:
    _database, writer = _writer(tmp_path)
    first = writer.try_acquire_lease(
        resource_kind="run",
        resource_id="run-001",
        owner_token="worker-a",
        now=NOW,
        lease_until=NOW + timedelta(seconds=10),
    )
    assert first is not None
    assert first.fence == 1

    blocked = writer.try_acquire_lease(
        resource_kind="run",
        resource_id="run-001",
        owner_token="worker-b",
        now=NOW + timedelta(seconds=5),
        lease_until=NOW + timedelta(seconds=20),
    )
    assert blocked is None

    takeover = writer.try_acquire_lease(
        resource_kind="run",
        resource_id="run-001",
        owner_token="worker-b",
        now=NOW + timedelta(seconds=11),
        lease_until=NOW + timedelta(seconds=30),
    )
    assert takeover is not None
    assert takeover.fence == 2

    with pytest.raises(LeaseLostError):
        writer.renew_lease(
            first,
            now=NOW + timedelta(seconds=12),
            lease_until=NOW + timedelta(seconds=40),
        )
    renewed = writer.renew_lease(
        takeover,
        now=NOW + timedelta(seconds=12),
        lease_until=NOW + timedelta(seconds=40),
    )
    assert renewed.fence == takeover.fence
    assert renewed.revision == takeover.revision + 1


def test_lease_release_expires_owner_and_preserves_monotonic_fence(
    tmp_path: Path,
) -> None:
    _database, writer = _writer(tmp_path)
    acquired = writer.try_acquire_lease(
        resource_kind="campaign",
        resource_id="campaign-001",
        owner_token="worker-a",
        now=NOW,
        lease_until=NOW + timedelta(seconds=30),
    )
    assert acquired is not None

    released = writer.release_lease(acquired, released_at=NOW + timedelta(seconds=1))
    assert released.fence == acquired.fence
    assert released.revision == acquired.revision + 1
    assert released.lease_until == NOW + timedelta(seconds=1)

    reacquired = writer.try_acquire_lease(
        resource_kind="campaign",
        resource_id="campaign-001",
        owner_token="worker-b",
        now=NOW + timedelta(seconds=2),
        lease_until=NOW + timedelta(seconds=30),
    )
    assert reacquired is not None
    assert reacquired.fence == acquired.fence + 1

    with pytest.raises(LeaseLostError):
        writer.release_lease(acquired, released_at=NOW + timedelta(seconds=3))


def test_audit_chain_detects_durable_tampering(tmp_path: Path) -> None:
    database, writer = _writer(tmp_path)
    writer.create_session(
        AgentSession(
            session_id="session-001",
            created_at=NOW,
            retention_class=RetentionClass.AUDIT,
        )
    )
    writer.reserve_idempotency(
        scope="audit-probe",
        idempotency_key="idem-001",
        request_hash=_hash("request"),
        occurred_at=NOW + timedelta(seconds=1),
    )
    with database.connection() as connection:
        verified = verify_audit_chain(connection)
        assert verified.event_count == 2
        assert verified.head_hash is not None

        connection.execute("DROP TRIGGER agent_audit_no_update")
        connection.execute(
            "UPDATE agent_audit_events SET payload_hash = ? WHERE audit_id = 1",
            (_hash("tampered"),),
        )
        connection.commit()

        with pytest.raises(AuditChainError):
            verify_audit_chain(connection)
