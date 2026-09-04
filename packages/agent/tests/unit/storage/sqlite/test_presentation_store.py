"""Sanitized Agent presentation projection persistence contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.presentation import (
    AgentContextPresentation,
    AgentGuardrailPresentation,
    AgentPresentationConflict,
    AgentPresentationError,
    AgentRunPresentation,
    AgentToolPresentation,
    AgentUsagePresentation,
)
from ditto_agent.storage.sqlite.presentation_store import (
    AgentPresentationDatabase,
    AgentPresentationReader,
    AgentPresentationWriter,
)

NOW = datetime(2026, 8, 18, 7, 0, tzinfo=UTC)


def _projection(*, version: int = 1) -> AgentRunPresentation:
    return AgentRunPresentation(
        run_id="run-presentation-1",
        objective="Explain the exact PIT evidence.",
        context=AgentContextPresentation(
            context_type="daily_decision",
            context_id="strategy-a:paper-a:2026-08-19:artifact-v3",
        ),
        status=RunStatus.COMPLETED,
        output_summary="Momentum is supported by snapshot-bound evidence.",
        tool_records=(
            AgentToolPresentation(
                call_id="call-1",
                tool_name="read_factor_evidence",
                arguments_hash="a" * 64,
                result_hash="b" * 64,
                evidence_refs=("evidence-1",),
                artifact_refs=("artifact-1",),
            ),
        ),
        evidence_refs=("evidence-1",),
        artifact_refs=("artifact-1",),
        guardrail=AgentGuardrailPresentation(status="passed", reason_code=None),
        usage=AgentUsagePresentation(
            model_attempts=1,
            model_turns=1,
            tool_calls=1,
            retries=0,
            total_tokens=321,
            model_spend_usd=Decimal("0.12"),
            exhausted_reason=None,
        ),
        failure_code=None,
        projection_version=version,
        updated_at=NOW + timedelta(seconds=version),
    )


def test_presentation_projection_recovers_after_restart_and_is_separate(
    tmp_path: Path,
) -> None:
    database = AgentPresentationDatabase(tmp_path)
    database.initialize()
    writer = AgentPresentationWriter(database)
    writer.put(_projection())
    assert AgentPresentationReader(database).get("run-presentation-1") == _projection()
    presentation_path = database.path
    database.close()

    restarted = AgentPresentationDatabase(tmp_path)
    restarted.initialize()
    try:
        assert restarted.path == presentation_path
        assert (
            AgentPresentationReader(restarted).get("run-presentation-1")
            == _projection()
        )
    finally:
        restarted.close()


def test_presentation_projection_version_is_monotonic(tmp_path: Path) -> None:
    database = AgentPresentationDatabase(tmp_path)
    database.initialize()
    writer = AgentPresentationWriter(database)
    try:
        writer.put(_projection(version=2))
        with pytest.raises(AgentPresentationConflict):
            writer.put(_projection(version=1))
        assert AgentPresentationReader(database).get(
            "run-presentation-1"
        ) == _projection(version=2)
    finally:
        database.close()


def test_corrupt_presentation_payload_fails_closed(tmp_path: Path) -> None:
    database = AgentPresentationDatabase(tmp_path)
    database.initialize()
    writer = AgentPresentationWriter(database)
    try:
        writer.put(_projection())
        database.connection.execute(
            "UPDATE agent_run_presentation SET payload_json=? WHERE run_id=?",
            (b'{"leaked":"unexpected"}', "run-presentation-1"),
        )
        database.connection.commit()

        with pytest.raises(AgentPresentationError):
            AgentPresentationReader(database).get("run-presentation-1")
    finally:
        database.close()


def test_legacy_projection_without_execution_plan_remains_readable(
    tmp_path: Path,
) -> None:
    database = AgentPresentationDatabase(tmp_path)
    database.initialize()
    writer = AgentPresentationWriter(database)
    try:
        writer.put(_projection())
        row = database.connection.execute(
            "SELECT payload_json FROM agent_run_presentation WHERE run_id=?",
            ("run-presentation-1",),
        ).fetchone()
        raw = orjson.loads(row["payload_json"])
        raw.pop("execution_plan")
        legacy_payload = canonical_bytes(raw)
        database.connection.execute(
            """
            UPDATE agent_run_presentation
            SET payload_hash=?, payload_json=?
            WHERE run_id=?
            """,
            (
                hashlib.sha256(legacy_payload).hexdigest(),
                legacy_payload,
                "run-presentation-1",
            ),
        )
        database.connection.commit()

        assert (
            AgentPresentationReader(database).get("run-presentation-1") == _projection()
        )
    finally:
        database.close()
