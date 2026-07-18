"""SQLite append-only dataset/provider license ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.license import DatasetLicenseRecord, LicensePermission

__all__ = ["SQLiteDatasetLicenseStore"]


class SQLiteDatasetLicenseStore:
    """Durable immutable provider license reviews."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_license_records (
                record_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                source TEXT NOT NULL,
                terms_version TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                local_cache TEXT NOT NULL,
                derivative_compute TEXT NOT NULL,
                display TEXT NOT NULL,
                redistribution TEXT NOT NULL,
                notes TEXT NOT NULL,
                reviewed_by TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                UNIQUE(dataset_id, source, terms_version, effective_from)
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dataset_license_records_product
            ON dataset_license_records(dataset_id, source, effective_from)
            """
        )
        self._client.commit()

    def append_license(self, record: DatasetLicenseRecord) -> None:
        """Append a review, treating an exact duplicate as idempotent."""
        existing = self.get_license(record.record_id)
        if existing is not None:
            if existing == record:
                return
            raise ValueError(f"immutable license record conflict: {record.record_id}")
        try:
            self._client.execute(
                """
                INSERT INTO dataset_license_records (
                    record_id, dataset_id, source, terms_version, effective_from,
                    effective_to, local_cache, derivative_compute, display,
                    redistribution, notes, reviewed_by, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    record.record_id,
                    record.dataset_id,
                    record.source,
                    record.terms_version,
                    record.effective_from.isoformat(),
                    (
                        record.effective_to.isoformat()
                        if record.effective_to is not None
                        else None
                    ),
                    record.local_cache,
                    record.derivative_compute,
                    record.display,
                    record.redistribution,
                    record.notes,
                    record.reviewed_by,
                    record.reviewed_at.isoformat(),
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_license(self, record_id: str) -> DatasetLicenseRecord | None:
        """Return one immutable license review."""
        row = self._client.fetchone(
            "SELECT * FROM dataset_license_records WHERE record_id = ?",
            [record_id],
        )
        return None if row is None else _record_from_row(row)

    def list_licenses(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[DatasetLicenseRecord, ...]:
        """List reviews with optional product/provider filters."""
        rows = self._client.fetchall(
            """
            SELECT * FROM dataset_license_records
            WHERE (? IS NULL OR dataset_id = ?)
              AND (? IS NULL OR source = ?)
            ORDER BY effective_from, reviewed_at, record_id
            """,
            [dataset_id, dataset_id, source, source],
        )
        return tuple(_record_from_row(row) for row in rows)


def _permission(value: object) -> LicensePermission:
    permission = str(value)
    if permission not in {"allowed", "restricted", "prohibited"}:
        raise ValueError(f"invalid persisted license permission: {permission!r}")
    return cast(LicensePermission, permission)


def _record_from_row(row: dict[str, Any]) -> DatasetLicenseRecord:
    return DatasetLicenseRecord(
        record_id=str(row["record_id"]),
        dataset_id=str(row["dataset_id"]),
        source=str(row["source"]),
        terms_version=str(row["terms_version"]),
        effective_from=date.fromisoformat(str(row["effective_from"])),
        effective_to=(
            date.fromisoformat(str(row["effective_to"]))
            if row["effective_to"] is not None
            else None
        ),
        local_cache=_permission(row["local_cache"]),
        derivative_compute=_permission(row["derivative_compute"]),
        display=_permission(row["display"]),
        redistribution=_permission(row["redistribution"]),
        notes=str(row["notes"]),
        reviewed_by=str(row["reviewed_by"]),
        reviewed_at=datetime.fromisoformat(str(row["reviewed_at"])),
    )
