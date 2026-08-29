"""Immutable Agent episode persistence over the dedicated SQLite database."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    decode_episode,
    encode_episode,
)
from ditto_agent.storage.sqlite._codec import datetime_from_epoch_us, epoch_us
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentIntegrityError,
    AgentPersistenceError,
)


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


def _integrity(message: str, reason_code: str) -> AgentIntegrityError:
    return AgentIntegrityError(message, reason_code=reason_code)


def _event_from_row(row: sqlite3.Row) -> EpisodeEventRecord:
    return EpisodeEventRecord(
        event_id=int(row["event_id"]),
        run_id=str(row["run_id"]),
        run_sequence=int(row["run_sequence"]),
        event_type=str(row["event_type"]),
        payload_hash=str(row["payload_hash"]),
        occurred_at=datetime_from_epoch_us(
            int(row["occurred_at_us"]), field="event occurred_at"
        ),
        prev_hash=None if row["prev_hash"] is None else str(row["prev_hash"]),
        event_hash=str(row["event_hash"]),
    )


class AgentEpisodeWriter:
    """Seal one exact terminal run as an immutable episode."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        try:
            with self._database.transaction() as connection:
                yield connection
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent episode write failed",
                reason_code="agent_episode_write_failed",
            ) from exc

    @staticmethod
    def verify_run_identity(
        connection: sqlite3.Connection, episode: AgentEpisodeManifest
    ) -> None:
        """Require a terminal durable run with the episode's exact identities."""
        row = connection.execute(
            """
            SELECT status, objective_hash, authority_hash, manifest_hash
            FROM agent_runs
            WHERE run_id=?
            """,
            (episode.run_id,),
        ).fetchone()
        if row is None:
            raise _conflict("Episode run does not exist", "agent_episode_run_missing")
        durable = (
            RunStatus(str(row["status"])),
            str(row["objective_hash"]),
            str(row["authority_hash"]),
            str(row["manifest_hash"]),
        )
        expected = (
            episode.final_status,
            episode.input_hash,
            episode.authority_hash,
            episode.agent_manifest.manifest_hash,
        )
        if durable != expected:
            raise _conflict(
                "Episode identity conflicts with its durable run",
                "agent_episode_run_conflict",
            )

    @staticmethod
    def verify_event_identity(
        connection: sqlite3.Connection, episode: AgentEpisodeManifest
    ) -> None:
        """Require the episode to contain the exact durable run event chain."""
        rows = connection.execute(
            """
            SELECT event_id, run_id, run_sequence, event_type, payload_hash,
                   occurred_at_us, prev_hash, event_hash
            FROM agent_run_events
            WHERE run_id=?
            ORDER BY run_sequence
            """,
            (episode.run_id,),
        ).fetchall()
        try:
            durable = tuple(_event_from_row(row) for row in rows)
        except (TypeError, ValueError) as exc:
            raise _integrity(
                "Durable run events cannot be authenticated",
                "agent_episode_event_corrupt",
            ) from exc
        if durable != episode.events:
            raise _conflict(
                "Episode events differ from the durable run event chain",
                "agent_episode_event_conflict",
            )

    def put(self, episode: AgentEpisodeManifest) -> AgentEpisodeManifest:
        """Persist a terminal episode or accept only an exact replay."""
        if not isinstance(cast(object, episode), AgentEpisodeManifest):
            raise TypeError("episode must be an AgentEpisodeManifest")
        if not episode.verify_manifest_hash() or not episode.verify_replay_identity():
            raise ValueError("episode identity is invalid")
        payload = encode_episode(episode)
        sealed_at_us = epoch_us(episode.sealed_at, field="episode sealed_at")
        values = (
            episode.episode_id,
            episode.run_id,
            episode.manifest_hash,
            episode.replay_identity,
            payload,
            sealed_at_us,
        )
        with self._transaction() as connection:
            self.verify_run_identity(connection, episode)
            self.verify_event_identity(connection, episode)
            row = connection.execute(
                """
                SELECT episode_id, run_id, manifest_hash, replay_identity,
                       payload_json, sealed_at_us
                FROM agent_episode_manifests
                WHERE episode_id=? OR run_id=?
                """,
                (episode.episode_id, episode.run_id),
            ).fetchone()
            if row is not None:
                durable = (
                    row["episode_id"],
                    row["run_id"],
                    row["manifest_hash"],
                    row["replay_identity"],
                    row["payload_json"],
                    row["sealed_at_us"],
                )
                if durable != values:
                    raise _conflict(
                        "Episode replay conflicts with durable identity",
                        "agent_episode_conflict",
                    )
                return episode
            connection.execute(
                """
                INSERT INTO agent_episode_manifests (
                    episode_id, run_id, manifest_hash, replay_identity,
                    payload_json, sealed_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            append_audit_event(
                connection,
                category="episode",
                subject_id=episode.episode_id,
                action="sealed",
                payload_hash=canonical_sha256(
                    {
                        "manifest_hash": episode.manifest_hash,
                        "replay_identity": episode.replay_identity,
                    }
                ),
                occurred_at=episode.sealed_at,
            )
        return episode


class AgentEpisodeReader:
    """Read and re-authenticate immutable episode manifests."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database

    def get(self, episode_id: str) -> AgentEpisodeManifest | None:
        """Return one verified episode, failing closed on any durable drift."""
        try:
            connection = self._database.get_connection()
            row = connection.execute(
                """
                SELECT episode_id, run_id, manifest_hash, replay_identity,
                       payload_json, sealed_at_us
                FROM agent_episode_manifests
                WHERE episode_id=?
                """,
                (episode_id,),
            ).fetchone()
            if row is None:
                return None
            payload = row["payload_json"]
            if not isinstance(payload, bytes):
                raise _integrity(
                    "Durable episode payload has an invalid storage type",
                    "agent_episode_payload_type_invalid",
                )
            episode = decode_episode(payload)
            durable = (
                str(row["episode_id"]),
                str(row["run_id"]),
                str(row["manifest_hash"]),
                str(row["replay_identity"]),
                int(row["sealed_at_us"]),
            )
            expected = (
                episode.episode_id,
                episode.run_id,
                episode.manifest_hash,
                episode.replay_identity,
                epoch_us(episode.sealed_at, field="episode sealed_at"),
            )
            if durable != expected:
                raise _integrity(
                    "Durable episode columns conflict with its payload",
                    "agent_episode_column_drift",
                )
            try:
                AgentEpisodeWriter.verify_run_identity(connection, episode)
                AgentEpisodeWriter.verify_event_identity(connection, episode)
            except AgentConflictError as exc:
                raise _integrity(
                    "Durable episode no longer matches its sealed run",
                    "agent_episode_run_drift",
                ) from exc
            return episode
        except AgentPersistenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _integrity(
                "Durable episode payload cannot be authenticated",
                "agent_episode_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent episode read failed",
                reason_code="agent_episode_read_failed",
            ) from exc


__all__ = ["AgentEpisodeReader", "AgentEpisodeWriter"]
