"""Validation helpers shared by strict backtest checkpoint codecs."""

from __future__ import annotations

from datetime import date

import orjson

from ditto_backtest.audit.state import ExecutionAuditStateSnapshot

__all__ = [
    "is_canonical_audit_state_json",
    "require_canonical_audit_state_json",
    "require_canonical_json",
    "require_iso_date",
    "require_non_negative_counter",
]


def require_non_negative_counter(name: str, counter: int) -> None:
    """Reject booleans, non-integers, and negative checkpoint counters."""
    if type(counter) is not int or counter < 0:
        raise ValueError(f"checkpoint field {name!r} must be a non-negative integer")


def require_iso_date(name: str, value: str) -> None:
    """Reject empty or malformed checkpoint dates."""
    if not value:
        raise ValueError(f"checkpoint field {name!r} must be a non-empty ISO date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"checkpoint field {name!r} must be an ISO date") from None


def is_canonical_audit_state_json(payload_json: str) -> bool:
    """Return whether a typed execution-audit snapshot is canonical."""
    try:
        require_canonical_audit_state_json(payload_json)
    except (TypeError, ValueError):
        return False
    return True


def require_canonical_audit_state_json(payload_json: str) -> None:
    """Typed-decode the complete audit tree before accepting V2 evidence."""
    ExecutionAuditStateSnapshot.from_canonical_json(payload_json)


def require_canonical_json(name: str, payload_json: str) -> None:
    """Reject empty, invalid, or non-canonical generic R4 evidence JSON."""
    if type(payload_json) is not str or not payload_json:
        raise ValueError(f"checkpoint {name} must be a non-empty string")
    try:
        decoded = orjson.loads(payload_json)
        canonical = orjson.dumps(decoded, option=orjson.OPT_SORT_KEYS).decode()
    except orjson.JSONDecodeError:
        raise ValueError(f"checkpoint {name} must contain valid JSON") from None
    if canonical != payload_json:
        raise ValueError(f"checkpoint {name} JSON is not canonical")
