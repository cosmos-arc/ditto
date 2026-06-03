"""SQLite readers and writers for normalized broker gateway events."""

from __future__ import annotations

from typing import Any, cast

import orjson
from ditto_platform.foundation import SQLiteClient

from ditto_execution.models import BrokerEventRecord

__all__ = [
    "BROKER_EVENTS_DDL",
    "BrokerEventReader",
    "BrokerEventWriter",
]

_CREATE_BROKER_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS broker_events (
    event_id        TEXT PRIMARY KEY,
    run_id          TEXT    NOT NULL,
    broker          TEXT    NOT NULL,
    event_type      TEXT    NOT NULL,
    event_time      TEXT    NOT NULL,
    order_id        TEXT    NULL,
    broker_order_id TEXT    NULL,
    fill_id         TEXT    NULL,
    instrument_id   INTEGER NULL,
    status          TEXT    NULL,
    correlation_id  TEXT    NULL,
    payload         TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_IDX_BROKER_EVENTS_RUN_TIME = (
    "CREATE INDEX IF NOT EXISTS idx_broker_events_run_time "
    "ON broker_events(run_id, event_time);"
)

_CREATE_IDX_BROKER_EVENTS_RUN_ORDER = (
    "CREATE INDEX IF NOT EXISTS idx_broker_events_run_order "
    "ON broker_events(run_id, order_id);"
)

_CREATE_IDX_BROKER_EVENTS_RUN_BROKER_ORDER = (
    "CREATE INDEX IF NOT EXISTS idx_broker_events_run_broker_order "
    "ON broker_events(run_id, broker_order_id);"
)

_CREATE_IDX_BROKER_EVENTS_RUN_FILL = (
    "CREATE INDEX IF NOT EXISTS idx_broker_events_run_fill "
    "ON broker_events(run_id, fill_id);"
)

_INSERT_BROKER_EVENT = """
INSERT OR IGNORE INTO broker_events
    (event_id, run_id, broker, event_type, event_time, order_id,
     broker_order_id, fill_id, instrument_id, status, correlation_id,
     payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_BACKFILL_BROKER_EVENT_LINKS = """
UPDATE broker_events
SET
    order_id = CASE
        WHEN (order_id IS NULL OR trim(order_id) = '')
             AND ? IS NOT NULL
             AND trim(?) <> ''
        THEN ?
        ELSE order_id
    END,
    broker_order_id = CASE
        WHEN (broker_order_id IS NULL OR trim(broker_order_id) = '')
             AND ? IS NOT NULL
             AND trim(?) <> ''
        THEN ?
        ELSE broker_order_id
    END,
    fill_id = CASE
        WHEN (fill_id IS NULL OR trim(fill_id) = '')
             AND ? IS NOT NULL
             AND trim(?) <> ''
        THEN ?
        ELSE fill_id
    END,
    instrument_id = COALESCE(instrument_id, ?),
    correlation_id = CASE
        WHEN (correlation_id IS NULL OR trim(correlation_id) = '')
             AND ? IS NOT NULL
             AND trim(?) <> ''
        THEN ?
        ELSE correlation_id
    END
WHERE event_id = ?
"""

_GET_BROKER_EVENT = "SELECT * FROM broker_events WHERE event_id = ?"

_LIST_BROKER_EVENTS = """
SELECT * FROM broker_events
WHERE run_id = ?
  AND (? IS NULL OR event_type = ?)
  AND (? IS NULL OR order_id = ?)
  AND (? IS NULL OR broker_order_id = ?)
  AND (? IS NULL OR fill_id = ?)
  AND (? IS NULL OR substr(event_time, 1, 10) >= ?)
  AND (? IS NULL OR substr(event_time, 1, 10) <= ?)
ORDER BY event_time ASC, rowid ASC
"""

BROKER_EVENTS_DDL = (
    _CREATE_BROKER_EVENTS_TABLE
    + _CREATE_IDX_BROKER_EVENTS_RUN_TIME
    + _CREATE_IDX_BROKER_EVENTS_RUN_ORDER
    + _CREATE_IDX_BROKER_EVENTS_RUN_BROKER_ORDER
    + _CREATE_IDX_BROKER_EVENTS_RUN_FILL
)


class BrokerEventReader:
    """Read normalized broker gateway events from ``broker_events``."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def get(self, event_id: str) -> BrokerEventRecord | None:
        """Return one broker event by event_id."""
        row = self._client.fetchone(_GET_BROKER_EVENT, (event_id,))
        return self._row_to_broker_event(row) if row else None

    def list(
        self,
        run_id: str,
        *,
        event_type: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        fill_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[BrokerEventRecord]:
        """Return broker events matching run, link-key and date filters."""
        rows = self._client.fetchall(
            _LIST_BROKER_EVENTS,
            (
                run_id,
                event_type,
                event_type,
                order_id,
                order_id,
                broker_order_id,
                broker_order_id,
                fill_id,
                fill_id,
                start_date,
                start_date,
                end_date,
                end_date,
            ),
        )
        return [self._row_to_broker_event(row) for row in rows]

    @staticmethod
    def _row_to_broker_event(row: dict[str, Any]) -> BrokerEventRecord:
        payload = cast(dict[str, object], orjson.loads(row["payload"]))
        return BrokerEventRecord(
            event_id=str(row["event_id"]),
            run_id=str(row["run_id"]),
            broker=str(row["broker"]),
            event_type=str(row["event_type"]),
            event_time=str(row["event_time"]),
            order_id=cast(str | None, row["order_id"]),
            broker_order_id=cast(str | None, row["broker_order_id"]),
            fill_id=cast(str | None, row["fill_id"]),
            instrument_id=cast(int | None, row["instrument_id"]),
            status=cast(str | None, row["status"]),
            correlation_id=cast(str | None, row["correlation_id"]),
            payload=payload,
            created_at=str(row["created_at"]),
        )


class BrokerEventWriter:
    """Write normalized broker events to ``broker_events``."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def save(self, record: BrokerEventRecord) -> None:
        """Persist one normalized broker event."""
        self._client.execute(
            _INSERT_BROKER_EVENT,
            (
                record.event_id,
                record.run_id,
                record.broker,
                record.event_type,
                record.event_time,
                record.order_id,
                record.broker_order_id,
                record.fill_id,
                record.instrument_id,
                record.status,
                record.correlation_id,
                orjson.dumps(record.payload).decode("utf-8"),
                record.created_at,
            ),
        )
        self._client.execute(
            _BACKFILL_BROKER_EVENT_LINKS,
            (
                record.order_id,
                record.order_id,
                record.order_id,
                record.broker_order_id,
                record.broker_order_id,
                record.broker_order_id,
                record.fill_id,
                record.fill_id,
                record.fill_id,
                record.instrument_id,
                record.correlation_id,
                record.correlation_id,
                record.correlation_id,
                record.event_id,
            ),
        )
        self._client.commit()
