"""Data-owned field qualification rules, independent of application transports."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from ditto_data.catalog.field_evidence import CertifiedField
from ditto_data.catalog.license import DatasetLicenseRecord

type DataUse = Literal["display", "exploration", "formal_research", "promotion_paper"]
DATA_USES: tuple[DataUse, ...] = (
    "display",
    "exploration",
    "formal_research",
    "promotion_paper",
)


@dataclass(frozen=True, slots=True)
class FieldUsageScope:
    """Actual consumed scope and immutable input binding to qualify."""

    consumer_field: str
    consumer_input_hash: str | None
    instrument_ids: tuple[int, ...]
    required_from: date
    required_to: date
    knowledge_cutoff: datetime
    publication_cutoff: datetime


def license_reasons(
    license_record: DatasetLicenseRecord | None,
    purpose: DataUse,
    used_on: date,
) -> tuple[str, ...]:
    """Evaluate actual-use rights separately from historical data coverage."""
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


def field_reasons(
    field: CertifiedField | None,
    scope: FieldUsageScope,
) -> tuple[str, ...]:
    """Check reviewed scope, exact consumer content and temporal visibility."""
    if field is None:
        return ("FIELD_EVIDENCE_MISSING",)
    reasons: list[str] = []
    if scope.consumer_field and (
        scope.consumer_input_hash is None
        or (scope.consumer_field, scope.consumer_input_hash)
        not in field.consumer_bindings
    ):
        reasons.append("CONSUMER_INPUT_MISMATCH")
    if not set(scope.instrument_ids).issubset(field.instrument_ids):
        reasons.append("INSTRUMENT_SCOPE_MISSING")
    if scope.required_from < field.covered_from or scope.required_to > field.covered_to:
        reasons.append("FIELD_COVERAGE_MISSING")
    if (
        field.available_at is None
        or field.publication_at is None
        or field.observed_at is None
        or field.time_precision == "unknown"
    ):
        reasons.append("TIME_EVIDENCE_MISSING")
    elif field.time_precision == "date" and (
        field.date_visible_at is None
        or not field.calendar_hash
        or not field.calendar_evidence
    ):
        reasons.append("CALENDAR_EVIDENCE_MISSING")
    else:
        publication, available = _visibility_bounds(
            field.publication_at, field.available_at, field
        )
        if available > scope.knowledge_cutoff or publication > scope.publication_cutoff:
            reasons.append("TIME_NOT_VISIBLE")
    return tuple(reasons)


def _visibility_bounds(
    publication: datetime,
    available: datetime,
    field: CertifiedField,
) -> tuple[datetime, datetime]:
    """Lower-bound publication and knowledge visibility by every known fact."""
    for constraint in (field.date_visible_at, field.revised_at):
        if constraint is not None:
            publication = max(publication, constraint)
            available = max(available, constraint)
    if field.observed_at is not None:
        available = max(available, field.observed_at)
    return publication, available
