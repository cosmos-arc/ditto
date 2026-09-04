"""Application boundary for append-only reviewed data-product licenses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from ditto_data.catalog.license import (
    DatasetLicenseDraft,
    DatasetLicenseRecord,
    DatasetLicenseWriter,
)
from ditto_data.catalog.metadata import default_dataset_metadata

from ditto_application.exceptions import AppCommandError

__all__ = [
    "DataProductLicenseCommands",
    "DataProductLicensePermission",
    "ReviewDataProductLicense",
]

type DataProductLicensePermission = Literal["allowed", "restricted", "prohibited"]


@dataclass(frozen=True, slots=True)
class ReviewDataProductLicense:
    """Exact human-reviewed provider terms for one independent product."""

    dataset_id: str
    source: str
    terms_version: str
    effective_from: date
    effective_to: date | None
    local_cache: DataProductLicensePermission
    derivative_compute: DataProductLicensePermission
    display: DataProductLicensePermission
    redistribution: DataProductLicensePermission
    notes: str
    reviewed_by: str
    reviewed_at: datetime


class DataProductLicenseCommands:
    """Validate product/provider identity and append immutable review facts."""

    def __init__(self, writer: DatasetLicenseWriter) -> None:
        self._writer = writer

    def review(self, command: ReviewDataProductLicense) -> DatasetLicenseRecord:
        """Append a deterministic record only for a declared product source."""
        metadata = default_dataset_metadata().get(command.dataset_id)
        contract = metadata.dataset_spec if metadata is not None else None
        if contract is None:
            raise AppCommandError(
                f"Unknown data product: {command.dataset_id}",
                command="review_data_product_license",
                dataset_id=command.dataset_id,
            )
        declared_sources = {
            provider_dataset.partition(":")[0]
            for provider_dataset in contract.provider_datasets
        }
        if command.source not in declared_sources:
            raise AppCommandError(
                "license source is not declared by the data-product contract",
                command="review_data_product_license",
                dataset_id=command.dataset_id,
                source=command.source,
            )
        record = DatasetLicenseRecord.create(
            DatasetLicenseDraft(
                dataset_id=command.dataset_id,
                source=command.source,
                terms_version=command.terms_version,
                effective_from=command.effective_from,
                effective_to=command.effective_to,
                local_cache=command.local_cache,
                derivative_compute=command.derivative_compute,
                display=command.display,
                redistribution=command.redistribution,
                notes=command.notes,
                reviewed_by=command.reviewed_by,
                reviewed_at=command.reviewed_at,
            )
        )
        self._writer.append_license(record)
        return record
