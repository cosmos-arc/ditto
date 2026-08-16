from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ditto_agent.retention import (
    AgentRetentionService,
    RetentionPlan,
    RetentionPlanConflict,
)
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.retention import SQLiteRawContentRetentionStore

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)


def _epoch_us(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_run(
    database: AgentDatabase,
    *,
    run_id: str,
    age_days: int,
    retention_class: str = "standard",
    legal_hold_target: str | None = None,
) -> None:
    stored_at = NOW - timedelta(days=age_days)
    session_id = f"session-{run_id}"
    continuation = f'{{"provider_state":"{run_id}"}}'.encode()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO agent_manifests (
                manifest_hash, manifest_id, agent_version, prompt_version,
                prompt_hash, tool_schema_version, tool_schema_hash,
                model_profile, model_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "a" * 64,
                "manifest-retention-v1",
                "r5.5.0",
                "prompt-v1",
                "b" * 64,
                "tools-v1",
                "c" * 64,
                "balanced",
                "scripted-v1",
            ),
        )
        connection.execute(
            "INSERT INTO agent_sessions VALUES (?, ?, ?)",
            (session_id, _epoch_us(stored_at), retention_class),
        )
        connection.execute(
            """
            INSERT INTO agent_runs (
                run_id, session_id, status, objective_hash, authority_hash,
                max_model_tokens, max_model_spend_usd, model_profile,
                manifest_hash, created_at_us, started_at_us, finished_at_us,
                revision
            ) VALUES (?, ?, 'completed', ?, ?, 100, '0.01', 'balanced', ?, ?, ?, ?, 1)
            """,
            (
                run_id,
                session_id,
                _hash(f"objective-{run_id}"),
                "d" * 64,
                "a" * 64,
                _epoch_us(stored_at),
                _epoch_us(stored_at),
                _epoch_us(stored_at),
            ),
        )
        connection.execute(
            "INSERT INTO agent_run_continuations VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                "scripted",
                continuation,
                hashlib.sha256(continuation).hexdigest(),
                _epoch_us(stored_at),
            ),
        )
        connection.execute(
            """
            INSERT INTO agent_run_events (
                run_id, run_sequence, event_type, payload_hash,
                occurred_at_us, prev_hash, event_hash
            ) VALUES (?, 1, 'run_completed', ?, ?, NULL, ?)
            """,
            (run_id, "e" * 64, _epoch_us(stored_at), _hash(f"event-{run_id}")),
        )
        connection.execute(
            """
            INSERT INTO agent_approvals (
                request_id, run_id, action_hash, action_payload, status,
                requested_at_us, expires_at_us, operator_id, reason, decided_at_us
            ) VALUES (?, ?, ?, ?, 'approved', ?, ?, 'operator', 'approved', ?)
            """,
            (
                f"approval-{run_id}",
                run_id,
                _hash(f"action-{run_id}"),
                b"redacted-action",
                _epoch_us(stored_at),
                _epoch_us(stored_at + timedelta(hours=1)),
                _epoch_us(stored_at),
            ),
        )
        connection.execute(
            """
            INSERT INTO agent_episode_manifests (
                episode_id, run_id, manifest_hash, replay_identity,
                payload_json, sealed_at_us
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"episode-{run_id}",
                run_id,
                _hash(f"episode-manifest-{run_id}"),
                _hash(f"replay-{run_id}"),
                b'{"schema_version":1}',
                _epoch_us(stored_at),
            ),
        )
        if legal_hold_target is not None:
            target_id = session_id if legal_hold_target == "session" else run_id
            connection.execute(
                """
                INSERT INTO agent_retention (
                    target_kind, target_id, retention_class, retain_until_us,
                    legal_hold, updated_at_us
                ) VALUES (?, ?, 'audit', NULL, 1, ?)
                """,
                (legal_hold_target, target_id, _epoch_us(NOW)),
            )


def _service(tmp_path: Path) -> tuple[AgentDatabase, AgentRetentionService]:
    database = AgentDatabase(tmp_path)
    database.initialize()
    store = SQLiteRawContentRetentionStore(database)
    return database, AgentRetentionService(store=store)


def test_dry_run_uses_closed_30_day_boundary_and_is_content_addressed(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    for age in (29, 30, 31):
        _seed_run(database, run_id=f"run-{age}", age_days=age)

    plan = service.dry_run(as_of=NOW)

    assert [candidate.target_id for candidate in plan.candidates] == [
        "run-31",
        "run-30",
    ]
    assert all(
        candidate.target_kind == "run_continuation" for candidate in plan.candidates
    )
    assert plan.cutoff == NOW - timedelta(days=30)
    assert len(plan.plan_hash) == 64
    assert service.dry_run(as_of=NOW).plan_hash == plan.plan_hash
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM agent_run_continuations"
            ).fetchone()[0]
            == 3
        )


def test_cleanup_deletes_only_exact_raw_content_and_retains_formal_artifacts(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path)
    _seed_run(database, run_id="run-expired", age_days=31)
    _seed_run(
        database,
        run_id="run-audit",
        age_days=31,
        retention_class="audit",
    )
    _seed_run(
        database,
        run_id="run-hold-content",
        age_days=31,
        legal_hold_target="run_continuation",
    )
    _seed_run(
        database,
        run_id="run-hold-run",
        age_days=31,
        legal_hold_target="run",
    )
    _seed_run(
        database,
        run_id="run-hold-session",
        age_days=31,
        legal_hold_target="session",
    )
    plan = service.dry_run(as_of=NOW)

    result = service.execute(
        plan,
        expected_plan_hash=plan.plan_hash,
        approval_id="approval-retention-r5",
        executed_at=NOW,
    )

    assert result.deleted_target_ids == ("run-expired",)
    assert result.plan_hash == plan.plan_hash
    with database.connection() as connection:
        remaining = connection.execute(
            "SELECT run_id FROM agent_run_continuations ORDER BY run_id"
        ).fetchall()
        assert [str(row["run_id"]) for row in remaining] == [
            "run-audit",
            "run-hold-content",
            "run-hold-run",
            "run-hold-session",
        ]
        assert (
            connection.execute("SELECT COUNT(*) FROM agent_run_events").fetchone()[0]
            == 5
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM agent_approvals").fetchone()[0]
            == 5
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM agent_episode_manifests"
            ).fetchone()[0]
            == 5
        )
        audit = connection.execute(
            """
            SELECT category, subject_id, action, payload_hash
            FROM agent_audit_events
            ORDER BY audit_id DESC LIMIT 1
            """
        ).fetchone()
        assert tuple(audit) == (
            "retention",
            plan.plan_hash,
            "raw_content_deleted",
            result.audit_payload_hash,
        )


def test_cleanup_rejects_stale_or_unconfirmed_plan(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    _seed_run(database, run_id="run-expired", age_days=31)
    plan = service.dry_run(as_of=NOW)

    with pytest.raises(RetentionPlanConflict, match="confirmation"):
        service.execute(
            plan,
            expected_plan_hash="f" * 64,
            approval_id="approval-retention-r5",
            executed_at=NOW,
        )

    with database.transaction() as connection:
        payload = b'{"provider_state":"changed"}'
        connection.execute(
            """
            UPDATE agent_run_continuations
            SET payload_json=?, payload_hash=?
            WHERE run_id='run-expired'
            """,
            (payload, hashlib.sha256(payload).hexdigest()),
        )
    with pytest.raises(RetentionPlanConflict, match="changed"):
        service.execute(
            plan,
            expected_plan_hash=plan.plan_hash,
            approval_id="approval-retention-r5",
            executed_at=NOW,
        )


def test_retention_plan_rejects_nonstandard_cutoff() -> None:
    with pytest.raises(ValueError, match="fixed at 30 days"):
        RetentionPlan.create(
            as_of=NOW,
            cutoff=NOW - timedelta(days=31),
            candidates=(),
        )


def test_retention_plan_rejects_forged_public_construction() -> None:
    with pytest.raises(ValueError, match="plan_hash"):
        RetentionPlan(
            as_of=NOW,
            cutoff=NOW - timedelta(days=30),
            candidates=(),
            plan_hash="f" * 64,
        )
