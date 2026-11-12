"""SQLite append-only persistence for immutable research judgments."""

from __future__ import annotations

from datetime import datetime

import orjson
from ditto_platform.foundation import SQLiteClient

from ditto_analysis.errors import ResearchJudgmentIntegrityError
from ditto_analysis.research.judgments import ResearchJudgment

__all__ = ["SQLiteResearchJudgmentStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS research_judgment (
    judgment_id    TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    payload_json   TEXT NOT NULL
);
"""

_CREATE_RECENT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_research_judgment_recent "
    "ON research_judgment(created_at DESC, judgment_id DESC);"
)

_INSERT = """
INSERT INTO research_judgment (judgment_id, created_at, payload_json)
VALUES (?, ?, ?)
ON CONFLICT(judgment_id) DO NOTHING
"""

_GET_PAYLOAD = "SELECT payload_json FROM research_judgment WHERE judgment_id = ?"

_LIST_RECENT = """
SELECT judgment_id, payload_json
FROM research_judgment
ORDER BY created_at DESC, judgment_id DESC
LIMIT ?
"""


def _encode(judgment: ResearchJudgment) -> str:
    """Serialize the canonical record plus the first-recorded timestamp."""
    # created_at rides along for display but stays outside content addressing,
    # so one exact user record keeps one identity across retries.
    return orjson.dumps(
        {**judgment.canonical_payload, "created_at": _timestamp(judgment.created_at)}
    ).decode()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _decode(payload: str, *, expected_judgment_id: str) -> ResearchJudgment:
    """Rebuild one judgment and refuse payloads that break content addressing."""
    data = orjson.loads(payload)
    try:
        judgment = ResearchJudgment(
            run_ids=tuple(str(item) for item in data["run_ids"]),
            judgment=str(data["judgment"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            strategy_id=(str(data["strategy_id"]) if "strategy_id" in data else None),
            strategy_version=(
                int(data["strategy_version"]) if "strategy_version" in data else None
            ),
            schema_version=int(data["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchJudgmentIntegrityError(
            "persisted research judgment payload is not decodable",
            details={"judgment_id": expected_judgment_id},
        ) from exc
    if judgment.judgment_id != expected_judgment_id:
        raise ResearchJudgmentIntegrityError(
            "persisted research judgment payload does not rebuild its identity",
            details={"judgment_id": expected_judgment_id},
        )
    return judgment


class SQLiteResearchJudgmentStore:
    """Content-addressed append-only store for saved research judgments."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def init_schema(self) -> None:
        """Create the immutable research_judgment table and query index."""
        self._sqlite_client.executescript(_CREATE_TABLE + _CREATE_RECENT_INDEX)
        self._sqlite_client.commit()

    def save(self, value: ResearchJudgment) -> ResearchJudgment:
        """Insert one judgment; a canonical replay returns the stored entry."""
        encoded = _encode(value)
        existing = self.get(value.judgment_id)
        if existing is not None:
            # created_at stays outside content addressing: a retry that lands
            # later keeps the first-recorded timestamp instead of conflicting.
            if existing.canonical_payload == value.canonical_payload:
                return existing
            raise ResearchJudgmentIntegrityError(
                "research judgment identity already owns different content",
                details={"judgment_id": value.judgment_id},
            )
        self._sqlite_client.execute(
            _INSERT,
            (
                value.judgment_id,
                value.created_at.isoformat(),
                encoded,
            ),
        )
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (value.judgment_id,))
        if row is None:
            self._sqlite_client.rollback()
            raise ResearchJudgmentIntegrityError(
                "research judgment row vanished before verification",
                details={"judgment_id": value.judgment_id},
            )
        # A concurrent writer with the same canonical record may have committed
        # between our miss and the INSERT (ON CONFLICT DO NOTHING). Compare the
        # canonical content of the stored row — not its embedded created_at —
        # so an exact replay converges on the first-recorded entry instead of
        # being rejected as a content conflict; a truly different payload or a
        # tampered row still fails closed here.
        try:
            stored = _decode(
                str(row["payload_json"]), expected_judgment_id=value.judgment_id
            )
        except ResearchJudgmentIntegrityError:
            self._sqlite_client.rollback()
            raise
        if stored.canonical_payload != value.canonical_payload:
            self._sqlite_client.rollback()
            raise ResearchJudgmentIntegrityError(
                "research judgment identity already owns different content",
                details={"judgment_id": value.judgment_id},
            )
        self._sqlite_client.commit()
        return stored

    def get(self, judgment_id: str) -> ResearchJudgment | None:
        """Read and authenticate one exact judgment."""
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (judgment_id,))
        if row is None:
            return None
        return _decode(str(row["payload_json"]), expected_judgment_id=judgment_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchJudgment, ...]:
        """List the newest saved judgments without reading run artifacts."""
        rows = self._sqlite_client.fetchall(_LIST_RECENT, (_positive_limit(limit),))
        return tuple(
            _decode(
                str(row["payload_json"]),
                expected_judgment_id=str(row["judgment_id"]),
            )
            for row in rows
        )


def _positive_limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        # 上限是调用方编程合同（HTTP 已限 1..100）：坏值按编程错误暴露。
        raise ValueError("research judgment list limit must be positive")
    return limit
