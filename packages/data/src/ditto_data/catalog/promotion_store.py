"""SQLite-backed dataset promotion evidence store."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
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
            CREATE TABLE IF NOT EXISTS dataset_promotion_evidence_log (
                evidence_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                criterion TEXT NOT NULL,
                evidence_uri TEXT NOT NULL,
                approved_by TEXT NOT NULL,
                passed INTEGER NOT NULL,
                notes TEXT,
                reviewed_at TEXT,
                assessed_event_sequence INTEGER NOT NULL DEFAULT 0
            )
            """,
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dataset_promotion_evidence_log_dataset
            ON dataset_promotion_evidence_log(dataset_id)
            """,
        )
        # One-time migration (#383): legacy last-write-wins rows move into the
        # append-only log as unattributed (sequence 0 = never survives a
        # revocation), then the legacy table is retired.
        legacy = self._client.fetchone(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'dataset_promotion_evidence'
            """,
        )
        if legacy is not None:
            try:
                self._client.execute(
                    """
                    INSERT INTO dataset_promotion_evidence_log (
                        dataset_id, criterion, evidence_uri, approved_by,
                        passed, notes, reviewed_at, assessed_event_sequence
                    )
                    SELECT dataset_id, criterion, evidence_uri, approved_by,
                           passed, notes, reviewed_at, 0
                    FROM dataset_promotion_evidence
                    """,
                )
                self._client.execute("DROP TABLE dataset_promotion_evidence")
                self._client.commit()
            except Exception:
                self._client.rollback()
                raise
        self._client.commit()

    def upsert_dataset_evidence(
        self,
        dataset_id: str,
        evidence: DatasetPromotionEvidence,
    ) -> None:
        """Append one immutable evidence review to the log (#383)."""
        _validate_dataset_id(dataset_id)
        try:
            self._client.execute(
                """
                INSERT INTO dataset_promotion_evidence_log (
                    dataset_id,
                    criterion,
                    evidence_uri,
                    approved_by,
                    passed,
                    notes,
                    reviewed_at,
                    assessed_event_sequence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    evidence.assessed_event_sequence,
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
                reviewed_at,
                assessed_event_sequence
            FROM dataset_promotion_evidence_log AS current
            WHERE dataset_id = ?
              AND evidence_sequence = (
                SELECT MAX(evidence_sequence)
                FROM dataset_promotion_evidence_log AS newer
                WHERE newer.dataset_id = current.dataset_id
                  AND newer.criterion = current.criterion
              )
            ORDER BY criterion
            """,
            [dataset_id],
        )
        return tuple(_evidence_from_row(row) for row in rows)

    def list_dataset_evidence_history(
        self,
        dataset_id: str,
    ) -> tuple[DatasetPromotionEvidence, ...]:
        """Return the full append-only evidence audit trail for one dataset."""
        _validate_dataset_id(dataset_id)
        rows = self._client.fetchall(
            """
            SELECT
                criterion,
                evidence_uri,
                approved_by,
                passed,
                notes,
                reviewed_at,
                assessed_event_sequence
            FROM dataset_promotion_evidence_log
            WHERE dataset_id = ?
            ORDER BY evidence_sequence
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
        assessed_event_sequence=int(row.get("assessed_event_sequence") or 0),
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _normalized_instant_text(instant: datetime | None) -> str | None:
    """Serialize a timezone-aware instant as UTC ISO text for ordered compares."""
    if instant is None or instant.tzinfo is None:
        return None
    return instant.astimezone(UTC).isoformat()


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
        *,
        assessed_event_sequence: int,
    ) -> None:
        """
        Insert or replace a dataset maturity promotion override.

        Fails closed when a revocation event appended after
        ``assessed_event_sequence`` (the caller's assessment snapshot) already
        exists: a promotion computed from pre-revocation evidence must not
        resurrect a revoked override (#380). The append-only event sequence is
        the single write order — no timestamp comparison is needed or used.
        """
        _validate_dataset_id(promotion.dataset_id)
        promoted_at_text = _normalized_instant_text(promotion.promoted_at)
        if promoted_at_text is None:
            msg = (
                "cannot upsert a promotion without a timezone-aware "
                f"promoted_at: {promotion.dataset_id}"
            )
            raise ValueError(msg)
        if assessed_event_sequence < 0:
            msg = (
                "assessed_event_sequence must be a non-negative append-only "
                f"sequence: {promotion.dataset_id}"
            )
            raise ValueError(msg)
        try:
            # The revocation guard lives in the same statement as the write,
            # so a concurrent revoke cannot interleave between check and upsert.
            cursor = self._client.execute(
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
                SELECT ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dataset_maturity_promotion_events
                    WHERE dataset_id = ?
                      AND action = 'revoked'
                      AND event_id > ?
                )
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
                    promoted_at_text,
                    promotion.evidence_uri,
                    promotion.notes,
                    promotion.dataset_id,
                    assessed_event_sequence,
                ],
            )
            if cursor.rowcount != 1:
                msg = (
                    "cannot upsert a promotion superseded by a newer "
                    f"revocation: {promotion.dataset_id}"
                )
                raise ValueError(msg)
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
                event_id,
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
        if revoked_at.tzinfo is None:
            msg = (
                "revoked_at must be timezone-aware to order against "
                f"promotions: {dataset_id}"
            )
            raise ValueError(msg)
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
            sequence = self._insert_promotion_event(event)
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise
        return replace(event, sequence=sequence)

    def _insert_promotion_event(
        self,
        event: DatasetMaturityPromotionEvent,
    ) -> int:
        cursor = self._client.execute(
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
                _normalized_instant_text(event.action_at),
                event.evidence_uri,
                event.revocation_reason,
                event.notes,
            ],
        )
        return int(cursor.lastrowid or 0)


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
        sequence=int(row["event_id"]),
    )
