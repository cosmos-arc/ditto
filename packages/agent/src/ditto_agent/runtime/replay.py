"""Deterministic Agent episode replay without model or tool execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    EpisodeToolEffect,
    EpisodeToolResultRecord,
    decode_episode,
    encode_episode,
)


class EpisodeReplayError(RuntimeError):
    """An episode failed closed before any recorded result was returned."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


@dataclass(frozen=True, slots=True)
class EpisodeReplayResult:
    """Authenticated recorded events/results yielded by an offline replay."""

    replay_identity: str
    events: tuple[EpisodeEventRecord, ...]
    tool_results: tuple[EpisodeToolResultRecord, ...]
    skipped_side_effect_call_ids: tuple[str, ...]


class EpisodeReplayer:
    """Verify a sealed episode and return records without invoking dependencies."""

    def replay(self, episode: AgentEpisodeManifest) -> EpisodeReplayResult:
        """Replay only durable events and results; suppress every side effect."""
        if not isinstance(cast(object, episode), AgentEpisodeManifest):
            raise EpisodeReplayError(
                "Replay requires an Agent episode manifest",
                reason_code="episode_type_invalid",
            )
        if any(
            not result.evidence_refs and not result.artifact_refs
            for result in episode.tool_results
        ):
            raise EpisodeReplayError(
                "Episode result lacks a durable evidence or artifact reference",
                reason_code="episode_tool_result_reference_missing",
            )
        if not episode.verify_manifest_hash():
            raise EpisodeReplayError(
                "Episode manifest hash verification failed",
                reason_code="episode_manifest_hash_invalid",
            )
        if not episode.verify_replay_identity():
            raise EpisodeReplayError(
                "Episode replay identity verification failed",
                reason_code="episode_replay_identity_invalid",
            )
        try:
            authenticated = decode_episode(encode_episode(episode))
        except (TypeError, ValueError) as exc:
            raise EpisodeReplayError(
                "Episode structure verification failed",
                reason_code="episode_structure_invalid",
            ) from exc
        previous_hash: str | None = None
        for event in authenticated.events:
            if event.prev_hash != previous_hash or not event.verify_event_hash():
                raise EpisodeReplayError(
                    "Episode event chain verification failed",
                    reason_code="episode_event_chain_invalid",
                )
            previous_hash = event.event_hash
        return EpisodeReplayResult(
            replay_identity=authenticated.replay_identity,
            events=authenticated.events,
            tool_results=authenticated.tool_results,
            skipped_side_effect_call_ids=tuple(
                call.call_id
                for call in authenticated.tool_calls
                if call.effect is EpisodeToolEffect.SIDE_EFFECT
            ),
        )


__all__ = ["EpisodeReplayError", "EpisodeReplayResult", "EpisodeReplayer"]
