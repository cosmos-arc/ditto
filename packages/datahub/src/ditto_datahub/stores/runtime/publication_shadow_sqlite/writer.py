"""SQLite-backed writer for derived publication shadow slots."""

from __future__ import annotations

from ditto_datahub.models.publication_safety import DerivedShadowSlotRecord
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["SQLiteDerivedShadowSlotWriter"]


class SQLiteDerivedShadowSlotWriter:
    """Persist shadow slot control-plane rows into SQLite."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def write_slot(self, record: DerivedShadowSlotRecord) -> None:
        """Upsert the current slot for one derived id."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO derived_shadow_slot (
                derived_id, candidate_version, baseline_version,
                activated_at, disabled_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.derived_id,
                record.candidate_version,
                record.baseline_version,
                record.activated_at,
                record.disabled_at,
            ),
        )
        self._sqlite_client.commit()

    def disable_slot(self, derived_id: str, disabled_at: str) -> None:
        """Disable the active slot for one derived id."""
        self._sqlite_client.execute(
            """
            UPDATE derived_shadow_slot
            SET disabled_at = ?
            WHERE derived_id = ? AND disabled_at IS NULL
            """,
            (disabled_at, derived_id),
        )
        self._sqlite_client.commit()
