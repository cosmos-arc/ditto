"""Application command boundary for data-product certification governance."""

from __future__ import annotations

from datetime import datetime

from ditto_data.catalog.certification import (
    CertificationGovernanceStore,
    CertificationReviewEvent,
    DatasetCertificationReport,
)

__all__ = ["DataProductCertificationCommands"]


class DataProductCertificationCommands:
    """Freeze reports and append human decisions without mutating machine facts."""

    def __init__(self, store: CertificationGovernanceStore) -> None:
        self._store = store

    def freeze(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        """Persist an immutable report for later independent review."""
        return self._store.append_report(report)

    def review(
        self,
        report_id: str,
        *,
        reviewer: str,
        reviewed_at: datetime,
    ) -> CertificationReviewEvent:
        """Append the human approval decision for a frozen report."""
        return self._store.approve_report(
            report_id,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
        )

    def revoke(
        self,
        report_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        reason: str,
    ) -> CertificationReviewEvent:
        """Append a revocation while keeping the full audit history."""
        return self._store.revoke_report(
            report_id,
            revoked_by=revoked_by,
            revoked_at=revoked_at,
            reason=reason,
        )

    def recertify(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        """Freeze a new report after the preceding certification was revoked."""
        return self._store.append_report(report)
