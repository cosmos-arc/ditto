"""SQLite-backed dataset promotion evidence store."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.metadata import DatasetMaturity
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetMaturityPromotionRevocationReason,
    DatasetPromotionEvidence,
)

__all__ = [
    "SQLiteDatasetMaturityPromotionStore",
    "SQLiteDatasetPromotionEvidenceStore",
]


class SQLiteDatasetPromotionEvidenceStore:
    """Durable store for catalog-owned dataset promotion evidence."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_promotion_evidence (
                dataset_id TEXT NOT NULL,
                criterion TEXT NOT NULL,
                evidence_uri TEXT NOT NULL,
                approved_by TEXT NOT NULL,
                passed INTEGER NOT NULL,
                notes TEXT,
                reviewed_at TEXT,
                PRIMARY KEY (dataset_id, criterion)
            )
            """,
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dataset_promotion_evidence_dataset
            ON dataset_promotion_evidence(dataset_id)
            """,
        )
        self._client.commit()

    def upsert_dataset_evidence(
        self,
        dataset_id: str,
        evidence: DatasetPromotionEvidence,
    ) -> None:
        """Insert or replace evidence for a dataset criterion."""
        _validate_dataset_id(dataset_id)
        try:
            self._client.execute(
                """
                INSERT INTO dataset_promotion_evidence (
                    dataset_id,
                    criterion,
                    evidence_uri,
                    approved_by,
                    passed,
                    notes,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (dataset_id, criterion)
                DO UPDATE SET
                    evidence_uri = excluded.evidence_uri,
                    approved_by = excluded.approved_by,
                    passed = excluded.passed,
                    notes = excluded.notes,
                    reviewed_at = excluded.reviewed_at
                """,
                [
                    dataset_id,
                    evidence.criterion,
                    evidence.evidence_uri,
                    evidence.approved_by,
                    1 if evidence.passed else 0,
                    evidence.notes,
                    evidence.reviewed_at.isoformat()
                    if evidence.reviewed_at is not None
                    else None,
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def list_dataset_evidence(
        self,
        dataset_id: str,
    ) -> tuple[DatasetPromotionEvidence, ...]:
        """Return persisted promotion evidence for one dataset."""
        _validate_dataset_id(dataset_id)
        rows = self._client.fetchall(
            """
            SELECT
                criterion,
                evidence_uri,
                approved_by,
                passed,
                notes,
                reviewed_at
            FROM dataset_promotion_evidence
            WHERE dataset_id = ?
            ORDER BY criterion
            """,
            [dataset_id],
        )
        return tuple(_evidence_from_row(row) for row in rows)


def _evidence_from_row(row: dict[str, Any]) -> DatasetPromotionEvidence:
    return DatasetPromotionEvidence(
        criterion=str(row["criterion"]),
        evidence_uri=str(row["evidence_uri"]),
        approved_by=str(row["approved_by"]),
        passed=bool(row["passed"]),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        reviewed_at=_optional_datetime(row["reviewed_at"]),
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _validate_dataset_id(dataset_id: str) -> None:
    if not dataset_id or dataset_id.strip() != dataset_id:
        msg = f"Invalid dataset_id: {dataset_id!r}"
        raise ValueError(msg)


class SQLiteDatasetMaturityPromotionStore:
    """Durable current-state store for dataset maturity promotion overrides."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_maturity_promotions (
                dataset_id TEXT PRIMARY KEY,
                previous_maturity TEXT NOT NULL,
                promoted_maturity TEXT NOT NULL,
                promoted_by TEXT NOT NULL,
                promoted_at TEXT,
                evidence_uri TEXT,
                notes TEXT
            )
            """,
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_maturity_promotion_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                action TEXT NOT NULL,
                previous_maturity TEXT NOT NULL,
                next_maturity TEXT NOT NULL,
                actor TEXT NOT NULL,
                action_at TEXT,
                evidence_uri TEXT,
                revocation_reason TEXT,
                notes TEXT
            )
            """,
        )
        self._ensure_promotion_events_revocation_reason_column()
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dataset_maturity_events_dataset
            ON dataset_maturity_promotion_events(dataset_id, event_id)
            """,
        )
        self._client.commit()

    def _ensure_promotion_events_revocation_reason_column(self) -> None:
        columns = {
            str(row["name"])
            for row in self._client.fetchall(
                "PRAGMA table_info(dataset_maturity_promotion_events)"
            )
        }
        if "revocation_reason" not in columns:
            self._client.execute(
                """
                ALTER TABLE dataset_maturity_promotion_events
                ADD COLUMN revocation_reason TEXT
                """,
            )

    def upsert_dataset_maturity_promotion(
        self,
        promotion: DatasetMaturityPromotion,
    ) -> None:
        """Insert or replace a dataset maturity promotion override."""
        _validate_dataset_id(promotion.dataset_id)
        try:
            self._client.execute(
                """
                INSERT INTO dataset_maturity_promotions (
                    dataset_id,
                    previous_maturity,
                    promoted_maturity,
                    promoted_by,
                    promoted_at,
                    evidence_uri,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (dataset_id)
                DO UPDATE SET
                    previous_maturity = excluded.previous_maturity,
                    promoted_maturity = excluded.promoted_maturity,
                    promoted_by = excluded.promoted_by,
                    promoted_at = excluded.promoted_at,
                    evidence_uri = excluded.evidence_uri,
                    notes = excluded.notes
                """,
                [
                    promotion.dataset_id,
                    promotion.previous_maturity,
                    promotion.promoted_maturity,
                    promotion.promoted_by,
                    promotion.promoted_at.isoformat()
                    if promotion.promoted_at is not None
                    else None,
                    promotion.evidence_uri,
                    promotion.notes,
                ],
            )
            self._insert_promotion_event(
                DatasetMaturityPromotionEvent(
                    dataset_id=promotion.dataset_id,
                    action="promoted",
                    previous_maturity=promotion.previous_maturity,
                    next_maturity=promotion.promoted_maturity,
                    actor=promotion.promoted_by,
                    action_at=promotion.promoted_at,
                    evidence_uri=promotion.evidence_uri,
                    notes=promotion.notes,
                )
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        """Return the current promotion override for one dataset, if any."""
        _validate_dataset_id(dataset_id)
        row = self._client.fetchone(
            """
            SELECT
                dataset_id,
                previous_maturity,
                promoted_maturity,
                promoted_by,
                promoted_at,
                evidence_uri,
                notes
            FROM dataset_maturity_promotions
            WHERE dataset_id = ?
            """,
            [dataset_id],
        )
        if row is None:
            return None
        return _promotion_from_row(row)

    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        """Return promotion governance events for one dataset."""
        _validate_dataset_id(dataset_id)
        rows = self._client.fetchall(
            """
            SELECT
                dataset_id,
                action,
                previous_maturity,
                next_maturity,
                actor,
                action_at,
                evidence_uri,
                revocation_reason,
                notes
            FROM dataset_maturity_promotion_events
            WHERE dataset_id = ?
            ORDER BY event_id
            """,
            [dataset_id],
        )
        return tuple(_promotion_event_from_row(row) for row in rows)

    def revoke_dataset_maturity_promotion(
        self,
        dataset_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        revocation_reason: DatasetMaturityPromotionRevocationReason,
        notes: str | None = None,
    ) -> DatasetMaturityPromotionEvent:
        """Remove a current promotion override and append a revoke event."""
        _validate_dataset_id(dataset_id)
        current = self.get_dataset_maturity_promotion(dataset_id)
        if current is None:
            msg = f"No active maturity promotion for dataset: {dataset_id}"
            raise ValueError(msg)
        event = DatasetMaturityPromotionEvent(
            dataset_id=dataset_id,
            action="revoked",
            previous_maturity=current.promoted_maturity,
            next_maturity=current.previous_maturity,
            actor=revoked_by,
            action_at=revoked_at,
            evidence_uri=current.evidence_uri,
            revocation_reason=revocation_reason,
            notes=notes,
        )
        try:
            self._client.execute(
                """
                DELETE FROM dataset_maturity_promotions
                WHERE dataset_id = ?
                """,
                [dataset_id],
            )
            self._insert_promotion_event(event)
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise
        return event

    def _insert_promotion_event(
        self,
        event: DatasetMaturityPromotionEvent,
    ) -> None:
        self._client.execute(
            """
            INSERT INTO dataset_maturity_promotion_events (
                dataset_id,
                action,
                previous_maturity,
                next_maturity,
                actor,
                action_at,
                evidence_uri,
                revocation_reason,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event.dataset_id,
                event.action,
                event.previous_maturity,
                event.next_maturity,
                event.actor,
                event.action_at.isoformat() if event.action_at is not None else None,
                event.evidence_uri,
                event.revocation_reason,
                event.notes,
            ],
        )


def _promotion_from_row(row: dict[str, Any]) -> DatasetMaturityPromotion:
    return DatasetMaturityPromotion(
        dataset_id=str(row["dataset_id"]),
        previous_maturity=cast(DatasetMaturity, str(row["previous_maturity"])),
        promoted_maturity=cast(DatasetMaturity, str(row["promoted_maturity"])),
        promoted_by=str(row["promoted_by"]),
        promoted_at=_optional_datetime(row["promoted_at"]),
        evidence_uri=str(row["evidence_uri"])
        if row["evidence_uri"] is not None
        else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
    )


def _promotion_event_from_row(row: dict[str, Any]) -> DatasetMaturityPromotionEvent:
    return DatasetMaturityPromotionEvent(
        dataset_id=str(row["dataset_id"]),
        action=cast(Literal["promoted", "revoked"], str(row["action"])),
        previous_maturity=cast(DatasetMaturity, str(row["previous_maturity"])),
        next_maturity=cast(DatasetMaturity, str(row["next_maturity"])),
        actor=str(row["actor"]),
        action_at=_optional_datetime(row["action_at"]),
        evidence_uri=str(row["evidence_uri"])
        if row["evidence_uri"] is not None
        else None,
        revocation_reason=cast(
            DatasetMaturityPromotionRevocationReason,
            str(row["revocation_reason"]),
        )
        if row["revocation_reason"] is not None
        else None,
        notes=str(row["notes"]) if row["notes"] is not None else None,
    )
