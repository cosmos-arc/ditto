"""Process-wide monotonic UTC clock for strategy governance provenance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

_CLOCK_LOCK = Lock()


class _ClockState:
    last_issued_at: datetime | None = None


_CLOCK_STATE = _ClockState()


def utc_now_iso() -> str:
    """Return a unique UTC instant, advancing by one microsecond on rollback."""
    with _CLOCK_LOCK:
        candidate = datetime.now(UTC)
        if (
            _CLOCK_STATE.last_issued_at is not None
            and candidate <= _CLOCK_STATE.last_issued_at
        ):
            candidate = _CLOCK_STATE.last_issued_at + timedelta(microseconds=1)
        _CLOCK_STATE.last_issued_at = candidate
        return candidate.isoformat(timespec="microseconds").replace("+00:00", "Z")
