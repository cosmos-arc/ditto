from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    EpisodeToolCallRecord,
    EpisodeToolEffect,
    EpisodeToolResultRecord,
    encode_episode,
)
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.episode_store import (
    AgentEpisodeReader,
    AgentEpisodeWriter,
)
from ditto_agent.storage.sqlite.errors import AgentConflictError, AgentPersistenceError
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _agent_manifest() -> AgentManifest:
    return AgentManifest(
        manifest_id="manifest-episode-v1",
        agent_version="r5.0.0",
        prompt_version="prompt-v1",
        prompt_hash=_hash("prompt-v1"),
        tool_schema_version="tools-v1",
        tool_schema_hash=_hash("tools-v1"),
        model_profile=ModelProfile.BALANCED,
        model_snapshot="scripted-model-v1",
    )


def _episode(
    events: tuple[EpisodeEventRecord, ...],
    *,
    final_output_hash: str | None = None,
) -> AgentEpisodeManifest:
    return AgentEpisodeManifest(
        episode_id="episode-001",
        run_id="run-001",
        input_hash=_hash("objective"),
        authority_hash=_hash("authority"),
        temporal_context_hash=_hash("temporal-context"),
        agent_manifest=_agent_manifest(),
        final_status=RunStatus.COMPLETED,
        events=events,
        tool_calls=(
            EpisodeToolCallRecord(
                call_id="call-read-001",
                tool_name="experiment_summary",
                arguments_hash=_hash("read-arguments"),
                effect=EpisodeToolEffect.READ_ONLY,
                action_hash=None,
            ),
            EpisodeToolCallRecord(
                call_id="call-write-001",
                tool_name="save_strategy_draft",
                arguments_hash=_hash("write-arguments"),
                effect=EpisodeToolEffect.SIDE_EFFECT,
                action_hash=_hash("approved-action"),
            ),
        ),
        tool_results=(
            EpisodeToolResultRecord(
                call_id="call-read-001",
                result_hash=_hash("read-result"),
                evidence_refs=("evidence-001",),
                artifact_refs=(),
            ),
            EpisodeToolResultRecord(
                call_id="call-write-001",
                result_hash=_hash("write-receipt"),
                evidence_refs=(),
                artifact_refs=("receipt://draft/001",),
            ),
        ),
        final_output_hash=final_output_hash or _hash("final-output"),
        sealed_at=NOW + timedelta(seconds=5),
    )


def _persisted_events(writer: AgentStoreWriter) -> tuple[EpisodeEventRecord, ...]:
    first = writer.append_run_event(
        run_id="run-001",
        event_type="tool_called",
        payload_hash=_hash("read-arguments"),
        occurred_at=NOW + timedelta(seconds=1),
    )
    second = writer.append_run_event(
        run_id="run-001",
        event_type="tool_result_recorded",
        payload_hash=_hash("read-result"),
        occurred_at=NOW + timedelta(seconds=2),
    )
    return tuple(
        EpisodeEventRecord(
            event_id=item.event_id,
            run_id=item.run_id,
            run_sequence=item.run_sequence,
            event_type=item.event_type,
            payload_hash=item.payload_hash,
            occurred_at=item.occurred_at,
            prev_hash=item.prev_hash,
            event_hash=item.event_hash,
        )
        for item in (first, second)
    )


def _store(
    tmp_path: Path,
) -> tuple[AgentStoreWriter, AgentEpisodeWriter, AgentEpisodeReader]:
    database = AgentDatabase(tmp_path)
    database.initialize()
    writer = AgentStoreWriter(database)
    manifest = _agent_manifest()
    writer.put_manifest(manifest)
    writer.create_session(
        AgentSession(
            session_id="session-001",
            created_at=NOW,
            retention_class=RetentionClass.AUDIT,
        )
    )
    writer.create_run(
        AgentRun(
            run_id="run-001",
            session_id="session-001",
            status=RunStatus.QUEUED,
            objective="objective",
            authority_hash=_hash("authority"),
            max_model_tokens=4_096,
            max_model_spend_usd=Decimal("0.25"),
            model_profile=ModelProfile.BALANCED,
            manifest_hash=manifest.manifest_hash,
            created_at=NOW,
        )
    )
    return writer, AgentEpisodeWriter(database), AgentEpisodeReader(database)


def test_episode_binds_versions_events_calls_results_and_persists_exactly(
    tmp_path: Path,
) -> None:
    run_writer, episode_writer, episode_reader = _store(tmp_path)
    events = _persisted_events(run_writer)
    run_writer.transition_run(
        run_id="run-001",
        expected_revision=0,
        target=RunStatus.RUNNING,
        occurred_at=NOW + timedelta(seconds=3),
    )
    run_writer.transition_run(
        run_id="run-001",
        expected_revision=1,
        target=RunStatus.COMPLETED,
        occurred_at=NOW + timedelta(seconds=4),
    )
    episode = _episode(events)

    assert episode.verify_manifest_hash()
    assert episode.verify_replay_identity()
    assert episode.agent_manifest.prompt_hash == _hash("prompt-v1")
    assert episode.events[-1].prev_hash == episode.events[0].event_hash

    assert episode_writer.put(episode) == episode
    assert episode_writer.put(episode) == episode
    assert episode_reader.get(episode.episode_id) == episode
    assert len({encode_episode(_episode(events)) for _ in range(100)}) == 1

    with pytest.raises(AgentPersistenceError) as sealed_info:
        run_writer.append_run_event(
            run_id="run-001",
            event_type="late_event",
            payload_hash=_hash("late"),
            occurred_at=NOW + timedelta(seconds=6),
        )

    assert sealed_info.value.reason_code == "agent_write_failed"

    with pytest.raises(AgentConflictError):
        episode_writer.put(_episode(events, final_output_hash=_hash("drift")))


def test_episode_rejects_event_chain_or_tool_result_reference_drift() -> None:
    event = EpisodeEventRecord.create(
        event_id=1,
        run_id="run-001",
        run_sequence=1,
        event_type="tool_called",
        payload_hash=_hash("payload"),
        occurred_at=NOW,
        prev_hash=None,
    )

    with pytest.raises(ValueError, match="event hash chain"):
        _episode((replace(event, payload_hash=_hash("tampered")),))
    with pytest.raises(ValueError, match="tool results"):
        replace(
            _episode((event,)),
            tool_results=(
                EpisodeToolResultRecord(
                    call_id="missing-call",
                    result_hash=_hash("result"),
                    evidence_refs=("evidence-missing",),
                    artifact_refs=(),
                ),
            ),
        )
