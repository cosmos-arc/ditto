"""Independent authenticated SQLite store for sanitized Agent projections."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock
from typing import cast

import orjson
from ditto_platform.foundation.db.sqlite_pool import SQLitePool

from ditto_agent._canonical import canonical_bytes
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.presentation import (
    AgentContextPresentation,
    AgentGuardrailPresentation,
    AgentGuardrailStatus,
    AgentPresentationConflict,
    AgentPresentationError,
    AgentRunPresentation,
    AgentRunPresentationUpdate,
    AgentToolPresentation,
    AgentUsagePresentation,
)
from ditto_agent.storage.sqlite import presentation_schema as schema
from ditto_agent.storage.sqlite._codec import epoch_us

_INITIALIZE_LOCK = Lock()


def _error(message: str, reason_code: str) -> AgentPresentationError:
    return AgentPresentationError(message, reason_code=reason_code)


class AgentPresentationDatabase:
    """Own only ``data_root/agent/agent-presentation.sqlite3``."""

    def __init__(self, data_root: Path) -> None:
        if not isinstance(cast(object, data_root), Path):
            raise TypeError("data_root must be pathlib.Path")
        self._path = data_root / "agent" / "agent-presentation.sqlite3"
        self._pool = SQLitePool(str(self._path))
        self._state_lock = Lock()
        self._closed = False

    @property
    def path(self) -> Path:
        """Return the sole database path owned by this wrapper."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the current thread's verified-lifecycle connection."""
        with self._state_lock:
            if self._closed:
                raise _error(
                    "Agent presentation database is closed",
                    "agent_presentation_database_closed",
                )
            connection = self._pool.get_connection()
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run one immediate projection transaction with rollback on failure."""
        connection = self.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def initialize(self) -> None:
        """Create or authenticate exactly the approved presentation schema."""
        with _INITIALIZE_LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = self.connection
            try:
                connection.execute("BEGIN IMMEDIATE")
                markers = (
                    connection.execute("PRAGMA application_id").fetchone()[0],
                    connection.execute("PRAGMA user_version").fetchone()[0],
                )
                rows = schema.schema_rows(connection)
                if markers == (0, 0) and not rows:
                    for statement in schema.schema_body_statements(
                        schema.load_schema_sql()
                    ):
                        connection.execute(statement)
                    connection.execute(f"PRAGMA application_id={schema.APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={schema.USER_VERSION}")
                elif markers != (schema.APPLICATION_ID, schema.USER_VERSION):
                    raise _error(
                        "Agent presentation schema markers are not approved",
                        "agent_presentation_schema_markers_invalid",
                    )
                self._verify_schema(connection)
                connection.commit()
            except AgentPresentationError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                raise _error(
                    "Agent presentation schema initialization failed",
                    "agent_presentation_schema_initialization_failed",
                ) from exc

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        rows = schema.schema_rows(connection)
        markers = (
            connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0],
        )
        if (
            markers != (schema.APPLICATION_ID, schema.USER_VERSION)
            or len(rows) != schema.SCHEMA_ROW_COUNT
            or schema.schema_fingerprint(rows) != schema.SCHEMA_FINGERPRINT
        ):
            raise _error(
                "Agent presentation schema has drifted",
                "agent_presentation_schema_drift",
            )

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> None:
        integrity = tuple(
            row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if integrity != ("ok",) or foreign_key_violations:
            raise _error(
                "Agent presentation database integrity failed",
                "agent_presentation_integrity_failed",
            )

    def backup_to(self, destination: Path) -> Path:
        """Create one verified, non-overwriting online projection backup."""
        if not isinstance(cast(object, destination), Path):
            raise TypeError("destination must be pathlib.Path")
        if destination == self._path:
            raise ValueError("backup destination must differ from the live database")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = self.connection
        self._verify_schema(source)
        self._verify_integrity(source)
        try:
            with sqlite3.connect(destination) as target:
                source.backup(target)
            with sqlite3.connect(destination) as verified:
                self._verify_schema(verified)
                self._verify_integrity(verified)
        except AgentPresentationError:
            destination.unlink(missing_ok=True)
            raise
        except sqlite3.Error as exc:
            destination.unlink(missing_ok=True)
            raise _error(
                "Agent presentation database backup failed",
                "agent_presentation_backup_failed",
            ) from exc
        return destination

    def close(self) -> None:
        """Permanently close every owned presentation connection."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._pool.close_all()

    def close_all(self) -> None:
        """Match the lifecycle convention of other Agent database wrappers."""
        self.close()


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise TypeError(f"{field} keys must be strings")
    return cast("Mapping[str, object]", raw)


