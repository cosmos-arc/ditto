"""SQLite append-only store for data-product certification governance."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.certification import (
    CertificationReviewEvent,
    DatasetCertificationReport,
    report_from_json,
    report_to_json,
)

__all__ = ["SQLiteCertificationStore"]


class SQLiteCertificationStore:
    """Persist immutable reports and append-only human review events."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_certification_reports (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL UNIQUE,
                dataset_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                report_json TEXT NOT NULL
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_certification_reports_product
            ON dataset_certification_reports(dataset_id, profile, sequence)
            """
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_certification_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (report_id)
                    REFERENCES dataset_certification_reports(report_id)
            )
            """
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_certification_events_report
            ON dataset_certification_events(report_id, event_id)
            """
        )
        self._client.commit()

    def append_report(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        """Freeze a report unless its product already has active conflicting facts."""
        latest = self._latest_report(report.dataset_id, report.profile)
        if latest is not None and self._latest_action(latest.report_id) != "revoked":
            if latest.content_hash == report.content_hash:
                return latest
            product = f"{report.dataset_id}/{report.profile}"
            raise ValueError(f"active certification report conflict: {product}")
        try:
            self._client.execute(
                """
                INSERT INTO dataset_certification_reports (
                    report_id,
                    dataset_id,
                    profile,
                    content_hash,
                    generated_at,
                    report_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    report.report_id,
                    report.dataset_id,
                    report.profile,
                    report.content_hash,
                    report.generated_at.isoformat(),
                    report_to_json(report),
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise
        return report

    def get_report(self, report_id: str) -> DatasetCertificationReport | None:
        """Return one immutable report by identity."""
        row = self._client.fetchone(
            """
            SELECT report_json
            FROM dataset_certification_reports
            WHERE report_id = ?
            """,
            [report_id],
        )
        return None if row is None else report_from_json(str(row["report_json"]))

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        """Return the latest report only when a non-revoked approval exists."""
        report = self._latest_report(dataset_id, profile)
        if report is None or self._latest_action(report.report_id) != "approved":
            return None
        return report

    def list_reports(
        self,
        dataset_id: str,
        profile: str,
    ) -> tuple[DatasetCertificationReport, ...]:
        """Return the full append-only report history in insertion order."""
        rows = self._client.fetchall(
            """
            SELECT report_json
            FROM dataset_certification_reports
            WHERE dataset_id = ? AND profile = ?
            ORDER BY sequence
            """,
            [dataset_id, profile],
        )
        return tuple(report_from_json(str(row["report_json"])) for row in rows)

    def list_events(
        self,
        report_id: str,
    ) -> tuple[CertificationReviewEvent, ...]:
        """Return all human decisions for one immutable report."""
        rows = self._client.fetchall(
            """
            SELECT
                event_id,
                report_id,
                dataset_id,
                profile,
                action,
                actor,
                occurred_at,
                reason
            FROM dataset_certification_events
            WHERE report_id = ?
            ORDER BY event_id
            """,
            [report_id],
        )
        return tuple(_event_from_row(row) for row in rows)

    def approve_report(
        self,
        report_id: str,
        *,
        reviewer: str,
        reviewed_at: datetime,
    ) -> CertificationReviewEvent:
        """Append an independent approval event without mutating machine facts."""
        _validate_actor_time(reviewer, reviewed_at)
        report = self._required_report(report_id)
        latest_action = self._latest_action(report_id)
        if latest_action == "approved":
            return self.list_events(report_id)[-1]
        if latest_action == "revoked":
            raise ValueError("revoked certification report cannot be re-approved")
        return self._append_event(
            report=report,
            action="approved",
            actor=reviewer,
            occurred_at=reviewed_at,
            reason=None,
        )

    def revoke_report(
        self,
        report_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        reason: str,
    ) -> CertificationReviewEvent:
        """Append a revocation while preserving the report and approval history."""
        _validate_actor_time(revoked_by, revoked_at)
        _validate_text("revocation reason", reason)
        report = self._required_report(report_id)
        if self._latest_action(report_id) != "approved":
            raise ValueError("only an approved certification report can be revoked")
        return self._append_event(
            report=report,
            action="revoked",
            actor=revoked_by,
            occurred_at=revoked_at,
            reason=reason,
        )

    def _append_event(
        self,
        *,
        report: DatasetCertificationReport,
        action: Literal["approved", "revoked"],
        actor: str,
        occurred_at: datetime,
        reason: str | None,
    ) -> CertificationReviewEvent:
        try:
            cursor = self._client.execute(
                """
                INSERT INTO dataset_certification_events (
                    report_id,
                    dataset_id,
                    profile,
                    action,
                    actor,
                    occurred_at,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    report.report_id,
                    report.dataset_id,
                    report.profile,
                    action,
                    actor,
                    occurred_at.isoformat(),
                    reason,
                ],
            )
            event_id = cursor.lastrowid
            if event_id is None:
                raise RuntimeError("SQLite did not return a certification event id")
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise
        return CertificationReviewEvent(
            event_id=event_id,
            report_id=report.report_id,
            dataset_id=report.dataset_id,
            profile=report.profile,
            action=action,
            actor=actor,
            occurred_at=occurred_at,
            reason=reason,
        )

    def _required_report(self, report_id: str) -> DatasetCertificationReport:
        report = self.get_report(report_id)
        if report is None:
            raise ValueError(f"unknown certification report: {report_id}")
        return report

    def _latest_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        row = self._client.fetchone(
            """
            SELECT report_json
            FROM dataset_certification_reports
            WHERE dataset_id = ? AND profile = ?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            [dataset_id, profile],
        )
        return None if row is None else report_from_json(str(row["report_json"]))

    def _latest_action(
        self,
        report_id: str,
    ) -> Literal["approved", "revoked"] | None:
        row = self._client.fetchone(
            """
            SELECT action
            FROM dataset_certification_events
            WHERE report_id = ?
            ORDER BY event_id DESC
            LIMIT 1
            """,
            [report_id],
        )
        if row is None:
            return None
        return cast(Literal["approved", "revoked"], str(row["action"]))


def _event_from_row(row: dict[str, Any]) -> CertificationReviewEvent:
    return CertificationReviewEvent(
        event_id=int(row["event_id"]),
        report_id=str(row["report_id"]),
        dataset_id=str(row["dataset_id"]),
        profile=str(row["profile"]),
        action=cast(Literal["approved", "revoked"], str(row["action"])),
        actor=str(row["actor"]),
        occurred_at=datetime.fromisoformat(str(row["occurred_at"])),
        reason=str(row["reason"]) if row["reason"] is not None else None,
    )


def _validate_actor_time(actor: str, occurred_at: datetime) -> None:
    _validate_text("actor", actor)
    if occurred_at.tzinfo is None:
        raise ValueError("certification decision time must be timezone-aware")


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"invalid certification {field}: {value!r}")
