"""Read-only five-category specimen summaries with reference re-verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.catalog.specimen import (
    SPECIMEN_CATEGORIES,
    DataSpecimen,
    SpecimenCategory,
    SpecimenReader,
)

__all__ = [
    "SPECIMEN_RULE_VERSION",
    "DataSpecimenQuery",
    "SpecimenCategorySummary",
    "SpecimenProcurementView",
    "SpecimenSourceView",
    "SpecimenView",
]

SPECIMEN_RULE_VERSION = "data-specimen-v1"


@dataclass(frozen=True)
class SpecimenSourceView:
    """Transport-safe projection of one collected specimen source."""

    source: str
    provider_snapshot_id: str | None
    upstream_group: str | None


@dataclass(frozen=True)
class SpecimenProcurementView:
    """Transport-safe projection of one procurement track."""

    option: str
    quote_status: str
    notes: str | None


@dataclass(frozen=True)
class SpecimenView:
    """Transport-safe projection of one adjudicated specimen record."""

    specimen_id: str
    category: str
    dataset_id: str
    anchor: str
    sources: tuple[SpecimenSourceView, ...]
    upstream_independent: bool
    convention_alignment: str
    coverage_from: date | None
    coverage_to: date | None
    knowable_from: datetime | None
    time_precision: str
    as_of_counterexample: str | None
    license_record_ids: tuple[str, ...]
    gaps: tuple[str, ...]
    allowed_uses: tuple[str, ...]
    verification_status: str
    procurement: tuple[SpecimenProcurementView, ...]
    adjudicated_by: str | None
    adjudicated_at: datetime | None
    evidence_uri: str | None


@dataclass(frozen=True)
class SpecimenCategorySummary:
    """One category's adjudication history and its unresolved gaps."""

    category: SpecimenCategory
    specimens: tuple[SpecimenView, ...]
    unresolved_gaps: tuple[str, ...]

    @property
    def latest(self) -> SpecimenView | None:
        """Newest adjudication, or None when the category has no specimen."""
        return self.specimens[0] if self.specimens else None

    @property
    def collected(self) -> bool:
        """False means the category is explicitly unverified, not passed."""
        return bool(self.specimens)


class DataSpecimenQuery:
    """Read specimen evidence only; adjudication happens out of band."""

    def __init__(
        self,
        specimens: SpecimenReader,
        snapshots: ProviderSnapshotReader,
        licenses: DatasetLicenseReader,
    ) -> None:
        self._specimens = specimens
        self._snapshots = snapshots
        self._licenses = licenses

    def summarize(self) -> tuple[SpecimenCategorySummary, ...]:
        """Return every category; missing ones stay explicitly unverified."""
        summaries: list[SpecimenCategorySummary] = []
        for category in SPECIMEN_CATEGORIES:
            records = self._specimens.list_specimens(category=category)
            specimens = tuple(_view(record) for record in records)
            unresolved = (
                self._unresolved_gaps(records)
                if records
                else ("SPECIMEN_NOT_COLLECTED",)
            )
            summaries.append(
                SpecimenCategorySummary(
                    category=category,
                    specimens=specimens,
                    unresolved_gaps=unresolved,
                )
            )
        return tuple(summaries)

    def _unresolved_gaps(self, records: tuple[DataSpecimen, ...]) -> tuple[str, ...]:
        latest = records[0]
        gaps = list(latest.gaps)
        for item in latest.sources:
            if (
                item.provider_snapshot_id is not None
                and self._snapshots.get_snapshot(item.provider_snapshot_id) is None
            ):
                gaps.append("SPECIMEN_SOURCE_SNAPSHOT_MISSING")
        for record_id in latest.license_record_ids:
            if self._licenses.get_license(record_id) is None:
                gaps.append("SPECIMEN_LICENSE_MISSING")
        return tuple(dict.fromkeys(gaps))


def _view(record: DataSpecimen) -> SpecimenView:
    return SpecimenView(
        specimen_id=record.specimen_id,
        category=record.category,
        dataset_id=record.dataset_id,
        anchor=record.anchor,
        sources=tuple(
            SpecimenSourceView(
                source=item.source,
                provider_snapshot_id=item.provider_snapshot_id,
                upstream_group=item.upstream_group,
            )
            for item in record.sources
        ),
        upstream_independent=record.upstream_independent,
        convention_alignment=record.convention_alignment,
        coverage_from=record.coverage_from,
        coverage_to=record.coverage_to,
        knowable_from=record.knowable_from,
        time_precision=record.time_precision,
        as_of_counterexample=record.as_of_counterexample,
        license_record_ids=record.license_record_ids,
        gaps=record.gaps,
        allowed_uses=record.allowed_uses,
        verification_status=record.verification_status,
        procurement=tuple(
            SpecimenProcurementView(
                option=item.option,
                quote_status=item.quote_status,
                notes=item.notes,
            )
            for item in record.procurement
        ),
        adjudicated_by=record.adjudicated_by,
        adjudicated_at=record.adjudicated_at,
        evidence_uri=record.evidence_uri,
    )
