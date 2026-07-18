"""R2 certification, maturity, PIT, snapshot, and partition readiness query."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader

from ditto_application.catalog_maturity import blocked_catalog_datasets
from ditto_application.exceptions import AppQueryError

__all__ = [
    "R2_P0_DATASETS",
    "R2_P1_DATASETS",
    "DataReadinessQueryFacade",
    "DataReadinessReport",
    "DatasetReadinessAssessment",
    "DatasetReadinessRequirement",
    "PartitionHealth",
]

type ReadinessStatus = Literal["ready", "blocked"]
type PartitionHealthStatus = Literal[
    "ready",
    "blocked",
    "missing",
    "stale",
    "dq_failed",
    "unknown",
]
type R2Bundle = Literal["market_core", "fundamental_macro"]

R2_P0_DATASETS: tuple[str, ...] = (
    "calendar",
    "stock_basic",
    "etf_basic",
    "index_basic",
    "stock_daily",
    "etf_daily",
    "index_daily",
    "adj_factor",
    "fund_adj",
    "stock_status",
    "index_weight",
    "corporate_actions",
)

R2_P1_DATASETS: tuple[str, ...] = (
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    "valuation_metrics",
    "macro_indicators",
    "commodity_daily",
)


@dataclass(frozen=True, slots=True)
class DatasetReadinessRequirement:
    """Exact certified interval and evidence required by one consumer."""

    dataset_id: str
    required_from: date
    required_to: date
    expected_snapshot_ids: tuple[str, ...] = ()
    requires_pit_universe: bool = False

    def __post_init__(self) -> None:
        """Validate the consumer interval and snapshot set."""
        if not self.dataset_id or self.dataset_id.strip() != self.dataset_id:
            raise AppQueryError(f"invalid readiness dataset_id: {self.dataset_id!r}")
        if self.required_to < self.required_from:
            raise AppQueryError("readiness required_to precedes required_from")
        if len(set(self.expected_snapshot_ids)) != len(self.expected_snapshot_ids):
            raise AppQueryError("readiness expected snapshot IDs must be unique")


@dataclass(frozen=True, slots=True)
class PartitionHealth:
    """Current canonical partition health supplied by the runtime host."""

    status: PartitionHealthStatus
    snapshot_id: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetReadinessAssessment:
    """Fail-closed readiness outcome for one required dataset."""

    dataset_id: str
    required_from: date
    required_to: date
    status: ReadinessStatus
    certification_report_id: str | None
    snapshot_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataReadinessReport:
    """Aggregate readiness that never replaces independent dataset evidence."""

    profile: str
    status: ReadinessStatus
    datasets: tuple[DatasetReadinessAssessment, ...]
    bundle: str | None = None


class DataReadinessQueryFacade:
    """Assess exact consumer intervals against approved R2 evidence."""

    def __init__(
        self,
        certification_reader: CertificationReader,
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
    ) -> None:
        self._certification_reader = certification_reader
        self._maturity_promotion_reader = maturity_promotion_reader

    def assess(
        self,
        *,
        profile: str,
        requirements: tuple[DatasetReadinessRequirement, ...],
        partition_health: Mapping[str, PartitionHealth] | None = None,
        bundle: str | None = None,
    ) -> DataReadinessReport:
        """Assess datasets independently, then aggregate without masking failures."""
        health_by_dataset = partition_health or {}
        assessments = tuple(
            self._assess_dataset(
                requirement,
                profile=profile,
                partition_health=health_by_dataset.get(requirement.dataset_id),
            )
            for requirement in requirements
        )
        return DataReadinessReport(
            profile=profile,
            status=(
                "ready"
                if assessments and all(item.status == "ready" for item in assessments)
                else "blocked"
            ),
            datasets=assessments,
            bundle=bundle,
        )

    def assess_bundle(
        self,
        bundle: R2Bundle,
        *,
        profile: str,
        required_from: date,
        required_to: date,
        partition_health: Mapping[str, PartitionHealth] | None = None,
    ) -> DataReadinessReport:
        """Assess the named P0/P1 aggregate while preserving per-product reasons."""
        if bundle not in {"market_core", "fundamental_macro"}:
            raise AppQueryError(f"unknown R2 readiness bundle: {bundle}")
        dataset_ids = R2_P0_DATASETS if bundle == "market_core" else R2_P1_DATASETS
        requirements = tuple(
            DatasetReadinessRequirement(
                dataset_id=dataset_id,
                required_from=required_from,
                required_to=required_to,
            )
            for dataset_id in dataset_ids
        )
        return self.assess(
            profile=profile,
            requirements=requirements,
            partition_health=partition_health,
            bundle=bundle,
        )

    def _assess_dataset(
        self,
        requirement: DatasetReadinessRequirement,
        *,
        profile: str,
        partition_health: PartitionHealth | None,
    ) -> DatasetReadinessAssessment:
        reasons: list[str] = []
        if blocked_catalog_datasets(
            (requirement.dataset_id,),
            maturity_promotion_reader=self._maturity_promotion_reader,
        ):
            reasons.append("DATASET_MATURITY_BLOCKED")

        report = self._certification_reader.get_active_report(
            requirement.dataset_id,
            profile,
        )
        snapshot_ids: tuple[str, ...] = ()
        report_id: str | None = None
        if report is None:
            reasons.append("CERTIFICATION_MISSING")
        else:
            report_id = report.report_id
            snapshot_ids = report.evidence.snapshot_ids
            coverage = report.coverage
            if (
                coverage.complete_from is None
                or requirement.required_from < coverage.complete_from
                or requirement.required_to > coverage.target_to
                or coverage.unapproved_gaps
            ):
                reasons.append("CERTIFIED_INTERVAL_MISSING")
            if requirement.requires_pit_universe and not any(
                check.passed and "universe" in check.name.lower()
                for check in report.evidence.pit_replay_results
            ):
                reasons.append("PIT_UNIVERSE_UNRESOLVED")
            if requirement.expected_snapshot_ids and not set(
                requirement.expected_snapshot_ids
            ).issubset(snapshot_ids):
                reasons.append("SOURCE_SNAPSHOT_MISMATCH")

        if partition_health is not None and partition_health.status != "ready":
            reasons.append(f"PARTITION_HEALTH_{partition_health.status.upper()}")
        return DatasetReadinessAssessment(
            dataset_id=requirement.dataset_id,
            required_from=requirement.required_from,
            required_to=requirement.required_to,
            status="blocked" if reasons else "ready",
            certification_report_id=report_id,
            snapshot_ids=snapshot_ids,
            reason_codes=tuple(reasons),
        )
