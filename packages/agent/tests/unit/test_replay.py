from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from ditto_agent.contracts.runtime import AgentManifest, ModelProfile, RunStatus
from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    EpisodeToolCallRecord,
    EpisodeToolEffect,
    EpisodeToolResultRecord,
)
from ditto_agent.runtime.replay import EpisodeReplayer, EpisodeReplayError

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _episode() -> AgentEpisodeManifest:
    first = EpisodeEventRecord.create(
        event_id=1,
        run_id="run-replay-001",
        run_sequence=1,
        event_type="tool_called",
        payload_hash=_hash("arguments"),
        occurred_at=NOW,
        prev_hash=None,
    )
    second = EpisodeEventRecord.create(
        event_id=2,
        run_id="run-replay-001",
        run_sequence=2,
        event_type="tool_result_recorded",
        payload_hash=_hash("result"),
        occurred_at=NOW + timedelta(seconds=1),
        prev_hash=first.event_hash,
    )
    return AgentEpisodeManifest(
        episode_id="episode-replay-001",
        run_id="run-replay-001",
        input_hash=_hash("input"),
        authority_hash=_hash("authority"),
        temporal_context_hash=_hash("temporal"),
        agent_manifest=AgentManifest(
            manifest_id="manifest-replay-v1",
            agent_version="r5.0.0",
            prompt_version="prompt-v1",
            prompt_hash=_hash("prompt"),
            tool_schema_version="tools-v1",
            tool_schema_hash=_hash("tools"),
            model_profile=ModelProfile.BALANCED,
            model_snapshot="scripted-model-v1",
        ),
        final_status=RunStatus.COMPLETED,
        events=(first, second),
        tool_calls=(
            EpisodeToolCallRecord(
                call_id="call-side-effect-001",
                tool_name="save_strategy_draft",
                arguments_hash=_hash("arguments"),
                effect=EpisodeToolEffect.SIDE_EFFECT,
                action_hash=_hash("action"),
            ),
        ),
        tool_results=(
            EpisodeToolResultRecord(
                call_id="call-side-effect-001",
                result_hash=_hash("result"),
                evidence_refs=(),
                artifact_refs=("receipt://draft/001",),
            ),
        ),
        final_output_hash=_hash("output"),
        sealed_at=NOW + timedelta(seconds=2),
    )


def test_replay_is_deterministic_and_returns_recorded_side_effect_receipt_only() -> (
    None
):
    episode = _episode()
    replayer = EpisodeReplayer()

    first = replayer.replay(episode)
    second = replayer.replay(episode)

    assert first == second
    assert first.events == episode.events
    assert first.tool_results == episode.tool_results
    assert first.skipped_side_effect_call_ids == ("call-side-effect-001",)
    assert first.replay_identity == episode.replay_identity


def test_replay_fails_closed_on_manifest_or_result_reference_tamper() -> None:
    episode = _episode()
    object.__setattr__(episode, "manifest_hash", "0" * 64)

    with pytest.raises(EpisodeReplayError) as manifest_info:
        EpisodeReplayer().replay(episode)

    assert manifest_info.value.reason_code == "episode_manifest_hash_invalid"

    restored = _episode()
    missing_reference = restored.tool_results[0]
    object.__setattr__(missing_reference, "artifact_refs", ())
    object.__setattr__(restored, "tool_results", (missing_reference,))
    with pytest.raises(EpisodeReplayError) as result_info:
        EpisodeReplayer().replay(restored)

    assert result_info.value.reason_code == "episode_tool_result_reference_missing"
