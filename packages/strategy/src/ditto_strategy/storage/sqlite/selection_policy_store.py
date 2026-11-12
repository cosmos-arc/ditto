"""SQLite append-only persistence for immutable SelectionSpec policy snapshots."""

from __future__ import annotations

from ditto_platform.foundation import SQLitePool, traced

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.codec import (
    decode_selection_policy,
    encode_selection_policy,
)
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    StockSelectionSpec,
    canonical_spec_hash,
)

__all__ = ["SQLiteSelectionPolicyStore"]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS selection_policy_snapshot (
    spec_hash    TEXT PRIMARY KEY,
    spec_id      TEXT NOT NULL,
    asset_kind   TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

_INSERT = """
INSERT INTO selection_policy_snapshot (spec_hash, spec_id, asset_kind, payload_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(spec_hash) DO NOTHING
"""

_GET = "SELECT payload_json FROM selection_policy_snapshot WHERE spec_hash = ?"


class SQLiteSelectionPolicyStore:
    """Content-addressed store implementing selection policy read/write ports."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("store.selection_policy.init_schema")
    def init_schema(self) -> None:
        """Create the immutable selection_policy_snapshot table."""
        connection = self._pool.get_connection()
        connection.executescript(_CREATE_TABLE)
        self._pool.commit()

    @traced("store.selection_policy.save_policy")
    def save_policy(self, value: StockSelectionSpec | EtfSelectionSpec) -> None:
        """Insert one exact policy snapshot, making exact replay a no-op."""
        spec_hash = canonical_spec_hash(value)
        encoded = encode_selection_policy(value).decode()
        connection = self._pool.get_connection()
        connection.execute(
            _INSERT,
            (
                spec_hash,
                value.spec_id,
                value.asset_kind.value,
                encoded,
            ),
        )
        row = connection.execute(_GET, (spec_hash,)).fetchone()
        if row is None or str(row["payload_json"]) != encoded:
            self._pool.rollback()
            raise StrategySpecError(
                "selection policy identity already owns different evidence",
                details={
                    "reason": "selection_policy_identity_conflict",
                    "spec_hash": spec_hash,
                },
            )
        self._pool.commit()

    @traced("store.selection_policy.policy_by_hash")
    def policy_by_hash(
        self, spec_hash: str
    ) -> StockSelectionSpec | EtfSelectionSpec | None:
        """Return one exact policy or None; tampered payloads fail closed."""
        row = self._pool.get_connection().execute(_GET, (spec_hash,)).fetchone()
        if row is None:
            return None
        return decode_selection_policy(
            str(row["payload_json"]),
            expected_spec_hash=spec_hash,
        )
