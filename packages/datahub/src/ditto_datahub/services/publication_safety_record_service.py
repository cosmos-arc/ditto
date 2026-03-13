"""Publication safety runtime record service."""

from __future__ import annotations

from ditto_datahub.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)
from ditto_datahub.stores.runtime.publication_safety import (
    CertificationReader,
    CertificationWriter,
    ManifestReader,
    ManifestWriter,
    ShadowReportReader,
    ShadowReportWriter,
)


class PublicationSafetyRecordService:
    """Unified service for publication safety runtime records."""

    def __init__(
        self,
        manifest_reader: ManifestReader,
        manifest_writer: ManifestWriter,
        shadow_report_reader: ShadowReportReader,
        shadow_report_writer: ShadowReportWriter,
        certification_reader: CertificationReader,
        certification_writer: CertificationWriter,
    ) -> None:
        self._manifest_reader = manifest_reader
        self._manifest_writer = manifest_writer
        self._shadow_report_reader = shadow_report_reader
        self._shadow_report_writer = shadow_report_writer
        self._certification_reader = certification_reader
        self._certification_writer = certification_writer

    def save_manifest(self, record: CompatibilityManifestRecord) -> None:
        """Persist a compatibility manifest record."""
        self._manifest_writer.write_manifest(record)

    def get_manifest(
        self,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord | None:
        """Read a compatibility manifest record."""
        return self._manifest_reader.read_manifest(derived_id, version)

    def save_shadow_report(
        self,
        report: ShadowDiffReportRecord,
        traces: tuple[ShadowTraceRecordRecord, ...],
    ) -> None:
        """Persist a shadow diff report and its traces."""
        self._shadow_report_writer.write_report(report, traces)

    def get_shadow_report(
        self,
        derived_id: str,
        report_id: str,
    ) -> ShadowDiffReportRecord | None:
        """Read a shadow diff report by report id."""
        return self._shadow_report_reader.read_report(derived_id, report_id)

    def list_shadow_traces(
        self,
        derived_id: str,
        report_id: str,
    ) -> list[ShadowTraceRecordRecord]:
        """List trace records for a shadow diff report."""
        return self._shadow_report_reader.list_trace_records(derived_id, report_id)

    def get_latest_shadow_report(
        self,
        derived_id: str,
        candidate_version: int,
        baseline_version: int,
    ) -> ShadowDiffReportRecord | None:
        """Return the latest shadow diff report for a candidate/baseline pair."""
        return self._shadow_report_reader.get_latest_report(
            derived_id, candidate_version, baseline_version
        )

    def save_certification_report(self, record: CertificationReportRecord) -> None:
        """Persist a certification report record."""
        self._certification_writer.write_report(record)

    def get_certification_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
        report_id: str,
    ) -> CertificationReportRecord | None:
        """Read a certification report by report id."""
        return self._certification_reader.read_report(
            derived_id, version, stage, report_id
        )

    def get_latest_certification_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
    ) -> CertificationReportRecord | None:
        """Return the latest certification report for a version/stage."""
        return self._certification_reader.get_latest_report(derived_id, version, stage)
