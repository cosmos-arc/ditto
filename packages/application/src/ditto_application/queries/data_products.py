"""Read models for independently certified R2 data products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.metadata import default_dataset_metadata

__all__ = [
    "DataProductCoverageView",
    "DataProductOverview",
    "DataProductsQueryFacade",
]


@dataclass(frozen=True, slots=True)
class DataProductOverview:
    """One product contract and its currently approved report identity."""

    dataset_id: str
    r2_scope: str
    maturity: str
    schedule: str
    owner: str
    raw_target_from: str | None
    certified_target_from: str | None
    active_certification_report_id: str | None


@dataclass(frozen=True, slots=True)
class DataProductCoverageView:
    """Operational coverage milestones for one product and profile."""

    dataset_id: str
    profile: str
    raw_from: date | None
    complete_from: date | None
    certified_from: date | None
    expected_partitions: int
    actual_partitions: int
    gaps: tuple[date, ...]
    unapproved_gaps: tuple[date, ...]


class DataProductsQueryFacade:
    """Expose R2 product status without coupling product certifications together."""

    def __init__(self, certification_reader: CertificationReader) -> None:
        self._certification_reader = certification_reader

    def list_products(self, *, profile: str) -> tuple[DataProductOverview, ...]:
        """List the 19 hard-scope products with independent active reports."""
        products: list[DataProductOverview] = []
        for metadata in default_dataset_metadata().values():
            contract = metadata.product_contract
            if contract is None or contract.r2_scope != "hard":
                continue
            active = self._certification_reader.get_active_report(
                metadata.dataset_id,
                profile,
            )
            products.append(
                DataProductOverview(
                    dataset_id=metadata.dataset_id,
                    r2_scope=contract.r2_scope,
                    maturity=metadata.maturity,
                    schedule=metadata.schedule,
                    owner=contract.owner,
                    raw_target_from=contract.raw_target_from,
                    certified_target_from=contract.certified_target_from,
                    active_certification_report_id=getattr(
                        active,
                        "report_id",
                        None,
                    ),
                )
            )
        return tuple(products)

    def coverage_view(
        self,
        coverage: DatasetCoverage,
        *,
        profile: str,
    ) -> DataProductCoverageView:
        """Join current machine coverage with an independently approved report."""
        active = self._certification_reader.get_active_report(
            coverage.dataset_id,
            profile,
        )
        return DataProductCoverageView(
            dataset_id=coverage.dataset_id,
            profile=profile,
            raw_from=coverage.raw_from,
            complete_from=coverage.complete_from,
            certified_from=(
                active.coverage.complete_from if active is not None else None
            ),
            expected_partitions=coverage.expected_partitions,
            actual_partitions=coverage.actual_partitions,
            gaps=coverage.gaps,
            unapproved_gaps=coverage.unapproved_gaps,
        )
