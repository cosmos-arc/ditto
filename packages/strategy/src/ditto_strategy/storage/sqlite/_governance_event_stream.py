"""Stable merged reads and append validation for governance event streams."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Never

from ditto_strategy.governance.models import StrategyGovernanceEvent
from ditto_strategy.governance.protocols import (
    InvalidStrategyGovernanceEventCursor,
    StrategyGovernanceEventIntegrityError,
)

type ConflictFactory = Callable[[str], Exception]
type EventKey = tuple[datetime, str]

_GOVERNANCE_EVENTS_UNION = """
SELECT event_id, strategy_id, 'decision' AS event_type,
       version AS target_version, decision AS decision_or_activation_kind,
       actor, reason, decided_at AS occurred_at
FROM strategy_decision_event
WHERE strategy_id = ?
UNION ALL
SELECT event_id, strategy_id, 'activation' AS event_type,
       target_version, activation_kind AS decision_or_activation_kind,
       actor, reason, activated_at AS occurred_at
FROM strategy_activation_event
WHERE strategy_id = ?
"""
_GOVERNANCE_EVENT_ID_EXISTS = """
SELECT event_id FROM strategy_decision_event WHERE event_id = ?
UNION ALL
SELECT event_id FROM strategy_activation_event WHERE event_id = ?
"""


@dataclass(frozen=True, slots=True)
class PendingGovernanceEvent:
    """Minimal identity needed to validate one event before insertion."""

    event_id: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class _PositionedEvent:
    event: StrategyGovernanceEvent
    key: EventKey


def _integrity_error(message: str) -> StrategyGovernanceEventIntegrityError:
    return StrategyGovernanceEventIntegrityError(
        f"STRATEGY_GOVERNANCE_EVENT_INTEGRITY_ERROR: {message}"
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _integrity_error(f"invalid occurred_at timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _integrity_error(
            f"occurred_at timestamp must be timezone-aware: {value!r}"
        )
    return parsed.astimezone(UTC)


def _row_to_positioned_event(row: sqlite3.Row) -> _PositionedEvent:
    event_id = str(row["event_id"])
    if not event_id.strip():
        raise _integrity_error("event_id must not be empty")
    occurred_at = str(row["occurred_at"])
    event = StrategyGovernanceEvent(
        event_id=event_id,
        strategy_id=str(row["strategy_id"]),
        event_type=str(row["event_type"]),
        target_version=int(row["target_version"]),
        decision_or_activation_kind=str(row["decision_or_activation_kind"]),
        actor=str(row["actor"]),
        reason=str(row["reason"]),
        occurred_at=occurred_at,
    )
    return _PositionedEvent(event=event, key=(_parse_timestamp(occurred_at), event_id))


def _load_positioned_events(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> tuple[_PositionedEvent, ...]:
    rows = conn.execute(
        _GOVERNANCE_EVENTS_UNION,
        (strategy_id, strategy_id),
    ).fetchall()
    positioned = tuple(_row_to_positioned_event(row) for row in rows)
    event_ids = [item.event.event_id for item in positioned]
    if len(set(event_ids)) != len(event_ids):
        raise _integrity_error(f"duplicate event_id in strategy stream: {strategy_id}")
    return tuple(sorted(positioned, key=lambda item: item.key))


def list_governance_events(
    conn: sqlite3.Connection,
    strategy_id: str,
    *,
    after_event_id: str | None,
    limit: int,
) -> tuple[StrategyGovernanceEvent, ...]:
    """Return a semantically sorted page after validating the whole stream."""
    positioned = _load_positioned_events(conn, strategy_id)
    start = 0
    if after_event_id is not None:
        for index, item in enumerate(positioned):
            if item.event.event_id == after_event_id:
                start = index + 1
                break
        else:
            raise InvalidStrategyGovernanceEventCursor(
                f"INVALID_EVENT_CURSOR: {after_event_id}"
            )
    return tuple(item.event for item in positioned[start : start + limit])


def _raise_conflict(conflict_factory: ConflictFactory, message: str) -> Never:
    raise conflict_factory(message)


def validate_new_governance_events(
    conn: sqlite3.Connection,
    strategy_id: str,
    events: Sequence[PendingGovernanceEvent],
    conflict_factory: ConflictFactory,
) -> None:
    """Enforce global event identity and append-only semantic positions."""
    if not events:
        return
    event_ids = tuple(event.event_id for event in events)
    if any(not event_id.strip() for event_id in event_ids):
        _raise_conflict(conflict_factory, "governance event_id must not be empty")
    if len(set(event_ids)) != len(event_ids):
        _raise_conflict(
            conflict_factory,
            "governance event_ids in one transaction must be distinct",
        )

    for event_id in event_ids:
        existing = conn.execute(
            _GOVERNANCE_EVENT_ID_EXISTS,
            (event_id, event_id),
        ).fetchone()
        if existing is not None:
            _raise_conflict(
                conflict_factory,
                f"governance event_id already exists: {existing['event_id']}",
            )

    keys: list[EventKey] = []
    for event in events:
        try:
            occurred_at = _parse_timestamp(event.occurred_at)
        except StrategyGovernanceEventIntegrityError as exc:
            _raise_conflict(conflict_factory, str(exc))
        keys.append((occurred_at, event.event_id))
    keys.sort()
    if any(current <= previous for previous, current in pairwise(keys)):
        _raise_conflict(
            conflict_factory,
            "governance event keys must be strictly increasing within a transaction",
        )

    persisted = _load_positioned_events(conn, strategy_id)
    if persisted and keys[0] <= persisted[-1].key:
        _raise_conflict(
            conflict_factory,
            "governance event key must be strictly greater than "
            + "the current stream tail",
        )
