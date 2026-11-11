"""SQLite append-only persistence for immutable Research Case handoffs."""

from __future__ import annotations

from datetime import datetime

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient

from ditto_analysis.errors import ResearchCaseIntegrityError
from ditto_analysis.research.cases import ResearchCase

__all__ = ["SQLiteResearchCaseStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS research_case (
    case_id            TEXT PRIMARY KEY,
    selection_run_id   TEXT NOT NULL,
    as_of              TEXT NOT NULL,
    payload_json       TEXT NOT NULL
);
"""

_CREATE_RUN_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_research_case_run "
    "ON research_case(selection_run_id, as_of DESC, case_id DESC);"
)

_CREATE_RECENT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_research_case_recent "
    "ON research_case(as_of DESC, case_id DESC);"
)

_INSERT = """
INSERT INTO research_case (case_id, selection_run_id, as_of, payload_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(case_id) DO NOTHING
"""

_GET_PAYLOAD = "SELECT payload_json FROM research_case WHERE case_id = ?"

_LIST_RECENT = """
SELECT case_id, payload_json
FROM research_case
ORDER BY as_of DESC, case_id DESC
LIMIT ?
"""

_LIST_BY_RUN = """
SELECT case_id, payload_json
FROM research_case
WHERE selection_run_id = ?
ORDER BY as_of DESC, case_id DESC
LIMIT ?
"""


def _encode(case: ResearchCase) -> str:
    """Serialize the canonical lineage payload without reordering fields."""
    return orjson.dumps(case.canonical_payload).decode()


def _decode(payload: str, *, expected_case_id: str) -> ResearchCase:
    """Rebuild one case and refuse payloads that break content addressing."""
    data = orjson.loads(payload)
    try:
        case = ResearchCase(
            selection_run_id=str(data["selection_run_id"]),
            selection_run_hash=str(data["selection_run_hash"]),
            selection_input_hash=str(data["selection_input_hash"]),
            selection_spec_hash=str(data["selection_spec_hash"]),
            objective=str(data["objective"]),
            asset_kind=str(data["asset_kind"]),
            as_of=datetime.fromisoformat(str(data["as_of"])),
            knowledge_cutoff=datetime.fromisoformat(str(data["knowledge_cutoff"])),
            publication_cutoff=datetime.fromisoformat(str(data["publication_cutoff"])),
            universe_snapshot_id=str(data["universe_snapshot_id"]),
            industry_rotation_snapshot_id=(
                None
                if data["industry_rotation_snapshot_id"] is None
                else str(data["industry_rotation_snapshot_id"])
            ),
            source_snapshot_ids=tuple(
                str(item) for item in data["source_snapshot_ids"]
            ),
            candidate_instrument_ids=tuple(
                InstrumentId(int(item)) for item in data["candidate_instrument_ids"]
            ),
            selection_status=str(data["selection_status"]),
            missing_inputs=tuple(str(item) for item in data["missing_inputs"]),
            schema_version=int(data["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchCaseIntegrityError(
            "persisted research case payload is not decodable",
            details={"case_id": expected_case_id},
        ) from exc
    if case.case_id != expected_case_id:
        raise ResearchCaseIntegrityError(
            "persisted research case payload does not rebuild its identity",
            details={"case_id": expected_case_id},
        )
    return case


class SQLiteResearchCaseStore:
    """Content-addressed append-only store for SelectionRun research cases."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def init_schema(self) -> None:
        """Create the immutable research_case table and query indexes."""
        self._sqlite_client.executescript(
            _CREATE_TABLE + _CREATE_RUN_INDEX + _CREATE_RECENT_INDEX
        )
        self._sqlite_client.commit()

    def save(self, value: ResearchCase) -> None:
        """Insert one case, making an exact replay a verified no-op."""
        encoded = _encode(value)
        self._sqlite_client.execute(
            _INSERT,
            (value.case_id, value.selection_run_id, _as_of_text(value), encoded),
        )
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (value.case_id,))
        if row is None or str(row["payload_json"]) != encoded:
            self._sqlite_client.rollback()
            raise ResearchCaseIntegrityError(
                "research case identity already owns different evidence",
                details={"case_id": value.case_id},
            )
        self._sqlite_client.commit()

    def get(self, case_id: str) -> ResearchCase | None:
        """Read and authenticate one exact case."""
        row = self._sqlite_client.fetchone(_GET_PAYLOAD, (case_id,))
        if row is None:
            return None
        return _decode(str(row["payload_json"]), expected_case_id=case_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchCase, ...]:
        """List the most recently decided cases without reading live state."""
        rows = self._sqlite_client.fetchall(_LIST_RECENT, (_positive_limit(limit),))
        return tuple(
            _decode(str(row["payload_json"]), expected_case_id=str(row["case_id"]))
            for row in rows
        )

    def list_by_run(
        self, selection_run_id: str, *, limit: int = 20
    ) -> tuple[ResearchCase, ...]:
        """List cases handed off from one exact SelectionRun."""
        rows = self._sqlite_client.fetchall(
            _LIST_BY_RUN,
            (selection_run_id, _positive_limit(limit)),
        )
        return tuple(
            _decode(str(row["payload_json"]), expected_case_id=str(row["case_id"]))
            for row in rows
        )


def _as_of_text(value: ResearchCase) -> str:
    """Render the decision instant in canonical sortable UTC form."""
    return value.as_of.isoformat()


def _positive_limit(limit: int) -> int:
    if isinstance(limit, bool) or limit < 1:
        # 上限是调用方编程合同（HTTP 已限 1..100）：坏值按编程错误暴露。
        raise ValueError("research case list limit must be positive")
    return limit
