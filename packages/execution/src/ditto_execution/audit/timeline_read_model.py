"""Read-model helpers for the execution operating timeline."""

from __future__ import annotations

import sqlite3
from typing import cast

import orjson

from ditto_execution.audit.models import ExecutionTimelineEntry

__all__ = [
    "query_account_snapshot_entries",
    "query_broker_event_entries",
    "query_order_event_entries",
    "query_position_entries",
    "timeline_sort_key",
]


def query_order_event_entries(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    start_date: str | None,
    end_date: str | None,
    order_id: str | None,
) -> tuple[ExecutionTimelineEntry, ...]:
    """Return normalized entries from append-only order journal events."""
    if not _table_exists(conn, "order_events"):
        return ()

    cursor = conn.execute(
        """
        SELECT event_seq, client_id, event_type, event_json, created_at
        FROM order_events
        WHERE (? IS NULL OR client_id = ?)
          AND (? IS NULL OR substr(created_at, 1, 10) >= ?)
          AND (? IS NULL OR substr(created_at, 1, 10) <= ?)
        ORDER BY event_seq ASC
        """,
        (order_id, order_id, start_date, start_date, end_date, end_date),
    )
    return tuple(
        _order_event_row_to_entry(run_id=run_id, row=dict(row))
        for row in cursor.fetchall()
    )


def query_position_entries(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    strategy_id: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[ExecutionTimelineEntry, ...]:
    """Return normalized entries from run-scoped position snapshots."""
    if not _table_exists(conn, "actual_positions"):
        return ()
    if "run_id" not in _table_columns(conn, "actual_positions"):
        return ()

    cursor = conn.execute(
        """
        SELECT rowid AS position_seq, *
        FROM actual_positions
        WHERE run_id = ?
          AND (? IS NULL OR strategy_id = ?)
          AND (? IS NULL OR snapshot_date >= ?)
          AND (? IS NULL OR snapshot_date <= ?)
        ORDER BY snapshot_date ASC, position_seq ASC
        """,
        (
            run_id,
            strategy_id,
            strategy_id,
            start_date,
            start_date,
            end_date,
            end_date,
        ),
    )
    return tuple(_position_row_to_entry(row=dict(row)) for row in cursor.fetchall())


def query_broker_event_entries(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    start_date: str | None,
    end_date: str | None,
    order_id: str | None,
    broker_order_id: str | None = None,
) -> tuple[ExecutionTimelineEntry, ...]:
    """Return normalized entries from broker gateway events."""
    if not _table_exists(conn, "broker_events"):
        return ()

    cursor = conn.execute(
        """
        SELECT rowid AS broker_event_seq, *
        FROM broker_events
        WHERE run_id = ?
          AND (? IS NULL OR order_id = ?)
          AND (? IS NULL OR broker_order_id = ?)
          AND (? IS NULL OR substr(event_time, 1, 10) >= ?)
          AND (? IS NULL OR substr(event_time, 1, 10) <= ?)
        ORDER BY event_time ASC, broker_event_seq ASC
        """,
        (
            run_id,
            order_id,
            order_id,
            broker_order_id,
            broker_order_id,
            start_date,
            start_date,
            end_date,
            end_date,
        ),
    )
    return tuple(_broker_event_row_to_entry(row=dict(row)) for row in cursor.fetchall())


def query_account_snapshot_entries(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    strategy_id: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[ExecutionTimelineEntry, ...]:
    """Return normalized entries from run-scoped account snapshots."""
    if not _table_exists(conn, "account_snapshots"):
        return ()

    cursor = conn.execute(
        """
        SELECT rowid AS account_seq, *
        FROM account_snapshots
        WHERE run_id = ?
          AND (? IS NULL OR strategy_id = ?)
          AND (? IS NULL OR snapshot_date >= ?)
          AND (? IS NULL OR snapshot_date <= ?)
        ORDER BY snapshot_date ASC, created_at ASC, account_seq ASC
        """,
        (
            run_id,
            strategy_id,
            strategy_id,
            start_date,
            start_date,
            end_date,
            end_date,
        ),
    )
    return tuple(
        _account_snapshot_row_to_entry(row=dict(row)) for row in cursor.fetchall()
    )


def timeline_sort_key(entry: ExecutionTimelineEntry) -> tuple[str, str, str, int]:
    """Sort timeline entries by trade date, timestamp, source type and row ID."""
    return (entry.trade_date, entry.created_at, entry.record_type, entry.id)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> frozenset[str]:
    return frozenset(
        str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})")
    )


def _order_event_row_to_entry(
    *, run_id: str, row: dict[str, object]
) -> ExecutionTimelineEntry:
    created_at = str(row["created_at"])
    client_id = str(row["client_id"])
    event_json = cast(str, row["event_json"])
    event_seq = int(cast(int | str, row["event_seq"]))
    payload = cast(dict[str, object], orjson.loads(event_json))
    payload = {
        **payload,
        "event_seq": event_seq,
        "event_type": str(row["event_type"]),
    }
    return ExecutionTimelineEntry(
        id=event_seq,
        run_id=run_id,
        trade_date=created_at[:10],
        record_type="order_event",
        instrument_id=None,
        instrument_scope="order",
        order_id=client_id,
        fill_id=None,
        correlation_id=client_id,
        payload=payload,
        created_at=created_at,
    )


def _position_row_to_entry(*, row: dict[str, object]) -> ExecutionTimelineEntry:
    position_seq = int(cast(int | str, row.pop("position_seq")))
    strategy_id = str(row["strategy_id"])
    return ExecutionTimelineEntry(
        id=position_seq,
        run_id=str(row["run_id"]),
        trade_date=str(row["snapshot_date"]),
        record_type="position_snapshot",
        instrument_id=cast(int, row["instrument_id"]),
        instrument_scope="instrument",
        order_id=None,
        fill_id=None,
        correlation_id=strategy_id,
        payload=row,
        created_at=str(row["created_at"]),
    )


def _broker_event_row_to_entry(*, row: dict[str, object]) -> ExecutionTimelineEntry:
    broker_event_seq = int(cast(int | str, row.pop("broker_event_seq")))
    event_time = str(row["event_time"])
    raw_payload = cast(str, row.pop("payload"))
    adapter_payload = cast(dict[str, object], orjson.loads(raw_payload))
    payload = {
        **row,
        "payload": adapter_payload,
    }
    order_id = cast(str | None, row["order_id"])
    broker_order_id = cast(str | None, row["broker_order_id"])
    correlation_id = cast(str | None, row["correlation_id"])
    if correlation_id is None:
        correlation_id = order_id or broker_order_id
    return ExecutionTimelineEntry(
        id=broker_event_seq,
        run_id=str(row["run_id"]),
        trade_date=event_time[:10],
        record_type="broker_event",
        instrument_id=cast(int | None, row["instrument_id"]),
        instrument_scope="broker",
        order_id=order_id,
        fill_id=cast(str | None, row["fill_id"]),
        correlation_id=correlation_id,
        payload=payload,
        created_at=event_time,
    )


def _account_snapshot_row_to_entry(*, row: dict[str, object]) -> ExecutionTimelineEntry:
    account_seq = int(cast(int | str, row.pop("account_seq")))
    account_id = str(row["account_id"])
    return ExecutionTimelineEntry(
        id=account_seq,
        run_id=str(row["run_id"]),
        trade_date=str(row["snapshot_date"]),
        record_type="account_snapshot",
        instrument_id=None,
        instrument_scope="account",
        order_id=None,
        fill_id=None,
        correlation_id=account_id,
        payload=row,
        created_at=str(row["created_at"]),
    )
