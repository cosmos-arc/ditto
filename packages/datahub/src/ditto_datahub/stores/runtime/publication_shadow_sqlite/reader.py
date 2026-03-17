"""SQLite-backed reader for derived publication shadow slots."""

from __future__ import annotations

from ditto_datahub.models.publication_safety import DerivedShadowSlotRecord
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["SQLiteDerivedShadowSlotReader"]


class SQLiteDerivedShadowSlotReader:
    """Read shadow slot control-plane rows from SQLite."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def read_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the current slot row for one derived id."""
        row = self._sqlite_client.fetchone(
            """
            SELECT derived_id, candidate_version, baseline_version,
                   activated_at, disabled_at
            FROM derived_shadow_slot
            WHERE derived_id = ?
            """,
            (derived_id,),
        )
        if row is None:
            return None
        return DerivedShadowSlotRecord(
            derived_id=row["derived_id"],
            candidate_version=row["candidate_version"],
            baseline_version=row["baseline_version"],
            activated_at=row["activated_at"],
            disabled_at=row["disabled_at"],
        )

    def read_active_slot(self, derived_id: str) -> DerivedShadowSlotRecord | None:
        """Read the active slot row for one derived id."""
        row = self._sqlite_client.fetchone(
            """
            SELECT derived_id, candidate_version, baseline_version,
                   activated_at, disabled_at
            FROM derived_shadow_slot
            WHERE derived_id = ? AND disabled_at IS NULL
            """,
            (derived_id,),
        )
        if row is None:
            return None
        return DerivedShadowSlotRecord(
            derived_id=row["derived_id"],
            candidate_version=row["candidate_version"],
            baseline_version=row["baseline_version"],
            activated_at=row["activated_at"],
            disabled_at=row["disabled_at"],
        )