def _exact(
    value: object, *, field: str, fields: frozenset[str]
) -> Mapping[str, object]:
    mapping = _mapping(value, field=field)
    if frozenset(mapping) != fields:
        raise ValueError(f"{field} fields are invalid")
    return mapping


def _string(value: object, *, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be text")
    return value


def _optional_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field=field)


def _integer(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    return value


def _text_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field} must be an array")
    items = tuple(cast("Sequence[object]", value))
    if not all(type(item) is str for item in items):
        raise TypeError(f"{field} must contain text")
    return cast(tuple[str, ...], items)


def _decode_context(value: object) -> AgentContextPresentation | None:
    if value is None:
        return None
    fields = frozenset({"context_type", "context_id"})
    raw = _exact(value, field="context", fields=fields)
    return AgentContextPresentation(
        context_type=_string(raw["context_type"], field="context_type"),
        context_id=_string(raw["context_id"], field="context_id"),
    )


def _decode_tool(value: object) -> AgentToolPresentation:
    fields = frozenset(
        {
            "call_id",
            "tool_name",
            "arguments_hash",
            "result_hash",
            "evidence_refs",
            "artifact_refs",
        }
    )
    raw = _exact(value, field="tool_record", fields=fields)
    return AgentToolPresentation(
        call_id=_string(raw["call_id"], field="call_id"),
        tool_name=_string(raw["tool_name"], field="tool_name"),
        arguments_hash=_string(raw["arguments_hash"], field="arguments_hash"),
        result_hash=_string(raw["result_hash"], field="result_hash"),
        evidence_refs=_text_tuple(raw["evidence_refs"], field="evidence_refs"),
        artifact_refs=_text_tuple(raw["artifact_refs"], field="artifact_refs"),
    )


