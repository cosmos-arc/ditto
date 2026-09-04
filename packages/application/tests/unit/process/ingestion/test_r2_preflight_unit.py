"""Unit contract for the R2 provider and performance preflight."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from ditto_application.processes.ingestion.r2_preflight import (
    R2_ACCEPTANCE_CERTIFICATION_PROFILE,
    ChunkBenchmark,
    ProductCertificationEvidence,
    ProviderAccessEvidence,
    R2IngestionPreflight,
    R2PreflightEvidence,
)
from ditto_data.catalog.license import (
    DatasetLicenseDraft,
    DatasetLicenseRecord,
)
from ditto_data.catalog.metadata import default_dataset_metadata

CHECKED_AT = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
AS_OF = date(2026, 7, 18)
REPRESENTATIVE_DATASETS = (
    "stock_daily",
    "index_daily",
    "adj_factor",
    "fund_adj",
)


def _hard_contracts():
    return tuple(
        metadata.dataset_spec
        for metadata in default_dataset_metadata().values()
        if metadata.dataset_spec is not None
        and metadata.dataset_spec.r2_scope == "hard"
    )


def _access() -> tuple[ProviderAccessEvidence, ...]:
    return tuple(
        ProviderAccessEvidence(
            provider_dataset=contract.provider_datasets[0],
            credential_configured=True,
            entitled=True,
            evidence_uri=(f"evidence://provider-access/{contract.dataset_id}/fixture"),
            checked_at=CHECKED_AT,
        )
        for contract in _hard_contracts()
    )


def _licenses() -> tuple[DatasetLicenseRecord, ...]:
    records = []
    for contract in _hard_contracts():
        source = contract.provider_datasets[0].partition(":")[0]
        records.append(
            DatasetLicenseRecord.create(
                DatasetLicenseDraft(
                    dataset_id=contract.dataset_id,
                    source=source,
                    terms_version="fixture-v1",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    local_cache="allowed",
                    derivative_compute="allowed",
                    display="restricted",
                    redistribution="prohibited",
                    notes="R2 deterministic fixture review.",
                    reviewed_by="fixture-reviewer",
                    reviewed_at=CHECKED_AT,
                )
            )
        )
    return tuple(records)


def _certifications() -> tuple[ProductCertificationEvidence, ...]:
    return tuple(
        ProductCertificationEvidence(
            dataset_id=contract.dataset_id,
            profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
            report_id=f"certification:{contract.dataset_id}:fixture",
            content_hash="a" * 64,
            certified_from=date(2010, 1, 1),
            certified_through=AS_OF,
        )
        for contract in _hard_contracts()
    )


def _benchmarks(
    *,
    elapsed_seconds: float = 60.0,
) -> tuple[ChunkBenchmark, ...]:
    return tuple(
        ChunkBenchmark(
            dataset_id=dataset_id,
            sample_partitions=20,
            sample_rows=100_000,
            elapsed_seconds=elapsed_seconds,
            target_partitions=3_000,
            observed_at=CHECKED_AT,
            evidence_uri=f"evidence://benchmark/{dataset_id}/fixture",
        )
        for dataset_id in REPRESENTATIVE_DATASETS
    )


@pytest.mark.unit
def test_ready_requires_22_contracts_access_licenses_and_performance_evidence() -> None:
    report = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=_access(),
            license_records=_licenses(),
            certifications=_certifications(),
            benchmarks=_benchmarks(),
            incremental_elapsed_seconds=120.0,
            workbench_query_seconds=0.4,
            as_of=AS_OF,
            checked_at=CHECKED_AT,
        )
    )

    assert report.status == "ready"
    assert report.contract_count == 22
    assert len(report.products) == 22
    assert all(product.ready for product in report.products)
    assert all(product.certification_report_id for product in report.products)
    assert all(
        product.certified_from <= date(2015, 1, 1) for product in report.products
    )
    assert report.performance.bootstrap_passed is True
    assert report.performance.projected_bootstrap_seconds == 36_000.0
    assert report.performance.incremental_passed is True
    assert report.performance.workbench_query_passed is True


@pytest.mark.unit
def test_missing_credential_is_configuration_blocked_and_never_success() -> None:
    access = list(_access())
    first = access[0]
    access[0] = ProviderAccessEvidence(
        provider_dataset=first.provider_dataset,
        credential_configured=False,
        entitled=False,
        evidence_uri="evidence://provider-access/missing-credential",
        checked_at=CHECKED_AT,
    )

    report = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=tuple(access),
            license_records=_licenses(),
            certifications=_certifications(),
            benchmarks=_benchmarks(),
            incremental_elapsed_seconds=120.0,
            workbench_query_seconds=0.4,
            as_of=AS_OF,
            checked_at=CHECKED_AT,
        )
    )

    assert report.status == "configuration_blocked"
    assert "credential_missing" in report.reason_codes
    assert "token" not in repr(report).casefold()
    assert "secret" not in repr(report).casefold()


@pytest.mark.unit
def test_entitlement_and_license_are_both_fail_closed() -> None:
    access = list(_access())
    target = next(
        item for item in access if item.provider_dataset == "tushare:fund_adj"
    )
    access[access.index(target)] = ProviderAccessEvidence(
        provider_dataset=target.provider_dataset,
        credential_configured=True,
        entitled=False,
        evidence_uri="evidence://provider-access/fund-adj-denied",
        checked_at=CHECKED_AT,
    )
    licenses = tuple(
        record for record in _licenses() if record.dataset_id != "index_weight"
    )

    report = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=tuple(access),
            license_records=licenses,
            certifications=_certifications(),
            benchmarks=_benchmarks(),
            incremental_elapsed_seconds=120.0,
            workbench_query_seconds=0.4,
            as_of=AS_OF,
            checked_at=CHECKED_AT,
        )
    )

    assert report.status == "configuration_blocked"
    product_reasons = {
        product.dataset_id: product.reason_codes for product in report.products
    }
    assert "entitlement_denied" in product_reasons["fund_adj"]
    assert "license_missing" in product_reasons["index_weight"]


@pytest.mark.unit
def test_performance_gate_blocks_slow_bootstrap_incremental_and_query() -> None:
    report = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=_access(),
            license_records=_licenses(),
            certifications=_certifications(),
            benchmarks=_benchmarks(elapsed_seconds=200.0),
            incremental_elapsed_seconds=1_801.0,
            workbench_query_seconds=5.1,
            as_of=AS_OF,
            checked_at=CHECKED_AT,
        )
    )

    assert report.status == "performance_blocked"
    assert report.performance.projected_bootstrap_seconds == 120_000.0
    assert report.performance.bootstrap_passed is False
    assert report.performance.incremental_passed is False
    assert report.performance.workbench_query_passed is False
    assert set(report.reason_codes) == {
        "bootstrap_over_24h",
        "incremental_over_30m",
        "workbench_query_over_5s",
    }


@pytest.mark.unit
def test_missing_or_short_active_certification_is_configuration_blocked() -> None:
    certifications = list(_certifications())
    stock_daily = next(
        item for item in certifications if item.dataset_id == "stock_daily"
    )
    certifications[certifications.index(stock_daily)] = ProductCertificationEvidence(
        dataset_id="stock_daily",
        profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
        report_id="certification:stock_daily:short",
        content_hash="b" * 64,
        certified_from=date(2020, 1, 1),
        certified_through=AS_OF,
    )
    certifications = [
        item for item in certifications if item.dataset_id != "index_weight"
    ]

    report = R2IngestionPreflight().run(
        R2PreflightEvidence(
            provider_access=_access(),
            license_records=_licenses(),
            certifications=tuple(certifications),
            benchmarks=_benchmarks(),
            incremental_elapsed_seconds=120.0,
            workbench_query_seconds=0.4,
            as_of=AS_OF,
            checked_at=CHECKED_AT,
        )
    )

    assert report.status == "configuration_blocked"
    product_reasons = {
        product.dataset_id: product.reason_codes for product in report.products
    }
    assert "certified_history_target_unmet" in product_reasons["stock_daily"]
    assert "certification_missing" in product_reasons["index_weight"]
