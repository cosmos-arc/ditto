"""SQLite append-only five-category data specimen evidence store."""

from __future__ import annotations

from typing import Any

import orjson
from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.specimen import DataSpecimen, SpecimenCategory

__all__ = ["SQLiteSpecimenStore"]


class SQLiteSpecimenStore:
    """Durable immutable adjudicated specimen evidence."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS data_specimen_records (
                specimen_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                adjudicated_at TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_data_specimen_records_category
            ON data_specimen_records(category, adjudicated_at, specimen_id)
            """
        )
        self._client.commit()

    def append_specimen(self, specimen: DataSpecimen) -> None:
        """Append one record, treating an identical retry as idempotent."""
        existing = self.get_specimen(specimen.specimen_id)
        if existing is not None:
            if existing == specimen:
                return
            raise ValueError(
                f"immutable specimen record conflict: {specimen.specimen_id}"
            )
        adjudicated_at = (
            specimen.adjudicated_at.isoformat()
            if specimen.adjudicated_at is not None
            else None
        )
        try:
            self._client.execute(
                """
                INSERT INTO data_specimen_records (
                    specimen_id, category, dataset_id, adjudicated_at, payload
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    specimen.specimen_id,
                    specimen.category,
                    specimen.dataset_id,
                    adjudicated_at,
                    orjson.dumps(specimen.to_payload()).decode(),
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_specimen(self, specimen_id: str) -> DataSpecimen | None:
        """Return one immutable specimen record."""
        row = self._client.fetchone(
            "SELECT payload FROM data_specimen_records WHERE specimen_id = ?",
            [specimen_id],
        )
        return None if row is None else _specimen_from_row(row)

    def list_specimens(
        self,
        *,
        category: SpecimenCategory | None = None,
        dataset_id: str | None = None,
    ) -> tuple[DataSpecimen, ...]:
        """List adjudicated records newest-first with optional filters."""
        rows = self._client.fetchall(
            """
            SELECT payload FROM data_specimen_records
            WHERE (? IS NULL OR category = ?)
              AND (? IS NULL OR dataset_id = ?)
            ORDER BY adjudicated_at IS NULL, adjudicated_at DESC, specimen_id
            """,
            [category, category, dataset_id, dataset_id],
        )
        return tuple(_specimen_from_row(row) for row in rows)


def _specimen_from_row(row: dict[str, Any]) -> DataSpecimen:
    return DataSpecimen.from_payload(orjson.loads(str(row["payload"])))
