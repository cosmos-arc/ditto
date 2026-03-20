"""Publication safety runtime record service."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_datahub.stores.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    MinimalDQReader,
    MinimalDQWriter,
    ShadowReportReader,
    ShadowReportWriter,
)


@dataclass(frozen=True)
class PublicationSafetyRuntimeStores:
    """Reader/writer bundle for publication safety runtime records."""

    manifest_reader: ManifestReader
    manifest_writer: ManifestWriter
    minimal_dq_reader: MinimalDQReader
    minimal_dq_writer: MinimalDQWriter
    shadow_report_reader: ShadowReportReader
    shadow_report_writer: ShadowReportWriter
    certification_reader: CertificationReader
    certification_writer: CertificationWriter


class PublicationSafetyRecordService:
    """Unified service for publication safety runtime records."""

    def __init__(self, stores: PublicationSafetyRuntimeStores) -> None:
        self._stores = stores

    def save_manifest(self, record: CompatibilityManifestRecord) -> None:
        """Persist a compatibility manifest record."""
        self._stores.manifest_writer.write_manifest(record)

    def get_manifest(
        self,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord | None:
        """Read a compatibility manifest record."""
        return self._stores.manifest_reader.read_manifest(derived_id, version)

    def save_minimal_dq_summary(self, record: DerivedMinimalDQSummaryRecord) -> None:
        """Persist one minimal DQ summary record."""
        self._stores.minimal_dq_writer.write_summary(record)

    def get_minimal_dq_summary(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Read one minimal DQ summary record."""
        return self._stores.minimal_dq_reader.read_summary(derived_id, version, run_id)

    def get_latest_minimal_dq_summary(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Return the latest minimal DQ summary for one derived version."""
        return self._stores.minimal_dq_reader.get_latest_summary(derived_id, version)

    def save_shadow_report(
        self,
        report: ShadowDiffReportRecord,
        traces: tuple[ShadowTraceRecordRecord, ...],
    ) -> None:
        """Persist a shadow diff report and its traces."""
        self._stores.shadow_report_writer.write_report(report, traces)

    def get_shadow_report(
        self,
        derived_id: str,
        report_id: str,
    ) -> ShadowDiffReportRecord | None:
        """Read a shadow diff report by report id."""
        return self._stores.shadow_report_reader.read_report(derived_id, report_id)

    def list_shadow_traces(
        self,
        derived_id: str,
        report_id: str,
    ) -> list[ShadowTraceRecordRecord]:
        """List trace records for a shadow diff report."""
        return self._stores.shadow_report_reader.list_trace_records(
            derived_id,
            report_id,
        )

    def get_latest_shadow_report(
        self,
        derived_id: str,
        candidate_version: int,
        baseline_version: int,
    ) -> ShadowDiffReportRecord | None:
        """Return the latest shadow diff report for a candidate/baseline pair."""
        return self._stores.shadow_report_reader.get_latest_report(
            derived_id, candidate_version, baseline_version
        )

    def save_certification_report(self, record: CertificationReportRecord) -> None:
        """Persist a certification report record."""
        self._stores.certification_writer.write_report(record)

    def get_certification_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
        report_id: str,
    ) -> CertificationReportRecord | None:
        """Read a certification report by report id."""
        return self._stores.certification_reader.read_report(
            derived_id, version, stage, report_id
        )

    def get_latest_certification_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
    ) -> CertificationReportRecord | None:
        """Return the latest certification report for a version/stage."""
        return self._stores.certification_reader.get_latest_report(
            derived_id,
            version,
            stage,
        )
