"""SQLite append-only persistence for immutable SelectionRun artifacts."""

from __future__ import annotations

from ditto_platform.foundation import SQLitePool, traced

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.codec import decode_selection_run, encode_selection_run
from ditto_strategy.selection.contracts import SelectionRun

__all__ = ["SQLiteSelectionRunStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS selection_run (
    run_id       TEXT PRIMARY KEY,
    spec_id      TEXT NOT NULL,
    asset_kind   TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

_CREATE_SPEC_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_selection_run_spec "
    "ON selection_run(spec_id, as_of DESC, run_id DESC);"
)

_INSERT = """
INSERT INTO selection_run (run_id, spec_id, asset_kind, as_of, payload_json)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(run_id) DO NOTHING
"""

_GET = "SELECT payload_json FROM selection_run WHERE run_id = ?"

_LIST_BY_SPEC = """
SELECT run_id, payload_json
FROM selection_run
WHERE spec_id = ?
ORDER BY as_of DESC, run_id DESC
LIMIT ?
"""


class SQLiteSelectionRunStore:
    """Content-addressed store implementing selection read and write ports."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.selection_run.init_schema")
    def init_schema(self) -> None:
        """Create the immutable selection_run table and query index."""
        connection = self._pool.get_connection()
        connection.executescript(_CREATE_TABLE + _CREATE_SPEC_INDEX)
        self._pool.commit()

    @traced("store.selection_run.save")
    def save(self, value: SelectionRun) -> None:
        """Insert an exact run, making exact replay a verified no-op."""
        encoded = encode_selection_run(value).decode()
        connection = self._pool.get_connection()
        connection.execute(
            _INSERT,
            (
                value.run_id,
                value.spec_id,
                value.asset_kind.value,
                value.as_of.isoformat(),
                encoded,
            ),
        )
        row = connection.execute(_GET, (value.run_id,)).fetchone()
        if row is None or str(row["payload_json"]) != encoded:
            self._pool.rollback()
            raise StrategySpecError(
                "selection run identity already owns different evidence",
                details={
                    "reason": "selection_run_identity_conflict",
                    "run_id": value.run_id,
                },
            )
        self._pool.commit()

    @traced("store.selection_run.get")
    def get(self, run_id: str) -> SelectionRun | None:
        """Read and authenticate one exact run."""
        row = self._pool.get_connection().execute(_GET, (run_id,)).fetchone()
        if row is None:
            return None
        return decode_selection_run(
            str(row["payload_json"]),
            expected_run_id=run_id,
        )

    @traced("store.selection_run.list_by_spec")
    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        """List recent authenticated runs for one spec family."""
        if isinstance(limit, bool) or limit < 1:
            raise StrategySpecError(
                "selection run list limit must be positive",
                details={"reason": "invalid_selection_run_limit"},
            )
        rows = self._pool.get_connection().execute(
            _LIST_BY_SPEC,
            (spec_id, limit),
        )
        return [
            decode_selection_run(
                str(row["payload_json"]),
                expected_run_id=str(row["run_id"]),
            )
            for row in rows
        ]
