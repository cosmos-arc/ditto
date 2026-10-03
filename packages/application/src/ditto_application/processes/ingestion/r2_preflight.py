"""Fail-closed R2 provider access, contract, and performance preflight."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ditto_data.catalog.dataset_spec import DatasetSpec
from ditto_data.catalog.metadata import default_dataset_metadata

from ditto_application.exceptions import AppProcessError

__all__ = [
    "ChunkBenchmark",
    "PerformanceGateReport",
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

_EXPECTED_CONTRACT_COUNT = 22
_REPRESENTATIVE_DATASETS = frozenset(
    {"stock_daily", "index_daily", "adj_factor", "fund_adj"}
)
_BOOTSTRAP_LIMIT_SECONDS = 24 * 60 * 60
_INCREMENTAL_LIMIT_SECONDS = 30 * 60
_WORKBENCH_QUERY_LIMIT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class R2AcceptanceRuntimeEvidence:
    """Registry-resolved credentials without secret values."""

    credential_sources: frozenset[str]


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
    """Complete provider access and performance gate input."""

    provider_access: tuple[ProviderAccessEvidence, ...]
    benchmarks: tuple[ChunkBenchmark, ...]
    incremental_elapsed_seconds: float | None
    workbench_query_seconds: float | None
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ProductPreflightReport:
    """Provider access result for one independent data product."""

    dataset_id: str
    provider_datasets: tuple[str, ...]
    usable_provider_datasets: tuple[str, ...]
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
    """Evaluate frozen scope, provider access, and performance evidence."""

    def run_fixture(self, *, checked_at: datetime) -> R2PreflightReport:
        """Run the deterministic 22-product acceptance fixture."""
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
                benchmarks=benchmarks,
                incremental_elapsed_seconds=120.0,
                workbench_query_seconds=0.4,
                checked_at=checked_at,
            )
        )

    def run(self, evidence: R2PreflightEvidence) -> R2PreflightReport:
        """Return ready only after every declared release gate is proven."""
        provider_access = evidence.provider_access
        benchmarks = evidence.benchmarks
        incremental_elapsed_seconds = evidence.incremental_elapsed_seconds
        workbench_query_seconds = evidence.workbench_query_seconds
        checked_at = evidence.checked_at
        if checked_at.tzinfo is None:
            raise AppProcessError("preflight checked_at must be timezone-aware")
        contracts = _hard_contracts()
        access_by_dataset = _access_by_provider_dataset(provider_access)
        products = tuple(
            _evaluate_product(
                contract,
                access_by_dataset=access_by_dataset,
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


def _hard_contracts() -> tuple[DatasetSpec, ...]:
    return tuple(
        metadata.dataset_spec
        for metadata in default_dataset_metadata().values()
        if metadata.dataset_spec is not None
        and metadata.dataset_spec.r2_scope == "hard"
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


def _evaluate_product(
    contract: DatasetSpec,
    *,
    access_by_dataset: dict[str, ProviderAccessEvidence],
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
    reasons: list[str] = []
    if not observed:
        reasons.append("entitlement_unverified")
    if any(not item.credential_configured for item in observed):
        reasons.append("credential_missing")
    if observed and not usable:
        reasons.append("entitlement_denied")
    return ProductPreflightReport(
        dataset_id=contract.dataset_id,
        provider_datasets=contract.provider_datasets,
        usable_provider_datasets=usable,
        ready=not reasons,
        reason_codes=tuple(reasons),
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
