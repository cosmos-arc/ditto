"""Fail-closed R2 provider, license, contract, and performance preflight."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.product_contract import DatasetProductContract

from ditto_application.exceptions import AppProcessError

__all__ = [
    "R2_ACCEPTANCE_CERTIFICATION_PROFILE",
    "ChunkBenchmark",
    "PerformanceGateReport",
    "ProductCertificationEvidence",
    "ProductPreflightReport",
    "ProviderAccessEvidence",
    "R2AcceptanceRuntimeEvidence",
    "R2IngestionPreflight",
    "R2PreflightEvidence",
    "R2PreflightReport",
]

type R2PreflightStatus = Literal[
    "ready",
    "configuration_blocked",
    "performance_blocked",
]

_EXPECTED_CONTRACT_COUNT = 19
_REPRESENTATIVE_DATASETS = frozenset(
    {"stock_daily", "index_daily", "adj_factor", "fund_adj"}
)
_BOOTSTRAP_LIMIT_SECONDS = 24 * 60 * 60
_INCREMENTAL_LIMIT_SECONDS = 30 * 60
_WORKBENCH_QUERY_LIMIT_SECONDS = 5.0
_SHA256_HEX_LENGTH = 64
R2_ACCEPTANCE_CERTIFICATION_PROFILE = "r2-modern-a-share-v1"


@dataclass(frozen=True, slots=True)
class R2AcceptanceRuntimeEvidence:
    """Registry-resolved credentials and reviewed licenses without secret values."""

    credential_sources: frozenset[str]
    license_records: tuple[DatasetLicenseRecord, ...]
    certifications: tuple[ProductCertificationEvidence, ...]


@dataclass(frozen=True, slots=True)
class ProductCertificationEvidence:
    """Projection of one independently approved active certification report."""

    dataset_id: str
    profile: str
    report_id: str
    content_hash: str
    certified_from: date
    certified_through: date

    def __post_init__(self) -> None:
        """Reject ambiguous certification projections before gate evaluation."""
        for field_name in ("dataset_id", "profile", "report_id"):
            value = getattr(self, field_name)
            if not value or value.strip() != value:
                raise AppProcessError(
                    f"invalid product certification {field_name}: {value!r}"
                )
        if len(self.content_hash) != _SHA256_HEX_LENGTH or any(
            character not in "0123456789abcdef" for character in self.content_hash
        ):
            raise AppProcessError("product certification content_hash must be SHA-256")
        if self.certified_through < self.certified_from:
            raise AppProcessError("certification interval is reversed")


@dataclass(frozen=True, slots=True)
class ProviderAccessEvidence:
    """Non-secret result of one provider endpoint entitlement probe."""

    provider_dataset: str
    credential_configured: bool
    entitled: bool
    evidence_uri: str
    checked_at: datetime

    def __post_init__(self) -> None:
        """Reject ambiguous or unauditable access observations."""
        if ":" not in self.provider_dataset:
            raise AppProcessError("provider_dataset must use source:dataset form")
        if not self.evidence_uri.strip():
            raise AppProcessError("provider access evidence_uri cannot be blank")
        if self.checked_at.tzinfo is None:
            raise AppProcessError("provider access checked_at must be timezone-aware")
        if self.entitled and not self.credential_configured:
            raise AppProcessError("entitled access requires configured credentials")


@dataclass(frozen=True, slots=True)
class ChunkBenchmark:
    """Measured representative chunk and target-size extrapolation input."""

    dataset_id: str
    sample_partitions: int
    sample_rows: int
    elapsed_seconds: float
    target_partitions: int
    observed_at: datetime
    evidence_uri: str

    def __post_init__(self) -> None:
        """Require a positive, addressable benchmark sample."""
        if self.dataset_id not in _REPRESENTATIVE_DATASETS:
            raise AppProcessError(
                f"unsupported representative dataset: {self.dataset_id}"
            )
        if self.sample_partitions <= 0 or self.target_partitions <= 0:
            raise AppProcessError("benchmark partition counts must be positive")
        if self.sample_rows <= 0 or self.elapsed_seconds <= 0:
            raise AppProcessError("benchmark rows and elapsed time must be positive")
        if self.observed_at.tzinfo is None:
            raise AppProcessError("benchmark observed_at must be timezone-aware")
        if not self.evidence_uri.strip():
            raise AppProcessError("benchmark evidence_uri cannot be blank")

    @property
    def projected_seconds(self) -> float:
        """Linearly extrapolate the measured chunk to its declared target."""
        return self.elapsed_seconds / self.sample_partitions * self.target_partitions


@dataclass(frozen=True, slots=True)
class R2PreflightEvidence:
    """Complete provider, legal, certification, and performance gate input."""

    provider_access: tuple[ProviderAccessEvidence, ...]
    license_records: tuple[DatasetLicenseRecord, ...]
    certifications: tuple[ProductCertificationEvidence, ...]
    benchmarks: tuple[ChunkBenchmark, ...]
    incremental_elapsed_seconds: float | None
    workbench_query_seconds: float | None
    as_of: date
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ProductPreflightReport:
    """Access and reviewed-license result for one independent data product."""

    dataset_id: str
    provider_datasets: tuple[str, ...]
    usable_provider_datasets: tuple[str, ...]
    license_record_ids: tuple[str, ...]
    certification_profile: str
    certification_report_id: str | None
    certification_content_hash: str | None
    certified_from: date | None
    certified_through: date | None
    ready: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PerformanceGateReport:
    """Extrapolated bootstrap and observed incremental/query release gates."""

    representative_datasets: tuple[str, ...]
    projected_bootstrap_seconds: float | None
    bootstrap_limit_seconds: float
    bootstrap_passed: bool
    incremental_elapsed_seconds: float | None
    incremental_limit_seconds: float
    incremental_passed: bool
    workbench_query_seconds: float | None
    workbench_query_limit_seconds: float
    workbench_query_passed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class R2PreflightReport:
    """Complete release preflight without credential or secret material."""

    status: R2PreflightStatus
    checked_at: datetime
    contract_count: int
    products: tuple[ProductPreflightReport, ...]
    performance: PerformanceGateReport
    reason_codes: tuple[str, ...]


class R2IngestionPreflight:
    """Evaluate frozen scope, provider access, license, and performance evidence."""

    def run_fixture(self, *, checked_at: datetime) -> R2PreflightReport:
        """Run the deterministic 19-product acceptance fixture."""
        contracts = _hard_contracts()
        access = tuple(
            ProviderAccessEvidence(
                provider_dataset=contract.provider_datasets[0],
                credential_configured=True,
                entitled=True,
                evidence_uri=f"evidence://fixture/access/{contract.dataset_id}",
                checked_at=checked_at,
            )
            for contract in contracts
        )
        licenses = tuple(
            _fixture_license(
                contract.dataset_id,
                contract.provider_datasets[0],
                checked_at,
            )
            for contract in contracts
        )
        certifications = tuple(
            _fixture_certification(contract, checked_at) for contract in contracts
        )
        benchmarks = tuple(
            ChunkBenchmark(
                dataset_id=dataset_id,
                sample_partitions=20,
                sample_rows=100_000,
                elapsed_seconds=60.0,
                target_partitions=3_000,
                observed_at=checked_at,
                evidence_uri=f"evidence://fixture/benchmark/{dataset_id}",
            )
            for dataset_id in _REPRESENTATIVE_DATASETS
        )
        return self.run(
            R2PreflightEvidence(
                provider_access=access,
                license_records=licenses,
                certifications=certifications,
                benchmarks=benchmarks,
                incremental_elapsed_seconds=120.0,
                workbench_query_seconds=0.4,
                as_of=checked_at.date(),
                checked_at=checked_at,
            )
        )

    def run(self, evidence: R2PreflightEvidence) -> R2PreflightReport:
        """Return ready only after every declared release gate is proven."""
        provider_access = evidence.provider_access
        license_records = evidence.license_records
        certifications = evidence.certifications
        benchmarks = evidence.benchmarks
        incremental_elapsed_seconds = evidence.incremental_elapsed_seconds
        workbench_query_seconds = evidence.workbench_query_seconds
        as_of = evidence.as_of
        checked_at = evidence.checked_at
        if checked_at.tzinfo is None:
            raise AppProcessError("preflight checked_at must be timezone-aware")
        contracts = _hard_contracts()
        access_by_dataset = _access_by_provider_dataset(provider_access)
        certification_by_dataset = _certification_by_dataset(certifications)
        products = tuple(
            _evaluate_product(
                contract,
                access_by_dataset=access_by_dataset,
                license_records=license_records,
                certification=certification_by_dataset.get(contract.dataset_id),
                as_of=as_of,
            )
            for contract in contracts
        )
        configuration_reasons: list[str] = []
        if len(contracts) != _EXPECTED_CONTRACT_COUNT:
            configuration_reasons.append("contract_count_mismatch")
        for product in products:
            configuration_reasons.extend(product.reason_codes)

        performance = _performance_report(
            benchmarks,
            incremental_elapsed_seconds=incremental_elapsed_seconds,
            workbench_query_seconds=workbench_query_seconds,
        )
        missing_performance = "performance_evidence_missing" in (
            performance.reason_codes
        )
        if missing_performance:
            configuration_reasons.append("performance_evidence_missing")

        if configuration_reasons:
            status: R2PreflightStatus = "configuration_blocked"
            reasons = _unique(configuration_reasons)
        elif performance.reason_codes:
            status = "performance_blocked"
            reasons = performance.reason_codes
        else:
            status = "ready"
            reasons = ()
        return R2PreflightReport(
            status=status,
            checked_at=checked_at,
            contract_count=len(contracts),
            products=products,
            performance=performance,
            reason_codes=reasons,
        )


def _hard_contracts() -> tuple[DatasetProductContract, ...]:
    return tuple(
        metadata.product_contract
        for metadata in default_dataset_metadata().values()
        if metadata.product_contract is not None
        and metadata.product_contract.r2_scope == "hard"
    )


def _fixture_license(
    dataset_id: str,
    provider_dataset: str,
    checked_at: datetime,
) -> DatasetLicenseRecord:
    return DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id=dataset_id,
            source=provider_dataset.partition(":")[0],
            terms_version="fixture-v1",
            effective_from=checked_at.date(),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="restricted",
            redistribution="prohibited",
            notes="Deterministic acceptance fixture review.",
            reviewed_by="fixture-reviewer",
            reviewed_at=checked_at,
        )
    )


def _fixture_certification(
    contract: DatasetProductContract,
    checked_at: datetime,
) -> ProductCertificationEvidence:
    required_from = _required_certified_from(contract) or checked_at.date()
    return ProductCertificationEvidence(
        dataset_id=contract.dataset_id,
        profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
        report_id=f"certification:{contract.dataset_id}:fixture",
        content_hash=hashlib.sha256(contract.dataset_id.encode()).hexdigest(),
        certified_from=required_from,
        certified_through=max(required_from, checked_at.date()),
    )


def _access_by_provider_dataset(
    values: tuple[ProviderAccessEvidence, ...],
) -> dict[str, ProviderAccessEvidence]:
    result: dict[str, ProviderAccessEvidence] = {}
    for value in values:
        if value.provider_dataset in result:
            raise AppProcessError(
                f"duplicate provider access evidence: {value.provider_dataset}"
            )
        result[value.provider_dataset] = value
    return result


def _certification_by_dataset(
    values: tuple[ProductCertificationEvidence, ...],
) -> dict[str, ProductCertificationEvidence]:
    result: dict[str, ProductCertificationEvidence] = {}
    for value in values:
        if value.dataset_id in result:
            raise AppProcessError(
                f"duplicate active product certification: {value.dataset_id}"
            )
        result[value.dataset_id] = value
    return result


def _required_certified_from(contract: DatasetProductContract) -> date | None:
    for value in (contract.certified_target_from, contract.raw_target_from):
        if value is None:
            continue
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return None


def _evaluate_product(
    contract: DatasetProductContract,
    *,
    access_by_dataset: dict[str, ProviderAccessEvidence],
    license_records: tuple[DatasetLicenseRecord, ...],
    certification: ProductCertificationEvidence | None,
    as_of: date,
) -> ProductPreflightReport:
    observed = tuple(
        access_by_dataset[item]
        for item in contract.provider_datasets
        if item in access_by_dataset
    )
    usable = tuple(
        item.provider_dataset
        for item in observed
        if item.credential_configured and item.entitled
    )
    usable_sources = {item.partition(":")[0] for item in usable}
    licenses = tuple(
        record
        for record in license_records
        if record.dataset_id == contract.dataset_id
        and record.source in usable_sources
        and _license_allows_r2(record, as_of)
    )
    reasons: list[str] = []
    if not observed:
        reasons.append("entitlement_unverified")
    if any(not item.credential_configured for item in observed):
        reasons.append("credential_missing")
    if observed and not usable:
        reasons.append("entitlement_denied")
    if usable and not licenses:
        reasons.append("license_missing")
    required_certified_from = _required_certified_from(contract)
    if (
        certification is None
        or certification.profile != R2_ACCEPTANCE_CERTIFICATION_PROFILE
    ):
        reasons.append("certification_missing")
    elif (
        required_certified_from is not None
        and certification.certified_from > required_certified_from
    ):
        reasons.append("certified_history_target_unmet")
    return ProductPreflightReport(
        dataset_id=contract.dataset_id,
        provider_datasets=contract.provider_datasets,
        usable_provider_datasets=usable,
        license_record_ids=tuple(record.record_id for record in licenses),
        certification_profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
        certification_report_id=(
            certification.report_id if certification is not None else None
        ),
        certification_content_hash=(
            certification.content_hash if certification is not None else None
        ),
        certified_from=(
            certification.certified_from if certification is not None else None
        ),
        certified_through=(
            certification.certified_through if certification is not None else None
        ),
        ready=not reasons,
        reason_codes=tuple(reasons),
    )


def _license_allows_r2(record: DatasetLicenseRecord, as_of: date) -> bool:
    return (
        record.effective_from <= as_of
        and (record.effective_to is None or as_of <= record.effective_to)
        and record.local_cache == "allowed"
        and record.derivative_compute == "allowed"
    )


def _performance_report(
    benchmarks: tuple[ChunkBenchmark, ...],
    *,
    incremental_elapsed_seconds: float | None,
    workbench_query_seconds: float | None,
) -> PerformanceGateReport:
    by_dataset = {benchmark.dataset_id: benchmark for benchmark in benchmarks}
    if len(by_dataset) != len(benchmarks):
        raise AppProcessError("duplicate representative benchmark dataset")
    complete = frozenset(by_dataset) == _REPRESENTATIVE_DATASETS
    projected = (
        sum(item.projected_seconds for item in by_dataset.values())
        if complete
        else None
    )
    bootstrap_passed = projected is not None and projected <= _BOOTSTRAP_LIMIT_SECONDS
    incremental_passed = (
        incremental_elapsed_seconds is not None
        and 0 <= incremental_elapsed_seconds <= _INCREMENTAL_LIMIT_SECONDS
    )
    query_passed = (
        workbench_query_seconds is not None
        and 0 <= workbench_query_seconds <= _WORKBENCH_QUERY_LIMIT_SECONDS
    )
    reasons: list[str] = []
    if (
        projected is None
        or incremental_elapsed_seconds is None
        or (workbench_query_seconds is None)
    ):
        reasons.append("performance_evidence_missing")
    else:
        if not bootstrap_passed:
            reasons.append("bootstrap_over_24h")
        if not incremental_passed:
            reasons.append("incremental_over_30m")
        if not query_passed:
            reasons.append("workbench_query_over_5s")
    return PerformanceGateReport(
        representative_datasets=tuple(sorted(by_dataset)),
        projected_bootstrap_seconds=projected,
        bootstrap_limit_seconds=float(_BOOTSTRAP_LIMIT_SECONDS),
        bootstrap_passed=bootstrap_passed,
        incremental_elapsed_seconds=incremental_elapsed_seconds,
        incremental_limit_seconds=float(_INCREMENTAL_LIMIT_SECONDS),
        incremental_passed=incremental_passed,
        workbench_query_seconds=workbench_query_seconds,
        workbench_query_limit_seconds=_WORKBENCH_QUERY_LIMIT_SECONDS,
        workbench_query_passed=query_passed,
        reason_codes=tuple(reasons),
    )


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
