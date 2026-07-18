"""External API models for the R2 data-products workbench."""

from __future__ import annotations

from datetime import date, datetime

from ditto_application.queries.data_products import (
    DataProductCheckView,
    DataProductCoverageView,
    DataProductEvidenceView,
    DataProductLicenseView,
    DataProductOverview,
    DataProductQualityView,
    DataProductRunView,
)
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DataProductCheckResponse",
    "DataProductCoverageResponse",
    "DataProductEvidenceResponse",
    "DataProductLicenseResponse",
    "DataProductOverviewResponse",
    "DataProductQualityResponse",
    "DataProductRunResponse",
    "to_data_product_coverage",
    "to_data_product_evidence",
    "to_data_product_license",
    "to_data_product_overview",
    "to_data_product_quality",
    "to_data_product_run",
]


class DataProductOverviewResponse(BaseModel):
    """Static product contract plus active certification identity."""

    dataset_id: str = Field(description="Canonical dataset identifier")
    r2_scope: str = Field(description="R2 scope classification")
    maturity: str = Field(description="Effective catalog maturity")
    schedule: str = Field(description="Expected partition schedule")
    owner: str = Field(description="Accountable data-product owner")
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


def to_data_product_overview(value: DataProductOverview) -> DataProductOverviewResponse:
    """Map the application overview projection to the public API model."""
    return DataProductOverviewResponse(
        dataset_id=value.dataset_id,
        r2_scope=value.r2_scope,
        maturity=value.maturity,
        schedule=value.schedule,
        owner=value.owner,
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
