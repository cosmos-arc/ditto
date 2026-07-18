"""Read models for independently certified R2 data products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ditto_data.catalog.certification import (
    CertificationReader,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.metadata import default_dataset_metadata

__all__ = [
    "DataProductCheckView",
    "DataProductCoverageView",
    "DataProductEvidenceView",
    "DataProductLicenseView",
    "DataProductOverview",
    "DataProductQualityView",
    "DataProductRunView",
    "DataProductsQueryFacade",
]


@dataclass(frozen=True, slots=True)
class DataProductOverview:
    """One product contract and its currently approved report identity."""

    dataset_id: str
    r2_scope: str
    maturity: str
    schedule: str
    owner: str
    raw_target_from: str | None
    certified_target_from: str | None
    active_certification_report_id: str | None


@dataclass(frozen=True, slots=True)
class DataProductCoverageView:
    """Operational coverage milestones for one product and profile."""

    dataset_id: str
    profile: str
    raw_from: date | None
    complete_from: date | None
    certified_from: date | None
    expected_partitions: int
    actual_partitions: int
    gaps: tuple[date, ...]
    unapproved_gaps: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class DataProductCheckView:
    """One named evidence check exposed to the operations workbench."""

    name: str
    evidence_uri: str
    passed: bool


@dataclass(frozen=True, slots=True)
class DataProductQualityView:
    """DQ, PIT, freshness, recovery, and consumer evidence for one report."""

    dataset_id: str
    profile: str
    report_id: str
    dq_rule_version: str
    dq_results: tuple[DataProductCheckView, ...]
    pit_replay_results: tuple[DataProductCheckView, ...]
    freshness_results: tuple[DataProductCheckView, ...]
    recovery_results: tuple[DataProductCheckView, ...]
    consumer_results: tuple[DataProductCheckView, ...]


@dataclass(frozen=True, slots=True)
class DataProductRunView:
    """One immutable certification generation and its review status."""

    dataset_id: str
    profile: str
    report_id: str
    generated_at: datetime
    content_hash: str
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None


@dataclass(frozen=True, slots=True)
class DataProductEvidenceView:
    """Provider, schema, snapshot, fallback, and override evidence."""

    dataset_id: str
    profile: str
    report_id: str
    content_hash: str
    source_ids: tuple[str, ...]
    schema_versions: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    fallback_history: tuple[str, ...]
    override_history: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataProductLicenseView:
    """License ledger identities bound to one certification report."""

    dataset_id: str
    profile: str
    report_id: str
    license_record_ids: tuple[str, ...]


class DataProductsQueryFacade:
    """Expose R2 product status without coupling product certifications together."""

    def __init__(self, certification_reader: CertificationReader) -> None:
        self._certification_reader = certification_reader

    def list_products(self, *, profile: str) -> tuple[DataProductOverview, ...]:
        """List the 19 hard-scope products with independent active reports."""
        products: list[DataProductOverview] = []
        for metadata in default_dataset_metadata().values():
            contract = metadata.product_contract
            if contract is None or contract.r2_scope != "hard":
                continue
            active = self._certification_reader.get_active_report(
                metadata.dataset_id,
                profile,
            )
            products.append(
                DataProductOverview(
                    dataset_id=metadata.dataset_id,
                    r2_scope=contract.r2_scope,
                    maturity=metadata.maturity,
                    schedule=metadata.schedule,
                    owner=contract.owner,
                    raw_target_from=contract.raw_target_from,
                    certified_target_from=contract.certified_target_from,
                    active_certification_report_id=getattr(
                        active,
                        "report_id",
                        None,
                    ),
                )
            )
        return tuple(products)

    def coverage_view(
        self,
        coverage: DatasetCoverage,
        *,
        profile: str,
    ) -> DataProductCoverageView:
        """Join current machine coverage with an independently approved report."""
        active = self._certification_reader.get_active_report(
            coverage.dataset_id,
            profile,
        )
        return DataProductCoverageView(
            dataset_id=coverage.dataset_id,
            profile=profile,
            raw_from=coverage.raw_from,
            complete_from=coverage.complete_from,
            certified_from=(
                active.coverage.complete_from if active is not None else None
            ),
            expected_partitions=coverage.expected_partitions,
            actual_partitions=coverage.actual_partitions,
            gaps=coverage.gaps,
            unapproved_gaps=coverage.unapproved_gaps,
        )

    def coverage_for_product(
        self,
        dataset_id: str,
        *,
        profile: str,
    ) -> DataProductCoverageView | None:
        """Return the latest frozen coverage with current approval projection."""
        report = self._latest_report(dataset_id, profile)
        if report is None:
            return None
        return self.coverage_view(report.coverage, profile=profile)

    def quality_for_product(
        self,
        dataset_id: str,
        *,
        profile: str,
    ) -> DataProductQualityView | None:
        """Return quality and PIT evidence from the latest immutable report."""
        report = self._latest_report(dataset_id, profile)
        if report is None:
            return None
        evidence = report.evidence
        return DataProductQualityView(
            dataset_id=dataset_id,
            profile=profile,
            report_id=report.report_id,
            dq_rule_version=evidence.dq_rule_version,
            dq_results=_checks(evidence.dq_results),
            pit_replay_results=_checks(evidence.pit_replay_results),
            freshness_results=_checks(evidence.freshness_results),
            recovery_results=_checks(evidence.recovery_results),
            consumer_results=_checks(evidence.consumer_results),
        )

    def runs_for_product(
        self,
        dataset_id: str,
        *,
        profile: str,
    ) -> tuple[DataProductRunView, ...]:
        """Return report generations with approval and revocation projection."""
        runs: list[DataProductRunView] = []
        for report in self._certification_reader.list_reports(dataset_id, profile):
            events = self._certification_reader.list_events(report.report_id)
            latest = events[-1] if events else None
            runs.append(
                DataProductRunView(
                    dataset_id=dataset_id,
                    profile=profile,
                    report_id=report.report_id,
                    generated_at=report.generated_at,
                    content_hash=report.content_hash,
                    status=latest.action if latest is not None else "pending_review",
                    reviewed_by=latest.actor if latest is not None else None,
                    reviewed_at=latest.occurred_at if latest is not None else None,
                    revocation_reason=(
                        latest.reason
                        if latest is not None and latest.action == "revoked"
                        else None
                    ),
                )
            )
        return tuple(runs)

    def evidence_for_product(
        self,
        dataset_id: str,
        *,
        profile: str,
    ) -> DataProductEvidenceView | None:
        """Return source and provenance evidence from the latest report."""
        report = self._latest_report(dataset_id, profile)
        if report is None:
            return None
        evidence = report.evidence
        return DataProductEvidenceView(
            dataset_id=dataset_id,
            profile=profile,
            report_id=report.report_id,
            content_hash=report.content_hash,
            source_ids=evidence.source_ids,
            schema_versions=evidence.schema_versions,
            snapshot_ids=evidence.snapshot_ids,
            fallback_history=evidence.fallback_history,
            override_history=evidence.override_history,
        )

    def license_for_product(
        self,
        dataset_id: str,
        *,
        profile: str,
    ) -> DataProductLicenseView | None:
        """Return license ledger bindings from the latest report."""
        report = self._latest_report(dataset_id, profile)
        if report is None:
            return None
        return DataProductLicenseView(
            dataset_id=dataset_id,
            profile=profile,
            report_id=report.report_id,
            license_record_ids=report.evidence.license_record_ids,
        )

    def _latest_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        reports = self._certification_reader.list_reports(dataset_id, profile)
        return reports[-1] if reports else None


def _checks(checks: tuple[EvidenceCheck, ...]) -> tuple[DataProductCheckView, ...]:
    return tuple(
        DataProductCheckView(
            name=check.name,
            evidence_uri=check.evidence_uri,
            passed=check.passed,
        )
        for check in checks
    )