def _decode_tools(value: object) -> tuple[AgentToolPresentation, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError("tool_records must be an array")
    return tuple(_decode_tool(item) for item in cast("Sequence[object]", value))


def _decode_guardrail(value: object) -> AgentGuardrailPresentation:
    raw = _exact(
        value,
        field="guardrail",
        fields=frozenset({"status", "reason_code"}),
    )
    status = _string(raw["status"], field="guardrail status")
    if status not in {"passed", "blocked", "unknown"}:
        raise ValueError("guardrail status is invalid")
    return AgentGuardrailPresentation(
        status=cast(AgentGuardrailStatus, status),
        reason_code=_optional_string(raw["reason_code"], field="guardrail reason_code"),
    )


def _decode_usage(value: object) -> AgentUsagePresentation | None:
    if value is None:
        return None
    fields = frozenset(
        {
            "model_attempts",
            "model_turns",
            "tool_calls",
            "retries",
            "total_tokens",
            "model_spend_usd",
            "exhausted_reason",
        }
    )
    raw = _exact(value, field="usage", fields=fields)
    spend = _string(raw["model_spend_usd"], field="model_spend_usd")
    try:
        spend_decimal = Decimal(spend)
    except InvalidOperation as exc:
        raise ValueError("model_spend_usd is invalid") from exc
    return AgentUsagePresentation(
        model_attempts=_integer(raw["model_attempts"], field="model_attempts"),
        model_turns=_integer(raw["model_turns"], field="model_turns"),
        tool_calls=_integer(raw["tool_calls"], field="tool_calls"),
        retries=_integer(raw["retries"], field="retries"),
        total_tokens=_integer(raw["total_tokens"], field="total_tokens"),
        model_spend_usd=spend_decimal,
        exhausted_reason=_optional_string(
            raw["exhausted_reason"], field="exhausted_reason"
        ),
    )


def _decode_projection(payload: bytes) -> AgentRunPresentation:
    raw = _exact(
        orjson.loads(payload),
        field="presentation",
        fields=frozenset(AgentRunPresentation.__dataclass_fields__),
    )
    status = RunStatus(_string(raw["status"], field="status"))
    updated_at_raw = _string(raw["updated_at"], field="updated_at")
    updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
    projection = AgentRunPresentation(
        run_id=_string(raw["run_id"], field="run_id"),
        objective=_string(raw["objective"], field="objective"),
        context=_decode_context(raw["context"]),
        status=status,
        output_summary=_optional_string(raw["output_summary"], field="output_summary"),
        tool_records=_decode_tools(raw["tool_records"]),
        evidence_refs=_text_tuple(raw["evidence_refs"], field="evidence_refs"),
        artifact_refs=_text_tuple(raw["artifact_refs"], field="artifact_refs"),
        guardrail=_decode_guardrail(raw["guardrail"]),
        usage=_decode_usage(raw["usage"]),
        failure_code=_optional_string(raw["failure_code"], field="failure_code"),
        projection_version=_integer(
            raw["projection_version"], field="projection_version"
        ),
        updated_at=updated_at,
        event_cursor=_integer(raw["event_cursor"], field="event_cursor"),
    )
    if canonical_bytes(projection) != payload:
        raise ValueError("presentation payload is not canonical")
    return projection


class AgentPresentationWriter:
    """Persist monotonic derived projections without touching audit state."""

    def __init__(self, database: AgentPresentationDatabase) -> None:
        self._database = database

    def put(self, projection: AgentRunPresentation) -> bool:
        """Insert or advance a projection; return False for an exact replay."""
        if not isinstance(cast(object, projection), AgentRunPresentation):
            raise TypeError("projection must be an AgentRunPresentation")
        payload = canonical_bytes(projection)
        payload_hash = hashlib.sha256(payload).hexdigest()
        try:
            with self._database.transaction() as connection:
                existing = connection.execute(
                    """
                    SELECT projection_version, payload_hash, payload_json
                    FROM agent_run_presentation
                    WHERE run_id=?
                    """,
                    (projection.run_id,),
                ).fetchone()
                if existing is not None:
                    durable = (
                        int(existing["projection_version"]),
                        str(existing["payload_hash"]),
                        existing["payload_json"],
                    )
                    expected = (
                        projection.projection_version,
                        payload_hash,
                        payload,
                    )
                    if durable == expected:
                        return False
                    if projection.projection_version <= durable[0]:
                        raise AgentPresentationConflict(
                            "Agent presentation version conflicts with durable state",
                            reason_code="agent_presentation_version_conflict",
                        )
                    connection.execute(
                        """
                        UPDATE agent_run_presentation
                        SET projection_version=?, updated_at_us=?, status=?,
                            payload_hash=?, payload_json=?
                        WHERE run_id=?
                        """,
                        (
                            projection.projection_version,
                            epoch_us(projection.updated_at, field="updated_at"),
                            projection.status.value,
                            payload_hash,
                            payload,
                            projection.run_id,
                        ),
                    )
                    return True
                connection.execute(
                    """
                    INSERT INTO agent_run_presentation (
                        run_id, projection_version, updated_at_us, status,
                        payload_hash, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        projection.run_id,
                        projection.projection_version,
                        epoch_us(projection.updated_at, field="updated_at"),
                        projection.status.value,
                        payload_hash,
                        payload,
                    ),
                )
                return True
        except AgentPresentationError:
            raise
        except sqlite3.Error as exc:
            raise _error(
                "Agent presentation write failed",
                "agent_presentation_write_failed",
            ) from exc


class AgentPresentationReader:
    """Read and re-authenticate sanitized run projections."""

    def __init__(self, database: AgentPresentationDatabase) -> None:
        self._database = database

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> AgentRunPresentation:
        payload = row["payload_json"]
        payload_hash = row["payload_hash"]
        if not isinstance(payload, bytes) or not isinstance(payload_hash, str):
            raise TypeError("presentation storage types are invalid")
        if hashlib.sha256(payload).hexdigest() != payload_hash:
            raise ValueError("presentation payload hash is invalid")
        projection = _decode_projection(payload)
        durable = (
            str(row["run_id"]),
            int(row["projection_version"]),
            int(row["updated_at_us"]),
            str(row["status"]),
        )
        expected = (
            projection.run_id,
            projection.projection_version,
            epoch_us(projection.updated_at, field="updated_at"),
            projection.status.value,
        )
        if durable != expected:
            raise ValueError("presentation columns drifted from payload")
        return projection

    def get(self, run_id: str) -> AgentRunPresentation | None:
        """Return one verified projection, or None when it was never materialized."""
        normalized = normalized_text(run_id, field="run_id")
        try:
            row = self._database.connection.execute(
                """
                SELECT run_id, projection_version, updated_at_us, status,
                       payload_hash, payload_json
                FROM agent_run_presentation
                WHERE run_id=?
                """,
                (normalized,),
            ).fetchone()
            return None if row is None else self._decode_row(row)
        except AgentPresentationError:
            raise
        except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
            raise _error(
                "Agent presentation payload cannot be authenticated",
                "agent_presentation_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise _error(
                "Agent presentation read failed",
                "agent_presentation_read_failed",
            ) from exc

    def list(self) -> tuple[AgentRunPresentation, ...]:
        """Return every verified projection newest first."""
        try:
            rows = self._database.connection.execute(
                """
                SELECT run_id, projection_version, updated_at_us, status,
                       payload_hash, payload_json
                FROM agent_run_presentation
                ORDER BY updated_at_us DESC, run_id DESC
                """
            ).fetchall()
            return tuple(self._decode_row(row) for row in rows)
        except AgentPresentationError:
            raise
        except (orjson.JSONDecodeError, TypeError, ValueError) as exc:
            raise _error(
                "Agent presentation payload cannot be authenticated",
                "agent_presentation_payload_invalid",
            ) from exc
        except sqlite3.Error as exc:
            raise _error(
                "Agent presentation read failed",
                "agent_presentation_read_failed",
            ) from exc


class AgentPresentationProjector:
    """Merge outcome-derived content into the monotonic persisted projection."""

    def __init__(
        self,
        *,
        reader: AgentPresentationReader,
        writer: AgentPresentationWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def publish(self, update: AgentRunPresentationUpdate) -> None:
        """Preserve host context/cursor while advancing readable outcome content."""
        existing = self._reader.get(update.run_id)
        if existing is not None and existing.objective != update.objective:
            raise AgentPresentationConflict(
                "Agent presentation objective conflicts with durable state",
                reason_code="agent_presentation_objective_conflict",
            )
        if existing is None:
            projection = AgentRunPresentation(
                run_id=update.run_id,
                objective=update.objective,
                context=update.context,
                status=update.status,
                output_summary=update.output_summary,
                tool_records=update.tool_records,
                evidence_refs=update.evidence_refs,
                artifact_refs=update.artifact_refs,
                guardrail=update.guardrail,
                usage=update.usage,
                failure_code=update.failure_code,
                projection_version=1,
                updated_at=update.updated_at,
            )
        else:
            projection = replace(
                existing,
                context=update.context or existing.context,
                status=update.status,
                output_summary=update.output_summary,
                tool_records=update.tool_records,
                evidence_refs=update.evidence_refs,
                artifact_refs=update.artifact_refs,
                guardrail=update.guardrail,
                usage=update.usage,
                failure_code=update.failure_code,
                projection_version=existing.projection_version + 1,
                updated_at=update.updated_at,
            )
        self._writer.put(projection)


__all__ = [
    "AgentPresentationDatabase",
    "AgentPresentationProjector",
    "AgentPresentationReader",
    "AgentPresentationWriter",
]
