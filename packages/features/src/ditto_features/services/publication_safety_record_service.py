"""Publication safety runtime record service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_features.publication_safety_records import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)


class ManifestReaderProtocol(Protocol):
    """Reader port for compatibility manifests."""

    def read_manifest(
        self,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord | None:
        """Read a compatibility manifest."""
        ...


class ManifestWriterProtocol(Protocol):
    """Writer port for compatibility manifests."""

    def write_manifest(self, record: CompatibilityManifestRecord) -> None:
        """Write a compatibility manifest."""
        ...


class MinimalDQReaderProtocol(Protocol):
    """Reader port for minimal DQ summaries."""

    def read_summary(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Read a minimal DQ summary."""
        ...

    def get_latest_summary(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedMinimalDQSummaryRecord | None:
        """Read the latest minimal DQ summary."""
        ...


class MinimalDQWriterProtocol(Protocol):
    """Writer port for minimal DQ summaries."""

    def write_summary(self, record: DerivedMinimalDQSummaryRecord) -> None:
        """Write a minimal DQ summary."""
        ...


class ShadowReportReaderProtocol(Protocol):
    """Reader port for shadow diff and trace records."""

    def read_report(
        self,
        derived_id: str,
        report_id: str,
    ) -> ShadowDiffReportRecord | None:
        """Read a shadow diff report."""
        ...

    def list_trace_records(
        self,
        derived_id: str,
        report_id: str,
    ) -> list[ShadowTraceRecordRecord]:
        """List trace records for a shadow diff report."""
        ...

    def get_latest_report(
        self,
        derived_id: str,
        candidate_version: int,
        baseline_version: int,
    ) -> ShadowDiffReportRecord | None:
        """Read the latest shadow diff report."""
        ...


class ShadowReportWriterProtocol(Protocol):
    """Writer port for shadow diff and trace records."""

    def write_report(
        self,
        report: ShadowDiffReportRecord,
        traces: tuple[ShadowTraceRecordRecord, ...],
    ) -> None:
        """Write a shadow diff report and its traces."""
        ...


class CertificationReaderProtocol(Protocol):
    """Reader port for certification reports."""

    def read_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
        report_id: str,
    ) -> CertificationReportRecord | None:
        """Read a certification report."""
        ...

    def get_latest_report(
        self,
        derived_id: str,
        version: int,
        stage: str,
    ) -> CertificationReportRecord | None:
        """Read the latest certification report."""
        ...


class CertificationWriterProtocol(Protocol):
    """Writer port for certification reports."""

    def write_report(self, record: CertificationReportRecord) -> None:
        """Write a certification report."""
        ...


@dataclass(frozen=True)
class PublicationSafetyRuntimeStores:
    """Reader/writer bundle for publication safety runtime records."""

    manifest_reader: ManifestReaderProtocol
    manifest_writer: ManifestWriterProtocol
    minimal_dq_reader: MinimalDQReaderProtocol
    minimal_dq_writer: MinimalDQWriterProtocol
    shadow_report_reader: ShadowReportReaderProtocol
    shadow_report_writer: ShadowReportWriterProtocol
    certification_reader: CertificationReaderProtocol
    certification_writer: CertificationWriterProtocol


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
