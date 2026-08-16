"""Immutable persistence for PIT-bound DecisionOpinion outcome feedback."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import orjson

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.outcome_feedback import (
    DecisionOpinionAdoption,
    DecisionOutcomeFeedback,
)
from ditto_agent.storage.sqlite._codec import datetime_from_epoch_us, epoch_us
from ditto_agent.storage.sqlite.decision_opinion_store import (
    DecisionOpinionShadowDatabase,
)
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentIntegrityError,
    AgentPersistenceError,
)

_EVENT_TYPE = "shadow_outcome_feedback_persisted"


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


def _integrity(message: str, reason_code: str) -> AgentIntegrityError:
    return AgentIntegrityError(message, reason_code=reason_code)


def _feedback_payload(feedback: DecisionOutcomeFeedback) -> dict[str, object]:
    return {
        field_name: getattr(feedback, field_name)
        for field_name in DecisionOutcomeFeedback.__dataclass_fields__
    }


def _event_hash(*, feedback_id: str, payload_hash: str, occurred_at: datetime) -> str:
    return canonical_sha256(
        {
            "event_sequence": 1,
            "event_type": _EVENT_TYPE,
            "feedback_id": feedback_id,
            "payload_hash": payload_hash,
            "occurred_at": occurred_at,
        }
    )


class DecisionOutcomeFeedbackShadowWriter:
    """Append feedback and its event atomically after opinion persistence."""

    def __init__(self, database: DecisionOpinionShadowDatabase) -> None:
        self._database = database

    def append_feedback(self, feedback: DecisionOutcomeFeedback) -> bool:
        """Append once; return False only for an exact immutable replay."""
        if not isinstance(cast(object, feedback), DecisionOutcomeFeedback):
            raise TypeError("feedback must be DecisionOutcomeFeedback")
        if not feedback.verify_integrity():
            raise _integrity(
                "Decision outcome feedback identity is invalid",
                "decision_outcome_feedback_invalid",
            )
        payload = canonical_bytes(_feedback_payload(feedback))
        known_at_us = epoch_us(
            feedback.outcome_known_at, field="feedback outcome_known_at"
        )
        linked_at_us = epoch_us(feedback.linked_at, field="feedback linked_at")
        event_hash = _event_hash(
            feedback_id=feedback.feedback_id,
            payload_hash=feedback.feedback_hash,
            occurred_at=feedback.linked_at,
        )
        try:
            with self._database.transaction() as connection:
                existing = connection.execute(
                    """
                    SELECT feedback_id, opinion_id, observation_id,
                           feedback_hash, payload_json
                    FROM shadow_outcome_feedback
                    WHERE feedback_id=? OR opinion_id=? OR observation_id=?
                       OR feedback_hash=?
                    """,
                    (
                        feedback.feedback_id,
                        feedback.opinion_id,
                        feedback.observation_id,
                        feedback.feedback_hash,
                    ),
                ).fetchone()
                if existing is not None:
                    durable = (
                        str(existing["feedback_id"]),
                        str(existing["opinion_id"]),
                        str(existing["observation_id"]),
                        str(existing["feedback_hash"]),
                        existing["payload_json"],
                    )
                    expected = (
                        feedback.feedback_id,
                        feedback.opinion_id,
                        feedback.observation_id,
                        feedback.feedback_hash,
                        payload,
                    )
                    if durable != expected:
                        raise _conflict(
                            "Decision outcome feedback conflicts with shadow state",
                            "decision_outcome_feedback_conflict",
                        )
                    return False
                connection.execute(
                    """
                    INSERT INTO shadow_outcome_feedback (
                        feedback_id, opinion_id, shadow_outcome_id, opinion_hash,
                        observation_id, observation_hash, outcome_known_at_us,
                        linked_at_us, source_snapshot_id, adoption,
                        accuracy_basis_points, calibration_basis_points,
                        memory_promotion, feedback_hash, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        feedback.feedback_id,
                        feedback.opinion_id,
                        feedback.shadow_outcome_id,
                        feedback.opinion_hash,
                        feedback.observation_id,
                        feedback.observation_hash,
                        known_at_us,
                        linked_at_us,
                        feedback.source_snapshot_id,
                        feedback.adoption.value,
                        feedback.accuracy_basis_points,
                        feedback.calibration_basis_points,
                        feedback.memory_promotion,
                        feedback.feedback_hash,
                        payload,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO shadow_outcome_feedback_events (
                        feedback_id, event_sequence, event_type, payload_hash,
                        occurred_at_us, event_hash
                    ) VALUES (?, 1, ?, ?, ?, ?)
                    """,
                    (
                        feedback.feedback_id,
                        _EVENT_TYPE,
                        feedback.feedback_hash,
                        linked_at_us,
                        event_hash,
                    ),
                )
                return True
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Decision outcome feedback append failed",
                reason_code="decision_outcome_feedback_append_failed",
            ) from exc


@dataclass(frozen=True, slots=True)
class DecisionOutcomeFeedbackShadowEvent:
    """One authenticated event from the outcome feedback namespace."""

    event_id: int
    feedback_id: str
    event_sequence: int
    event_type: str
    payload_hash: str
    occurred_at: datetime
    event_hash: str


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError("evidence_refs must be an array")
    items = tuple(cast(Sequence[object], value))
    if not items or not all(isinstance(item, str) for item in items):
        raise TypeError("evidence_refs must contain strings")
    return cast(tuple[str, ...], items)


def _decode_feedback(payload: bytes) -> DecisionOutcomeFeedback:
    raw = orjson.loads(payload)
    if not isinstance(raw, Mapping):
        raise TypeError("feedback payload must be an object")
    value = cast("Mapping[str, object]", raw)
    if frozenset(value) != frozenset(DecisionOutcomeFeedback.__dataclass_fields__):
        raise ValueError("feedback payload fields are invalid")
    integer_fields = (
        "schema_version",
        "accuracy_basis_points",
        "calibration_basis_points",
    )
    if any(
        isinstance(value[field], bool) or not isinstance(value[field], int)
        for field in integer_fields
    ):
        raise TypeError("feedback integer fields are invalid")
    text_fields = tuple(
        field
        for field in DecisionOutcomeFeedback.__dataclass_fields__
        if field
        not in {
            *integer_fields,
            "outcome_known_at",
            "linked_at",
            "evidence_refs",
        }
    )
    if any(not isinstance(value[field], str) for field in text_fields):
        raise TypeError("feedback text fields are invalid")
    return DecisionOutcomeFeedback(
        schema_version=cast(int, value["schema_version"]),
        feedback_id=cast(str, value["feedback_id"]),
        opinion_id=cast(str, value["opinion_id"]),
        shadow_outcome_id=cast(str, value["shadow_outcome_id"]),
        opinion_hash=cast(str, value["opinion_hash"]),
        observation_id=cast(str, value["observation_id"]),
        observation_hash=cast(str, value["observation_hash"]),
        outcome_known_at=_datetime(value["outcome_known_at"]),
        linked_at=_datetime(value["linked_at"]),
        source_snapshot_id=cast(str, value["source_snapshot_id"]),
        evidence_refs=_text_tuple(value["evidence_refs"]),
        adoption=DecisionOpinionAdoption(cast(str, value["adoption"])),
        accuracy_basis_points=cast(int, value["accuracy_basis_points"]),
        calibration_basis_points=cast(int, value["calibration_basis_points"]),
        memory_promotion=cast(str, value["memory_promotion"]),
        feedback_hash=cast(str, value["feedback_hash"]),
    )


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("feedback datetime is invalid")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DecisionOutcomeFeedbackShadowReader:
    """Read and re-authenticate only outcome feedback records and events."""

    def __init__(self, database: DecisionOpinionShadowDatabase) -> None:
        self._database = database

    def get_feedback(self, feedback_id: str) -> DecisionOutcomeFeedback | None:
        """Return one verified feedback record."""
        try:
            row = (
                self._database.get_connection()
                .execute(
                    """
                SELECT feedback_id, opinion_id, shadow_outcome_id, opinion_hash,
                       observation_id, observation_hash, outcome_known_at_us,
                       linked_at_us, source_snapshot_id, adoption,
                       accuracy_basis_points, calibration_basis_points,
                       memory_promotion, feedback_hash, payload_json
                FROM shadow_outcome_feedback WHERE feedback_id=?
                """,
                    (feedback_id,),
                )
                .fetchone()
            )
            if row is None:
                return None
            payload = row["payload_json"]
            if not isinstance(payload, bytes):
                raise TypeError("feedback payload storage type is invalid")
            feedback = _decode_feedback(payload)
            durable = (
                str(row["feedback_id"]),
                str(row["opinion_id"]),
                str(row["shadow_outcome_id"]),
                str(row["opinion_hash"]),
                str(row["observation_id"]),
                str(row["observation_hash"]),
                int(row["outcome_known_at_us"]),
                int(row["linked_at_us"]),
                str(row["source_snapshot_id"]),
                str(row["adoption"]),
                int(row["accuracy_basis_points"]),
                int(row["calibration_basis_points"]),
                str(row["memory_promotion"]),
                str(row["feedback_hash"]),
            )
            expected = (
                feedback.feedback_id,
                feedback.opinion_id,
                feedback.shadow_outcome_id,
                feedback.opinion_hash,
                feedback.observation_id,
                feedback.observation_hash,
                epoch_us(feedback.outcome_known_at, field="feedback outcome_known_at"),
                epoch_us(feedback.linked_at, field="feedback linked_at"),
                feedback.source_snapshot_id,
                feedback.adoption.value,
                feedback.accuracy_basis_points,
                feedback.calibration_basis_points,
                feedback.memory_promotion,
                feedback.feedback_hash,
            )
            if durable != expected:
                raise ValueError("feedback columns drifted from payload")
            return feedback
        except AgentPersistenceError:
            raise
        except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
            raise _integrity(
                "Decision outcome feedback cannot be authenticated",
                "decision_outcome_feedback_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Decision outcome feedback read failed",
                reason_code="decision_outcome_feedback_read_failed",
            ) from exc

    def list_events(
        self, feedback_id: str
    ) -> tuple[DecisionOutcomeFeedbackShadowEvent, ...]:
        """Return the authenticated append-only event for one feedback record."""
        try:
            rows = (
                self._database.get_connection()
                .execute(
                    """
                SELECT event_id, feedback_id, event_sequence, event_type,
                       payload_hash, occurred_at_us, event_hash
                FROM shadow_outcome_feedback_events
                WHERE feedback_id=? ORDER BY event_sequence
                """,
                    (feedback_id,),
                )
                .fetchall()
            )
            events = tuple(
                DecisionOutcomeFeedbackShadowEvent(
                    event_id=int(row["event_id"]),
                    feedback_id=str(row["feedback_id"]),
                    event_sequence=int(row["event_sequence"]),
                    event_type=str(row["event_type"]),
                    payload_hash=str(row["payload_hash"]),
                    occurred_at=datetime_from_epoch_us(
                        int(row["occurred_at_us"]), field="feedback event occurred_at"
                    ),
                    event_hash=str(row["event_hash"]),
                )
                for row in rows
            )
            for event in events:
                if (
                    event.event_sequence != 1
                    or event.event_type != _EVENT_TYPE
                    or event.event_hash
                    != _event_hash(
                        feedback_id=event.feedback_id,
                        payload_hash=event.payload_hash,
                        occurred_at=event.occurred_at,
                    )
                ):
                    raise ValueError("feedback event is invalid")
            return events
        except AgentPersistenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _integrity(
                "Decision outcome feedback events cannot be authenticated",
                "decision_outcome_feedback_event_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Decision outcome feedback event read failed",
                reason_code="decision_outcome_feedback_event_read_failed",
            ) from exc

    def count_feedback(self) -> int:
        """Return the isolated feedback count for operational verification."""
        try:
            row = (
                self._database.get_connection()
                .execute("SELECT COUNT(*) FROM shadow_outcome_feedback")
                .fetchone()
            )
            return int(row[0])
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Decision outcome feedback count failed",
                reason_code="decision_outcome_feedback_count_failed",
            ) from exc


__all__ = [
    "DecisionOutcomeFeedbackShadowEvent",
    "DecisionOutcomeFeedbackShadowReader",
    "DecisionOutcomeFeedbackShadowWriter",
]
