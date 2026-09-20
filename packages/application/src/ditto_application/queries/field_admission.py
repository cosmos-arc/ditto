"""Read-only field/use admission over existing snapshot and approval ledgers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.field_evidence import CertifiedField
from ditto_data.catalog.license import DatasetLicenseReader, DatasetLicenseRecord
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

from ditto_application.exceptions import AppQueryError

type DataUse = Literal["display", "exploration", "formal_research", "promotion_paper"]
DATA_USES: tuple[DataUse, ...] = (
    "display",
    "exploration",
    "formal_research",
    "promotion_paper",
)


@dataclass(frozen=True, slots=True)
class FieldRequirement:
    """Exact field, snapshot and consumer binding; no client eligibility flags."""

    dataset_id: str
    field: str
    snapshot_id: str
    consumer_field: str = ""


@dataclass(frozen=True, slots=True)
class FieldAdmissionRequest:
    """Scope and temporal identity shared by every requested input field."""

    fields: tuple[FieldRequirement, ...]
    instrument_ids: tuple[int, ...]
    required_from: date
    required_to: date
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    purpose: DataUse
    profile: str = "selection-fields-v1"

    def __post_init__(self) -> None:
        """Fail closed on ambiguous or empty input scopes."""
        if self.required_from > self.required_to:
            raise AppQueryError("field admission interval is reversed")
        if not self.instrument_ids or not self.fields:
            raise AppQueryError("field admission requires fields and instruments")
        if (
            self.knowledge_cutoff.tzinfo is None
            or self.publication_cutoff.tzinfo is None
        ):
            raise AppQueryError("field admission cutoffs must be timezone-aware")
        if self.purpose not in DATA_USES:
            raise AppQueryError("unknown field admission purpose")


@dataclass(frozen=True, slots=True)
class FieldAdmission:
    """Addressed evidence and reasons for one actual consumer dependency."""

    dataset_id: str
    field: str
    snapshot_id: str
    consumer_field: str
    allowed_uses: tuple[DataUse, ...]
    reason_codes: tuple[str, ...]
    license_record_id: str | None
    certification_report_id: str | None
    covered_from: date | None
    covered_to: date | None
    time_precision: str
    evidence_uri: str | None


@dataclass(frozen=True, slots=True)
class FieldAdmissionReport:
    """Data qualification only; strategy validation and approval remain separate."""

    allowed: bool
    purpose: DataUse
    fields: tuple[FieldAdmission, ...]
    rule_version: str = "field-admission-v1"


def _license_reasons(
    license_record: DatasetLicenseRecord | None,
    purpose: DataUse,
    used_on: date,
) -> tuple[str, ...]:
    if license_record is None:
        return ("LICENSE_MISSING",)
    if license_record.effective_from > used_on or (
        license_record.effective_to is not None
        and used_on >= license_record.effective_to
    ):
        return ("LICENSE_INTERVAL_MISSING",)
    permissions = (license_record.local_cache, license_record.display)
    if purpose != "display":
        permissions += (license_record.derivative_compute,)
    return (
        ()
        if all(item == "allowed" for item in permissions)
        else ("LICENSE_RESTRICTED",)
    )


def _field_reasons(
    field: CertifiedField | None,
    requirement: FieldRequirement,
    request: FieldAdmissionRequest,
) -> tuple[str, ...]:
    if field is None:
        return ("FIELD_EVIDENCE_MISSING",)
    reasons: list[str] = []
    if (
        requirement.consumer_field
        and requirement.consumer_field not in field.consumer_fields
    ):
        reasons.append("CONSUMER_BINDING_MISSING")
    if not set(request.instrument_ids).issubset(field.instrument_ids):
        reasons.append("INSTRUMENT_SCOPE_MISSING")
    if (
        request.required_from < field.covered_from
        or request.required_to > field.covered_to
    ):
        reasons.append("FIELD_COVERAGE_MISSING")
    if (
        field.available_at is None
        or field.publication_at is None
        or field.time_precision == "unknown"
    ):
        reasons.append("TIME_EVIDENCE_MISSING")
    elif (
        field.available_at > request.knowledge_cutoff
        or field.publication_at > request.publication_cutoff
    ):
        reasons.append("TIME_NOT_VISIBLE")
    return tuple(reasons)


class FieldAdmissionQuery:
    """Intersect only the requested fields, using durable reviewed evidence."""

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        licenses: DatasetLicenseReader,
        certifications: CertificationReader,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._licenses = licenses
        self._certifications = certifications
        self._now = now or (lambda: datetime.now(UTC))

    def assess(self, request: FieldAdmissionRequest) -> FieldAdmissionReport:
        """Assess exact snapshots without ingestion or certification writes."""
        used_on = self._now().astimezone(ZoneInfo("Asia/Shanghai")).date()
        fields = tuple(
            self._assess_field(item, request, used_on) for item in request.fields
        )
        return FieldAdmissionReport(
            allowed=all(request.purpose in item.allowed_uses for item in fields),
            purpose=request.purpose,
            fields=fields,
        )

    def _assess_field(
        self, item: FieldRequirement, request: FieldAdmissionRequest, used_on: date
    ) -> FieldAdmission:
        snapshot = self._snapshots.get_snapshot(item.snapshot_id)
        report = self._certifications.get_active_report(
            item.dataset_id, request.profile
        )
        reasons: list[str] = []
        field: CertifiedField | None = None
        license_record = None
        if snapshot is None:
            reasons.append("SNAPSHOT_MISSING")
        elif snapshot.dataset_id != item.dataset_id:
            reasons.append("SNAPSHOT_CONFLICT")
        else:
            license_record = self._licenses.get_license(snapshot.license_record_id)
            if license_record is not None and (
                license_record.dataset_id != item.dataset_id
                or license_record.source != snapshot.source
            ):
                license_record = None
            if not snapshot.payload_retained:
                reasons.append("SNAPSHOT_PAYLOAD_MISSING")
            if request.required_from < date.fromisoformat(
                snapshot.request_start
            ) or request.required_to > date.fromisoformat(snapshot.request_end):
                reasons.append("SNAPSHOT_COVERAGE_MISSING")
        if report is None:
            reasons.append("CERTIFICATION_MISSING")
        else:
            if item.snapshot_id not in report.evidence.snapshot_ids:
                reasons.append("SNAPSHOT_CONFLICT")
            if (
                license_record is not None
                and license_record.record_id not in report.evidence.license_record_ids
            ):
                reasons.append("LICENSE_CERTIFICATION_CONFLICT")
            field = next(
                (
                    value
                    for value in report.evidence.certified_fields
                    if value.field == item.field
                    and value.snapshot_id == item.snapshot_id
                ),
                None,
            )
        reasons.extend(_field_reasons(field, item, request))
        allowed: tuple[DataUse, ...] = tuple(
            purpose
            for purpose in DATA_USES
            if not reasons and not _license_reasons(license_record, purpose, used_on)
        )
        return FieldAdmission(
            dataset_id=item.dataset_id,
            field=item.field,
            snapshot_id=item.snapshot_id,
            consumer_field=item.consumer_field,
            allowed_uses=allowed,
            reason_codes=tuple(
                dict.fromkeys(
                    (
                        *reasons,
                        *_license_reasons(license_record, request.purpose, used_on),
                    )
                )
            ),
            license_record_id=license_record.record_id if license_record else None,
            certification_report_id=report.report_id if report else None,
            covered_from=field.covered_from if field else None,
            covered_to=field.covered_to if field else None,
            time_precision=field.time_precision if field else "unknown",
            evidence_uri=field.evidence_uri if field else None,
        )
