"""Migration and tamper tests for immutable shadow outcome feedback."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_agent._canonical import canonical_sha256
from ditto_agent.outcome_feedback import (
    DecisionOpinionAdoption,
    DecisionOutcomeFeedback,
    DecisionOutcomeLinker,
    DecisionOutcomeObservation,
    DecisionOutcomeObservationInput,
)
from ditto_agent.storage.sqlite import decision_opinion_schema as schema
from ditto_agent.storage.sqlite.decision_opinion_store import (
    DecisionOpinionShadowDatabase,
    DecisionOpinionShadowReader,
    DecisionOpinionShadowWriter,
)
from ditto_agent.storage.sqlite.decision_outcome_feedback_store import (
    DecisionOutcomeFeedbackShadowReader,
    DecisionOutcomeFeedbackShadowWriter,
)
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentIntegrityError,
    AgentSchemaError,
)
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
)
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext


def _opinion() -> DecisionOpinionRecord:
    generated_at = datetime(2026, 8, 16, 8, 1, tzinfo=UTC)
    identity = {
        "schema_version": 1,
        "status": "completed",
        "v3_artifact_id": "daily-decision-v3:strategy-1:2026-08-15",
        "v3_evidence_hash": "a" * 64,
        "v3_readiness": "ready",
        "summary": "V3 remains authoritative.",
        "dissent": "Tail risk deserves review.",
        "uncertainty": "This is a shadow interpretation.",
        "evidence_refs": ("daily-decision-v3:strategy-1:2026-08-15",),
        "blocking_reasons": (),
        "reason_code": None,
        "model_profile": "balanced",
        "prompt_hash": "b" * 64,
        "provider_id": "scripted",
        "generated_at": generated_at,
    }
    digest = canonical_sha256(identity)
    return DecisionOpinionRecord(
        schema_version=1,
        opinion_id=f"decision-opinion-{digest}",
        shadow_outcome_id=f"decision-shadow-{digest}",
        status="completed",
        v3_artifact_id="daily-decision-v3:strategy-1:2026-08-15",
        v3_evidence_hash="a" * 64,
        v3_readiness="ready",
        summary="V3 remains authoritative.",
        dissent="Tail risk deserves review.",
        uncertainty="This is a shadow interpretation.",
        evidence_refs=("daily-decision-v3:strategy-1:2026-08-15",),
        blocking_reasons=(),
        reason_code=None,
        model_profile="balanced",
        prompt_hash="b" * 64,
        provider_id="scripted",
        generated_at=generated_at,
        opinion_hash=digest,
    )


def _opinion_version(*, summary: str, generated_at: datetime) -> DecisionOpinionRecord:
    base = _opinion()
    identity = {
        "schema_version": base.schema_version,
        "status": base.status,
        "v3_artifact_id": base.v3_artifact_id,
        "v3_evidence_hash": base.v3_evidence_hash,
        "v3_readiness": base.v3_readiness,
        "summary": summary,
        "dissent": base.dissent,
        "uncertainty": base.uncertainty,
        "evidence_refs": base.evidence_refs,
        "blocking_reasons": base.blocking_reasons,
        "reason_code": base.reason_code,
        "model_profile": base.model_profile,
        "prompt_hash": base.prompt_hash,
        "provider_id": base.provider_id,
        "generated_at": generated_at,
    }
    digest = canonical_sha256(identity)
    return replace(
        base,
        opinion_id=f"decision-opinion-{digest}",
        shadow_outcome_id=f"decision-shadow-{digest}",
        summary=summary,
        generated_at=generated_at,
        opinion_hash=digest,
    )


def _feedback(*, calibration: int = 9_000) -> DecisionOutcomeFeedback:
    opinion = _opinion()
    observation = DecisionOutcomeObservation.create(
        DecisionOutcomeObservationInput(
            opinion_id=opinion.opinion_id,
            shadow_outcome_id=opinion.shadow_outcome_id,
            outcome_kind="next_session_review",
            outcome_period_start=datetime(2026, 8, 17, 1, 30, tzinfo=UTC),
            outcome_period_end=datetime(2026, 8, 17, 7, 0, tzinfo=UTC),
            outcome_known_at=datetime(2026, 8, 17, 8, 0, tzinfo=UTC),
            published_at=datetime(2026, 8, 17, 7, 30, tzinfo=UTC),
            source_snapshot_id="outcome-snapshot-1",
            evidence_refs=("outcome:strategy-1:2026-08-17",),
            adoption=DecisionOpinionAdoption.REVIEWED,
            accuracy_basis_points=10_000,
            calibration_basis_points=calibration,
            is_holdout=False,
        )
    )
    return DecisionOutcomeLinker().link(
        opinion=opinion,
        observation=observation,
        context=EvidenceTemporalContext(
            decision_time=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 17, 8, 30, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 17, 8, 0, tzinfo=UTC),
            source_snapshot_id="outcome-snapshot-1",
        ),
        linked_at=datetime(2026, 8, 17, 9, 0, tzinfo=UTC),
    )


def _create_v1_database(data_root: Path) -> DecisionOpinionShadowDatabase:
    database = DecisionOpinionShadowDatabase(data_root)
    database.path.parent.mkdir(parents=True)
    with sqlite3.connect(database.path) as connection:
        for statement in schema.schema_body_statements(
            schema.load_schema_sql(version=1), version=1
        ):
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
    return database


def test_shadow_v1_migrates_forward_without_changing_historical_opinion(
    tmp_path: Path,
) -> None:
    database = _create_v1_database(tmp_path)
    assert DecisionOpinionShadowWriter(database).append_opinion(_opinion())
    before = DecisionOpinionShadowReader(database).get_opinion(_opinion().opinion_id)
    database.close_all()

    migrated = DecisionOpinionShadowDatabase(tmp_path)
    migrated.initialize()

    assert (
        migrated.get_connection().execute("PRAGMA user_version").fetchone()[0]
        == schema.USER_VERSION
    )
    assert (
        DecisionOpinionShadowReader(migrated).get_opinion(_opinion().opinion_id)
        == before
    )
    assert "shadow_outcome_feedback" in migrated.catalog_names()
    assert "shadow_outcome_feedback_events" in migrated.catalog_names()
    assert "shadow_decision_opinions_artifact_generated" in migrated.catalog_names()


@pytest.mark.parametrize("state", ["drift", "future"])
def test_shadow_migration_fails_closed_without_partial_v2_state(
    tmp_path: Path,
    state: str,
) -> None:
    database = _create_v1_database(tmp_path)
    connection = database.get_connection()
    if state == "drift":
        connection.execute("DROP TRIGGER shadow_decision_events_no_delete")
    else:
        connection.execute(f"PRAGMA user_version={schema.USER_VERSION + 1}")
    connection.commit()
    database.close_all()

    candidate = DecisionOpinionShadowDatabase(tmp_path)
    with pytest.raises(AgentSchemaError):
        candidate.initialize()

    with sqlite3.connect(candidate.path) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == (
            1 if state == "drift" else schema.USER_VERSION + 1
        )
        assert (
            raw.execute(
                "SELECT COUNT(*) FROM sqlite_schema "
                "WHERE name='shadow_outcome_feedback'"
            ).fetchone()[0]
            == 0
        )


def test_latest_opinion_lookup_is_exact_and_newest_first(tmp_path: Path) -> None:
    database = DecisionOpinionShadowDatabase(tmp_path)
    database.initialize()
    writer = DecisionOpinionShadowWriter(database)
    older = _opinion_version(
        summary="Older shadow opinion.",
        generated_at=datetime(2026, 8, 16, 8, 1, tzinfo=UTC),
    )
    newer = _opinion_version(
        summary="Newest shadow opinion.",
        generated_at=datetime(2026, 8, 16, 8, 2, tzinfo=UTC),
    )
    try:
        writer.append_opinion(older)
        writer.append_opinion(newer)
        reader = DecisionOpinionShadowReader(database)
        assert reader.get_latest_by_v3_artifact_id(older.v3_artifact_id) == newer
        assert reader.get_latest_by_v3_artifact_id("daily-decision-v3:missing") is None
    finally:
        database.close_all()


def test_feedback_and_event_append_atomically_and_exact_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    database = DecisionOpinionShadowDatabase(tmp_path)
    database.initialize()
    assert DecisionOpinionShadowWriter(database).append_opinion(_opinion())
    writer = DecisionOutcomeFeedbackShadowWriter(database)
    reader = DecisionOutcomeFeedbackShadowReader(database)
    feedback = _feedback()

    assert writer.append_feedback(feedback)
    assert writer.append_feedback(feedback) is False
    assert reader.get_feedback(feedback.feedback_id) == feedback
    events = reader.list_events(feedback.feedback_id)
    assert len(events) == 1
    assert events[0].event_type == "shadow_outcome_feedback_persisted"
    assert reader.count_feedback() == 1


def test_feedback_is_append_only_and_payload_tamper_fails_reauthentication(
    tmp_path: Path,
) -> None:
    database = DecisionOpinionShadowDatabase(tmp_path)
    database.initialize()
    DecisionOpinionShadowWriter(database).append_opinion(_opinion())
    feedback = _feedback()
    DecisionOutcomeFeedbackShadowWriter(database).append_feedback(feedback)
    connection = database.get_connection()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE shadow_outcome_feedback SET payload_json=? WHERE feedback_id=?",
            (b"{}", feedback.feedback_id),
        )
    connection.rollback()
    connection.execute("DROP TRIGGER shadow_outcome_feedback_no_update")
    connection.execute(
        "UPDATE shadow_outcome_feedback SET payload_json=? WHERE feedback_id=?",
        (b"{}", feedback.feedback_id),
    )
    connection.commit()

    with pytest.raises(AgentIntegrityError):
        DecisionOutcomeFeedbackShadowReader(database).get_feedback(feedback.feedback_id)


def test_one_opinion_cannot_be_relinked_to_conflicting_outcome_metrics(
    tmp_path: Path,
) -> None:
    database = DecisionOpinionShadowDatabase(tmp_path)
    database.initialize()
    DecisionOpinionShadowWriter(database).append_opinion(_opinion())
    writer = DecisionOutcomeFeedbackShadowWriter(database)
    writer.append_feedback(_feedback())

    with pytest.raises(AgentConflictError):
        writer.append_feedback(_feedback(calibration=1_000))


def test_feedback_constructor_rejects_identity_tamper() -> None:
    with pytest.raises(ValueError, match="feedback_hash"):
        replace(_feedback(), feedback_hash="f" * 64)
