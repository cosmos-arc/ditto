"""SQLite append-only persistence for immutable next-day plans."""

from __future__ import annotations

from datetime import date, datetime

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient

from ditto_analysis.errors import NextDayPlanIntegrityError
from ditto_analysis.research.plans import NextDayPlan, PlanCandidateNote

__all__ = ["SQLiteNextDayPlanStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS next_day_plan (
    plan_id           TEXT PRIMARY KEY,
    observation_date  TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    payload_json      TEXT NOT NULL
);
"""

_CREATE_RECENT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_next_day_plan_recent "
    "ON next_day_plan(created_at DESC, plan_id DESC);"
)

_CREATE_OBSERVATION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_next_day_plan_observation "
    "ON next_day_plan(observation_date DESC, created_at DESC, plan_id DESC);"
)

_INSERT = """
INSERT INTO next_day_plan (plan_id, observation_date, created_at, payload_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(plan_id) DO NOTHING
"""

_GET_PAYLOAD = "SELECT payload_json FROM next_day_plan WHERE plan_id = ?"

_LIST_RECENT = """
SELECT plan_id, payload_json
FROM next_day_plan
ORDER BY created_at DESC, plan_id DESC
LIMIT ?
"""

_LIST_BY_OBSERVATION = """
SELECT plan_id, payload_json
FROM next_day_plan
WHERE observation_date = ?
ORDER BY created_at DESC, plan_id DESC
LIMIT ?
"""


def _encode(plan: NextDayPlan) -> str:
    """Serialize the canonical record plus the first-recorded timestamp."""
    # created_at rides along for display but stays outside content addressing,
    # so one exact user record keeps one identity across retries.
    return orjson.dumps(
        {**plan.canonical_payload, "created_at": _timestamp(plan.created_at)}
    ).decode()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _decode(payload: str, *, expected_plan_id: str) -> NextDayPlan:
    """Rebuild one plan and refuse payloads that break content addressing."""
    data = orjson.loads(payload)
    try:
        plan = NextDayPlan(
            observation_date=date.fromisoformat(str(data["observation_date"])),
            candidate_notes=tuple(
                PlanCandidateNote(
                    instrument_id=InstrumentId(int(note["instrument_id"])),
                    reason=str(note["reason"]),
                )
                for note in data["candidate_notes"]
            ),
            next_day_plan=str(data["next_day_plan"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            schema_version=int(data["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NextDayPlanIntegrityError(
            "persisted next-day plan payload is not decodable",
            details={"plan_id": expected_plan_id},
        ) from exc
    if plan.plan_id != expected_plan_id:
        raise NextDayPlanIntegrityError(
            "persisted next-day plan payload does not rebuild its identity",
            details={"plan_id": expected_plan_id},
        )
    return plan


class SQLiteNextDayPlanStore:
    """Content-addressed append-only store for post-market next-day plans."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def init_schema(self) -> None:
        """Create the immutable next_day_plan table and query indexes."""
        self._sqlite_client.executescript(
            _CREATE_TABLE + _CREATE_RECENT_INDEX + _CREATE_OBSERVATION_INDEX
        )
        self._sqlite_client.commit()

    def save(self, value: NextDayPlan) -> NextDayPlan:
        """Insert one plan; a canonical replay returns the stored entry."""
        encoded = _encode(value)
        existing = self.get(value.plan_id)
        if existing is not None:
            # created_at stays outside content addressing: a retry that lands
            # later keeps the first-recorded timestamp instead of conflicting.
            if existing.canonical_payload == value.canonical_payload:
                return existing
            raise NextDayPlanIntegrityError(
                "next-day plan identity already owns different content",
                details={"plan_id": value.plan_id},
            )
        self._sqlite_client.execute(
            _INSERT,
            (
                value.plan_id,
                value.observation_date.isoformat(),
                _created_at_text(value),
                encoded,
            ),
        )
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (value.plan_id,))
        if row is None:
            self._sqlite_client.rollback()
            raise NextDayPlanIntegrityError(
                "next-day plan row vanished before verification",
                details={"plan_id": value.plan_id},
            )
        # A concurrent writer with the same canonical record may have committed
        # between our miss and the INSERT (ON CONFLICT DO NOTHING). Compare the
        # canonical content of the stored row — not its embedded created_at —
        # so an exact replay converges on the first-recorded entry instead of
        # being rejected as a content conflict; a truly different payload or a
        # tampered row still fails closed here.
        try:
            stored = _decode(str(row["payload_json"]), expected_plan_id=value.plan_id)
        except NextDayPlanIntegrityError:
            self._sqlite_client.rollback()
            raise
        if stored.canonical_payload != value.canonical_payload:
            self._sqlite_client.rollback()
            raise NextDayPlanIntegrityError(
                "next-day plan identity already owns different content",
                details={"plan_id": value.plan_id},
            )
        self._sqlite_client.commit()
        return stored

    def get(self, plan_id: str) -> NextDayPlan | None:
        """Read and authenticate one exact plan."""
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (plan_id,))
        if row is None:
            return None
        return _decode(str(row["payload_json"]), expected_plan_id=plan_id)

    def list_recent(self, *, limit: int = 20) -> tuple[NextDayPlan, ...]:
        """List the newest recorded plans without reading live market state."""
        rows = self._sqlite_client.fetchall(_LIST_RECENT, (_positive_limit(limit),))
        return tuple(
            _decode(str(row["payload_json"]), expected_plan_id=str(row["plan_id"]))
            for row in rows
        )

    def list_by_observation(
        self, observation_date: str, *, limit: int = 20
    ) -> tuple[NextDayPlan, ...]:
        """List plans recorded for one exact original observation date."""
        rows = self._sqlite_client.fetchall(
            _LIST_BY_OBSERVATION,
            (observation_date, _positive_limit(limit)),
        )
        return tuple(
            _decode(str(row["payload_json"]), expected_plan_id=str(row["plan_id"]))
            for row in rows
        )


def _created_at_text(value: NextDayPlan) -> str:
    """Render the recording instant in canonical sortable UTC form."""
    return value.created_at.isoformat()


def _positive_limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        # 上限是调用方编程合同（HTTP 已限 1..100）：坏值按编程错误暴露。
        raise ValueError("next-day plan list limit must be positive")
    return limit
