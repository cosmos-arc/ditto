"""Independent immutable SQLite store for shadow DecisionOpinion records."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import cast

import orjson
from ditto_application.processes.risk.agent_decision_briefing import (
    DecisionOpinionRecord,
)
from ditto_platform.foundation.db.sqlite_pool import SQLitePool

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.storage.sqlite import decision_opinion_schema as schema
from ditto_agent.storage.sqlite._codec import datetime_from_epoch_us, epoch_us
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentDatabaseClosedError,
    AgentIntegrityError,
    AgentPersistenceError,
    AgentSchemaError,
)

__all__ = [
    "DecisionOpinionShadowDatabase",
    "DecisionOpinionShadowEvent",
    "DecisionOpinionShadowReader",
    "DecisionOpinionShadowWriter",
]

_INITIALIZE_LOCK = Lock()
_EVENT_TYPE = "shadow_decision_opinion_persisted"
_SHA256_LENGTH = 64


def _schema_error(
    message: str, reason_code: str, **details: object
) -> AgentSchemaError:
    return AgentSchemaError(message, reason_code=reason_code, details=details)


def _integrity(message: str, reason_code: str) -> AgentIntegrityError:
    return AgentIntegrityError(message, reason_code=reason_code)


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_canonical_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


class DecisionOpinionShadowDatabase:
    """Own only ``data_root/agent-shadow/decision-opinion.sqlite``."""

    def __init__(self, data_root: Path) -> None:
        if not isinstance(cast(object, data_root), Path):
            raise TypeError("data_root must be pathlib.Path")
        self._path = data_root / "agent-shadow" / "decision-opinion.sqlite"
        self._pool = SQLitePool(str(self._path))
        self._state_lock = Lock()
        self._closed = False

    @property
    def path(self) -> Path:
        """Return the only database path this wrapper may open."""
        return self._path

    def get_connection(self) -> sqlite3.Connection:
        """Return a thread-local connection with required integrity pragmas."""
        with self._state_lock:
            if self._closed:
                raise AgentDatabaseClosedError(
                    "DecisionOpinion shadow database is closed",
                    reason_code="decision_opinion_database_closed",
                )
            connection = self._pool.get_connection()
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA recursive_triggers=ON")
        pragmas = (
            connection.execute("PRAGMA foreign_keys").fetchone()[0],
            connection.execute("PRAGMA recursive_triggers").fetchone()[0],
        )
        if pragmas != (1, 1):
            raise _schema_error(
                "DecisionOpinion integrity pragmas could not be enabled",
                "decision_opinion_database_pragma_disabled",
            )
        return connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run one immediate shadow-only transaction."""
        connection = self.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def initialize(self) -> None:
        """Create or authenticate the isolated shadow schema and migrations."""
        with _INITIALIZE_LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = self.get_connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                markers = (
                    connection.execute("PRAGMA application_id").fetchone()[0],
                    connection.execute("PRAGMA user_version").fetchone()[0],
                )
                rows = schema.schema_rows(connection)
                if markers == (0, 0) and not rows:
                    for statement in schema.fresh_schema_body_statements():
                        connection.execute(statement)
                    connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={schema.USER_VERSION}")
                    current_version = schema.USER_VERSION
                elif (
                    markers[0] != schema.APPLICATION_ID
                    or markers[1] < 1
                    or markers[1] > schema.USER_VERSION
                ):
                    raise _schema_error(
                        "DecisionOpinion database markers are not approved",
                        "decision_opinion_schema_marker_invalid",
                        application_id=markers[0],
                        user_version=markers[1],
                    )
                else:
                    current_version = int(markers[1])
                self._verify_schema_version(connection, current_version)
                for target_version in range(
                    current_version + 1, schema.USER_VERSION + 1
                ):
                    for statement in schema.schema_body_statements(
                        schema.load_schema_sql(version=target_version),
                        version=target_version,
                    ):
                        connection.execute(statement)
                    connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={target_version}")
                    self._verify_schema_version(connection, target_version)
                self._verify_current_schema(connection)
                connection.commit()
            except AgentSchemaError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                raise _schema_error(
                    "DecisionOpinion schema initialization failed",
                    "decision_opinion_schema_initialization_failed",
                    sqlite_error=type(exc).__name__,
                ) from exc

    @staticmethod
    def _verify_schema_version(connection: sqlite3.Connection, version: int) -> None:
        rows = schema.schema_rows(connection)
        fingerprint = schema.schema_fingerprint(rows)
        expected_count, expected_fingerprint = schema.expected_schema(version)
        markers = (
            connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0],
        )
        if (
            markers != (schema.APPLICATION_ID, version)
            or len(rows) != expected_count
            or fingerprint != expected_fingerprint
        ):
            raise _schema_error(
                "DecisionOpinion schema has drifted",
                "decision_opinion_schema_drift",
                expected_fingerprint=expected_fingerprint,
                actual_fingerprint=fingerprint,
                version=version,
            )

    @staticmethod
    def _verify_current_schema(connection: sqlite3.Connection) -> None:
        DecisionOpinionShadowDatabase._verify_schema_version(
            connection, schema.USER_VERSION
        )

    def catalog_names(self) -> tuple[str, ...]:
        """Expose only authenticated object names for isolation evidence."""
        connection = self.get_connection()
        self._verify_current_schema(connection)
        return tuple(sorted(str(row[1]) for row in schema.schema_rows(connection)))

    def close_all(self) -> None:
        """Permanently close all owned shadow connections."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._pool.close_all()


@dataclass(frozen=True, slots=True)
class DecisionOpinionShadowEvent:
    """One append-only event from the independent shadow namespace."""

    event_id: int
    opinion_id: str
    event_sequence: int
    event_type: str
    payload_hash: str
    occurred_at: datetime
    event_hash: str


def _identity_payload(record: DecisionOpinionRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "status": record.status,
        "v3_artifact_id": record.v3_artifact_id,
        "v3_evidence_hash": record.v3_evidence_hash,
        "v3_readiness": record.v3_readiness,
        "summary": record.summary,
        "dissent": record.dissent,
        "uncertainty": record.uncertainty,
        "evidence_refs": record.evidence_refs,
        "blocking_reasons": record.blocking_reasons,
        "reason_code": record.reason_code,
        "model_profile": record.model_profile,
        "prompt_hash": record.prompt_hash,
        "provider_id": record.provider_id,
        "generated_at": record.generated_at,
    }


def _record_payload(record: DecisionOpinionRecord) -> dict[str, object]:
    return {
        field_name: getattr(record, field_name)
        for field_name in DecisionOpinionRecord.__dataclass_fields__
    }


def _validate_record(record: DecisionOpinionRecord) -> None:
    text_fields: tuple[object, ...] = (
        record.opinion_id,
        record.shadow_outcome_id,
        record.v3_artifact_id,
        record.summary,
        record.uncertainty,
        record.model_profile,
        record.provider_id,
    )
    if record.schema_version != 1 or not all(
        _is_canonical_text(value) for value in text_fields
    ):
        raise _integrity(
            "DecisionOpinion record has invalid required fields",
            "decision_opinion_record_invalid",
        )
    if not all(
        _is_hash(value)
        for value in (
            record.v3_evidence_hash,
            record.prompt_hash,
            record.opinion_hash,
        )
    ):
        raise _integrity(
            "DecisionOpinion record has invalid hashes",
            "decision_opinion_record_hash_invalid",
        )
    if (
        record.opinion_id != f"decision-opinion-{record.opinion_hash}"
        or record.shadow_outcome_id != f"decision-shadow-{record.opinion_hash}"
        or canonical_sha256(_identity_payload(record)) != record.opinion_hash
    ):
        raise _integrity(
            "DecisionOpinion content identity is invalid",
            "decision_opinion_record_identity_invalid",
        )
    if (
        record.generated_at.tzinfo is None
        or record.generated_at.utcoffset() != timedelta(0)
        or record.generated_at != record.generated_at.astimezone(UTC)
    ):
        raise _integrity(
            "DecisionOpinion generated_at is not UTC",
            "decision_opinion_record_time_invalid",
        )
    if record.evidence_refs != (record.v3_artifact_id,):
        raise _integrity(
            "DecisionOpinion references are outside its exact V3 artifact",
            "decision_opinion_record_evidence_invalid",
        )
    blocked = record.v3_readiness == "blocked"
    if blocked != (record.status == "blocked") or blocked != bool(
        record.blocking_reasons
    ):
        raise _integrity(
            "DecisionOpinion blocking state is inconsistent",
            "decision_opinion_record_status_invalid",
        )
    expected_reason = "daily_decision_v3_blocked" if blocked else None
    if record.reason_code != expected_reason:
        raise _integrity(
            "DecisionOpinion reason code is inconsistent",
            "decision_opinion_record_status_invalid",
        )


def _event_hash(*, opinion_id: str, payload_hash: str, occurred_at: datetime) -> str:
    return canonical_sha256(
        {
            "event_sequence": 1,
            "event_type": _EVENT_TYPE,
            "opinion_id": opinion_id,
            "payload_hash": payload_hash,
            "occurred_at": occurred_at,
        }
    )


class DecisionOpinionShadowWriter:
    """Append exact opinions and their event atomically in shadow state only."""

    def __init__(self, database: DecisionOpinionShadowDatabase) -> None:
        self._database = database

    def append_opinion(self, record: DecisionOpinionRecord) -> bool:
        """Append once; return False only for an exact immutable replay."""
        if not isinstance(cast(object, record), DecisionOpinionRecord):
            raise TypeError("record must be a DecisionOpinionRecord")
        _validate_record(record)
        payload = canonical_bytes(_record_payload(record))
        occurred_at_us = epoch_us(record.generated_at, field="opinion generated_at")
        event_hash = _event_hash(
            opinion_id=record.opinion_id,
            payload_hash=record.opinion_hash,
            occurred_at=record.generated_at,
        )
        try:
            with self._database.transaction() as connection:
                existing = connection.execute(
                    """
                    SELECT opinion_id, shadow_outcome_id, opinion_hash, payload_json
                    FROM shadow_decision_opinions
                    WHERE opinion_id=? OR shadow_outcome_id=? OR opinion_hash=?
                    """,
                    (
                        record.opinion_id,
                        record.shadow_outcome_id,
                        record.opinion_hash,
                    ),
                ).fetchone()
                if existing is not None:
                    durable = (
                        str(existing["opinion_id"]),
                        str(existing["shadow_outcome_id"]),
                        str(existing["opinion_hash"]),
                        existing["payload_json"],
                    )
                    expected = (
                        record.opinion_id,
                        record.shadow_outcome_id,
                        record.opinion_hash,
                        payload,
                    )
                    if durable != expected:
                        raise _conflict(
                            "DecisionOpinion replay conflicts with shadow state",
                            "decision_opinion_replay_conflict",
                        )
                    return False
                connection.execute(
                    """
                    INSERT INTO shadow_decision_opinions (
                        opinion_id, shadow_outcome_id, status, v3_artifact_id,
                        v3_evidence_hash, v3_readiness, opinion_hash,
                        generated_at_us, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.opinion_id,
                        record.shadow_outcome_id,
                        record.status,
                        record.v3_artifact_id,
                        record.v3_evidence_hash,
                        record.v3_readiness,
                        record.opinion_hash,
                        occurred_at_us,
                        payload,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO shadow_decision_events (
                        opinion_id, event_sequence, event_type, payload_hash,
                        occurred_at_us, event_hash
                    ) VALUES (?, 1, ?, ?, ?, ?)
                    """,
                    (
                        record.opinion_id,
                        _EVENT_TYPE,
                        record.opinion_hash,
                        occurred_at_us,
                        event_hash,
                    ),
                )
                return True
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "DecisionOpinion shadow append failed",
                reason_code="decision_opinion_append_failed",
            ) from exc


def _text_tuple(value: object, *, field: str, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{field} must be an array")
    items = tuple(cast(Sequence[object], value))
    if (not allow_empty and not items) or not all(
        isinstance(item, str) for item in items
    ):
        raise ValueError(f"{field} must contain strings")
    return cast(tuple[str, ...], items)


def _decode_record(payload: bytes) -> DecisionOpinionRecord:
    raw = orjson.loads(payload)
    if not isinstance(raw, Mapping):
        raise TypeError("DecisionOpinion payload must be an object")
    value = cast("Mapping[str, object]", raw)
    expected = frozenset(DecisionOpinionRecord.__dataclass_fields__)
    if frozenset(value) != expected:
        raise ValueError("DecisionOpinion payload fields are invalid")
    required_text = tuple(
        field_name
        for field_name in expected
        if field_name
        not in {
            "schema_version",
            "dissent",
            "evidence_refs",
            "blocking_reasons",
            "reason_code",
            "generated_at",
        }
    )
    if any(not isinstance(value[field], str) for field in required_text):
        raise TypeError("DecisionOpinion payload text fields are invalid")
    dissent = value["dissent"]
    reason_code = value["reason_code"]
    if dissent is not None and not isinstance(dissent, str):
        raise TypeError("DecisionOpinion dissent is invalid")
    if reason_code is not None and not isinstance(reason_code, str):
        raise TypeError("DecisionOpinion reason_code is invalid")
    schema_version = value["schema_version"]
    generated_at_raw = value["generated_at"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise TypeError("DecisionOpinion schema_version is invalid")
    if not isinstance(generated_at_raw, str):
        raise TypeError("DecisionOpinion generated_at is invalid")
    generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
    return DecisionOpinionRecord(
        schema_version=schema_version,
        opinion_id=cast(str, value["opinion_id"]),
        shadow_outcome_id=cast(str, value["shadow_outcome_id"]),
        status=cast(str, value["status"]),
        v3_artifact_id=cast(str, value["v3_artifact_id"]),
        v3_evidence_hash=cast(str, value["v3_evidence_hash"]),
        v3_readiness=cast(str, value["v3_readiness"]),
        summary=cast(str, value["summary"]),
        dissent=dissent,
        uncertainty=cast(str, value["uncertainty"]),
        evidence_refs=_text_tuple(
            value["evidence_refs"], field="evidence_refs", allow_empty=False
        ),
        blocking_reasons=_text_tuple(
            value["blocking_reasons"], field="blocking_reasons", allow_empty=True
        ),
        reason_code=reason_code,
        model_profile=cast(str, value["model_profile"]),
        prompt_hash=cast(str, value["prompt_hash"]),
        provider_id=cast(str, value["provider_id"]),
        generated_at=generated_at,
        opinion_hash=cast(str, value["opinion_hash"]),
    )


def _record_from_row(row: sqlite3.Row) -> DecisionOpinionRecord:
    payload = row["payload_json"]
    if not isinstance(payload, bytes):
        raise TypeError("DecisionOpinion payload storage type is invalid")
    record = _decode_record(payload)
    _validate_record(record)
    durable = (
        str(row["opinion_id"]),
        str(row["shadow_outcome_id"]),
        str(row["status"]),
        str(row["v3_artifact_id"]),
        str(row["v3_evidence_hash"]),
        str(row["v3_readiness"]),
        str(row["opinion_hash"]),
        int(row["generated_at_us"]),
    )
    expected = (
        record.opinion_id,
        record.shadow_outcome_id,
        record.status,
        record.v3_artifact_id,
        record.v3_evidence_hash,
        record.v3_readiness,
        record.opinion_hash,
        epoch_us(record.generated_at, field="opinion generated_at"),
    )
    if durable != expected:
        raise ValueError("DecisionOpinion columns drifted from payload")
    return record


class DecisionOpinionShadowReader:
    """Read and re-authenticate only independent shadow records and events."""

    def __init__(self, database: DecisionOpinionShadowDatabase) -> None:
        self._database = database

    def get_opinion(self, opinion_id: str) -> DecisionOpinionRecord | None:
        """Return one verified opinion without exposing core database access."""
        try:
            row = (
                self._database.get_connection()
                .execute(
                    """
                SELECT opinion_id, shadow_outcome_id, status, v3_artifact_id,
                       v3_evidence_hash, v3_readiness, opinion_hash,
                       generated_at_us, payload_json
                FROM shadow_decision_opinions
                WHERE opinion_id=?
                """,
                    (opinion_id,),
                )
                .fetchone()
            )
            if row is None:
                return None
            return _record_from_row(row)
        except AgentPersistenceError:
            raise
        except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
            raise _integrity(
                "DecisionOpinion shadow payload cannot be authenticated",
                "decision_opinion_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "DecisionOpinion shadow read failed",
                reason_code="decision_opinion_read_failed",
            ) from exc

    def get_latest_by_v3_artifact_id(
        self, v3_artifact_id: str
    ) -> DecisionOpinionRecord | None:
        """Return the newest authenticated opinion for one exact V3 artifact."""
        if not _is_canonical_text(v3_artifact_id):
            raise ValueError("v3_artifact_id must be non-empty canonical text")
        try:
            row = (
                self._database.get_connection()
                .execute(
                    """
                SELECT opinion_id, shadow_outcome_id, status, v3_artifact_id,
                       v3_evidence_hash, v3_readiness, opinion_hash,
                       generated_at_us, payload_json
                FROM shadow_decision_opinions
                WHERE v3_artifact_id=?
                ORDER BY generated_at_us DESC, opinion_id DESC
                LIMIT 1
                """,
                    (v3_artifact_id,),
                )
                .fetchone()
            )
            if row is None:
                return None
            return _record_from_row(row)
        except AgentPersistenceError:
            raise
        except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
            raise _integrity(
                "DecisionOpinion shadow payload cannot be authenticated",
                "decision_opinion_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "DecisionOpinion shadow read failed",
                reason_code="decision_opinion_read_failed",
            ) from exc

    def list_events(self, opinion_id: str) -> tuple[DecisionOpinionShadowEvent, ...]:
        """Return the authenticated append-only event for one opinion."""
        try:
            rows = (
                self._database.get_connection()
                .execute(
                    """
                SELECT event_id, opinion_id, event_sequence, event_type,
                       payload_hash, occurred_at_us, event_hash
                FROM shadow_decision_events
                WHERE opinion_id=?
                ORDER BY event_sequence
                """,
                    (opinion_id,),
                )
                .fetchall()
            )
            events = tuple(
                DecisionOpinionShadowEvent(
                    event_id=int(row["event_id"]),
                    opinion_id=str(row["opinion_id"]),
                    event_sequence=int(row["event_sequence"]),
                    event_type=str(row["event_type"]),
                    payload_hash=str(row["payload_hash"]),
                    occurred_at=datetime_from_epoch_us(
                        int(row["occurred_at_us"]), field="shadow event occurred_at"
                    ),
                    event_hash=str(row["event_hash"]),
                )
                for row in rows
            )
            for event in events:
                if (
                    event.event_sequence != 1
                    or event.event_type != _EVENT_TYPE
                    or not _is_hash(event.payload_hash)
                    or event.event_hash
                    != _event_hash(
                        opinion_id=event.opinion_id,
                        payload_hash=event.payload_hash,
                        occurred_at=event.occurred_at,
                    )
                ):
                    raise ValueError("DecisionOpinion shadow event is invalid")
            return events
        except AgentPersistenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _integrity(
                "DecisionOpinion shadow events cannot be authenticated",
                "decision_opinion_event_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "DecisionOpinion shadow event read failed",
                reason_code="decision_opinion_event_read_failed",
            ) from exc

    def count_opinions(self) -> int:
        """Return the isolated opinion count for operational verification."""
        try:
            row = (
                self._database.get_connection()
                .execute("SELECT COUNT(*) FROM shadow_decision_opinions")
                .fetchone()
            )
            return int(row[0])
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "DecisionOpinion shadow count failed",
                reason_code="decision_opinion_count_failed",
            ) from exc
