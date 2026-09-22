"""External API models for the R2 data-products workbench."""

from __future__ import annotations

from datetime import date, datetime

from ditto_application.queries.data_products import (
    DataProductCheckView,
    DataProductCoverageView,
    DataProductEvidenceView,
    DataProductLicenseView,
    DataProductQualityView,
    DataProductRunView,
    DataProductView,
)
from ditto_application.queries.data_specimen import (
    SpecimenCategorySummary,
    SpecimenProcurementView,
    SpecimenSourceView,
    SpecimenView,
)
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DataProductCheckResponse",
    "DataProductCoverageResponse",
    "DataProductEvidenceResponse",
    "DataProductLicenseResponse",
    "DataProductQualityResponse",
    "DataProductRunResponse",
    "DataProductViewResponse",
    "DataSpecimenCategoryResponse",
    "DataSpecimenProcurementResponse",
    "DataSpecimenResponse",
    "DataSpecimenSourceResponse",
    "to_data_product_coverage",
    "to_data_product_evidence",
    "to_data_product_license",
    "to_data_product_quality",
    "to_data_product_run",
    "to_data_product_view",
    "to_specimen_category",
]


class DataProductViewResponse(BaseModel):
    """Static dataset spec plus active certification identity."""

    dataset_id: str = Field(description="Canonical dataset identifier")
    r2_scope: str = Field(description="R2 scope classification")
    maturity: str = Field(description="Effective catalog maturity")
    schedule: str = Field(description="Expected partition schedule")
    owner: str = Field(description="Accountable data-product owner")
    schema_version: str = Field(description="Canonical dataset schema version")
    frequency: str = Field(description="Expected observation frequency")
    timezone: str = Field(description="Canonical dataset timezone")
    currency: str | None = Field(description="Canonical or mixed dataset currency")
    raw_target_from: str | None = Field(description="Raw history target")
    certified_target_from: str | None = Field(description="Certification target")
    active_certification_report_id: str | None = Field(
        description="Currently approved immutable report"
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductCoverageResponse(BaseModel):
    """Coverage milestones and current partition gaps."""

    dataset_id: str
    profile: str
    raw_from: date | None
    complete_from: date | None
    certified_from: date | None
    expected_partitions: int = Field(ge=0)
    actual_partitions: int = Field(ge=0)
    gaps: list[date]
    unapproved_gaps: list[date]

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductCheckResponse(BaseModel):
    """One evidence check with an addressable artifact."""

    name: str
    evidence_uri: str
    passed: bool

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductQualityResponse(BaseModel):
    """Quality, PIT, freshness, recovery, and consumer evidence."""

    dataset_id: str
    profile: str
    report_id: str
    dq_rule_version: str
    dq_results: list[DataProductCheckResponse]
    pit_replay_results: list[DataProductCheckResponse]
    freshness_results: list[DataProductCheckResponse]
    recovery_results: list[DataProductCheckResponse]
    consumer_results: list[DataProductCheckResponse]

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductRunResponse(BaseModel):
    """Immutable certification generation and review projection."""

    dataset_id: str
    profile: str
    report_id: str
    generated_at: datetime
    content_hash: str
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductEvidenceResponse(BaseModel):
    """Source, schema, snapshot, fallback, and override evidence."""

    dataset_id: str
    profile: str
    report_id: str
    content_hash: str
    source_ids: list[str]
    schema_versions: list[str]
    snapshot_ids: list[str]
    fallback_history: list[str]
    override_history: list[str]

    model_config = ConfigDict(strict=True, extra="ignore")


class DataProductLicenseResponse(BaseModel):
    """Reviewed license identities bound to a certification."""

    dataset_id: str
    profile: str
    report_id: str
    license_record_ids: list[str]

    model_config = ConfigDict(strict=True, extra="ignore")


class DataSpecimenSourceResponse(BaseModel):
    """One provider's collected original for the specimen anchor."""

    source: str
    provider_snapshot_id: str | None
    upstream_group: str | None

    model_config = ConfigDict(strict=True, extra="ignore")


class DataSpecimenProcurementResponse(BaseModel):
    """One procurement track; unknown quotes stay unknown."""

    option: str = Field(description="in_budget or professional track")
    quote_status: str = Field(description="unknown until a real quote is recorded")
    notes: str | None

    model_config = ConfigDict(strict=True, extra="ignore")


class DataSpecimenResponse(BaseModel):
    """One adjudicated five-category specimen evidence pack."""

    specimen_id: str
    category: str
    dataset_id: str
    anchor: str = Field(description="Concrete security/event sample identifier")
    sources: list[DataSpecimenSourceResponse]
    upstream_independent: bool
    convention_alignment: str
    coverage_from: date | None
    coverage_to: date | None
    knowable_from: datetime | None
    time_precision: str
    as_of_counterexample: str | None
    license_record_ids: list[str]
    gaps: list[str]
    allowed_uses: list[str]
    verification_status: str
    procurement: list[DataSpecimenProcurementResponse]
    adjudicated_by: str | None
    adjudicated_at: datetime | None
    evidence_uri: str | None

    model_config = ConfigDict(strict=True, extra="ignore")


class DataSpecimenCategoryResponse(BaseModel):
    """One category's conclusion; missing stays explicitly unverified."""

    category: str
    collected: bool
    unresolved_gaps: list[str]
    latest: DataSpecimenResponse | None

    model_config = ConfigDict(strict=True, extra="ignore")


def to_data_product_view(value: DataProductView) -> DataProductViewResponse:
    """Map the application dataset projection to the public API model."""
    return DataProductViewResponse(
        dataset_id=value.dataset_id,
        r2_scope=value.r2_scope,
        maturity=value.maturity,
        schedule=value.schedule,
        owner=value.owner,
        schema_version=value.schema_version,
        frequency=value.frequency,
        timezone=value.timezone,
        currency=value.currency,
        raw_target_from=value.raw_target_from,
        certified_target_from=value.certified_target_from,
        active_certification_report_id=value.active_certification_report_id,
    )


def to_data_product_coverage(
    value: DataProductCoverageView,
) -> DataProductCoverageResponse:
    """Map the application coverage projection to the public API model."""
    return DataProductCoverageResponse(
        dataset_id=value.dataset_id,
        profile=value.profile,
        raw_from=value.raw_from,
        complete_from=value.complete_from,
        certified_from=value.certified_from,
        expected_partitions=value.expected_partitions,
        actual_partitions=value.actual_partitions,
        gaps=list(value.gaps),
        unapproved_gaps=list(value.unapproved_gaps),
    )


def _checks(values: tuple[DataProductCheckView, ...]) -> list[DataProductCheckResponse]:
    return [
        DataProductCheckResponse(
            name=value.name,
            evidence_uri=value.evidence_uri,
            passed=value.passed,
        )
        for value in values
    ]


def to_data_product_quality(
    value: DataProductQualityView,
) -> DataProductQualityResponse:
    """Map application quality evidence to the public API model."""
    return DataProductQualityResponse(
        dataset_id=value.dataset_id,
        profile=value.profile,
        report_id=value.report_id,
        dq_rule_version=value.dq_rule_version,
        dq_results=_checks(value.dq_results),
        pit_replay_results=_checks(value.pit_replay_results),
        freshness_results=_checks(value.freshness_results),
        recovery_results=_checks(value.recovery_results),
        consumer_results=_checks(value.consumer_results),
    )


def to_data_product_run(value: DataProductRunView) -> DataProductRunResponse:
    """Map one immutable application run projection to the API model."""
    return DataProductRunResponse(
        dataset_id=value.dataset_id,
        profile=value.profile,
        report_id=value.report_id,
        generated_at=value.generated_at,
        content_hash=value.content_hash,
        status=value.status,
        reviewed_by=value.reviewed_by,
        reviewed_at=value.reviewed_at,
        revocation_reason=value.revocation_reason,
    )


def to_data_product_evidence(
    value: DataProductEvidenceView,
) -> DataProductEvidenceResponse:
    """Map application provider evidence to the public API model."""
    return DataProductEvidenceResponse(
        dataset_id=value.dataset_id,
        profile=value.profile,
        report_id=value.report_id,
        content_hash=value.content_hash,
        source_ids=list(value.source_ids),
        schema_versions=list(value.schema_versions),
        snapshot_ids=list(value.snapshot_ids),
        fallback_history=list(value.fallback_history),
        override_history=list(value.override_history),
    )


def to_data_product_license(
    value: DataProductLicenseView,
) -> DataProductLicenseResponse:
    """Map application license bindings to the public API model."""
    return DataProductLicenseResponse(
        dataset_id=value.dataset_id,
        profile=value.profile,
        report_id=value.report_id,
        license_record_ids=list(value.license_record_ids),
    )


def _specimen_source(value: SpecimenSourceView) -> DataSpecimenSourceResponse:
    return DataSpecimenSourceResponse(
        source=value.source,
        provider_snapshot_id=value.provider_snapshot_id,
        upstream_group=value.upstream_group,
    )


def _specimen_procurement(
    value: SpecimenProcurementView,
) -> DataSpecimenProcurementResponse:
    return DataSpecimenProcurementResponse(
        option=value.option,
        quote_status=value.quote_status,
        notes=value.notes,
    )


def _specimen(value: SpecimenView) -> DataSpecimenResponse:
    return DataSpecimenResponse(
        specimen_id=value.specimen_id,
        category=value.category,
        dataset_id=value.dataset_id,
        anchor=value.anchor,
        sources=[_specimen_source(item) for item in value.sources],
        upstream_independent=value.upstream_independent,
        convention_alignment=value.convention_alignment,
        coverage_from=value.coverage_from,
        coverage_to=value.coverage_to,
        knowable_from=value.knowable_from,
        time_precision=value.time_precision,
        as_of_counterexample=value.as_of_counterexample,
        license_record_ids=list(value.license_record_ids),
        gaps=list(value.gaps),
        allowed_uses=list(value.allowed_uses),
        verification_status=value.verification_status,
        procurement=[_specimen_procurement(item) for item in value.procurement],
        adjudicated_by=value.adjudicated_by,
        adjudicated_at=value.adjudicated_at,
        evidence_uri=value.evidence_uri,
    )


def to_specimen_category(
    summary: SpecimenCategorySummary,
) -> DataSpecimenCategoryResponse:
    """Map one category summary to the public API model."""
    return DataSpecimenCategoryResponse(
        category=summary.category,
        collected=summary.collected,
        unresolved_gaps=list(summary.unresolved_gaps),
        latest=_specimen(summary.latest) if summary.latest is not None else None,
    )
