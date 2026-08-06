"""Shared safety boundary for destructive R2 data-product operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ditto_data.catalog.metadata import default_dataset_metadata

from ditto_application.exceptions import AppCommandError

__all__ = [
    "DataProductOperation",
    "DataProductOperationPreview",
    "confirm_data_product_operation",
    "preview_data_product_operation",
]

type DataProductOperation = Literal[
    "bootstrap",
    "repair",
    "license",
    "build-certification",
    "certify",
    "promotion",
    "revoke",
]

_EFFECTS: dict[DataProductOperation, tuple[str, ...]] = {
    "bootstrap": (
        "write source and canonical partitions for the requested range",
        "append ingestion, lineage, snapshot, and catalog evidence",
    ),
    "repair": (
        "detect and rewrite missing or failed partitions",
        "append recovery evidence without deleting prior evidence",
    ),
    "license": (
        "append one immutable human review of provider usage rights",
        "make only the reviewed product and source eligible for evidence ingestion",
    ),
    "build-certification": (
        "measure the durable coverage, snapshot, license, PIT, DQ, and lifecycle chain",
        "append one immutable machine report for independent human review",
    ),
    "certify": (
        "append a human approval to an immutable certification report",
        "make the report eligible for readiness checks",
    ),
    "promotion": (
        "append reviewer evidence for one declared promotion criterion",
        "promote dataset maturity when every criterion is satisfied",
    ),
    "revoke": (
        "append a certification revocation event",
        "remove the report from active readiness without deleting history",
    ),
}


@dataclass(frozen=True, slots=True)
class DataProductOperationPreview:
    """Side-effect-free impact statement and exact confirmation token."""

    operation: DataProductOperation
    dataset_id: str
    mode: Literal["preview"]
    effects: tuple[str, ...]
    confirmation_phrase: str


def preview_data_product_operation(
    operation: DataProductOperation,
    dataset_id: str,
) -> DataProductOperationPreview:
    """Validate the target and return the canonical safety preview."""
    metadata = default_dataset_metadata().get(dataset_id)
    if metadata is None or metadata.product_contract is None:
        raise AppCommandError(
            f"Unknown data product: {dataset_id}",
            command=f"preview_data_product_{operation}",
            dataset_id=dataset_id,
        )
    return DataProductOperationPreview(
        operation=operation,
        dataset_id=dataset_id,
        mode="preview",
        effects=_EFFECTS[operation],
        confirmation_phrase=f"data-product:{operation}:{dataset_id}:confirm",
    )


def confirm_data_product_operation(
    preview: DataProductOperationPreview,
    confirmation: str | None,
) -> None:
    """Fail closed unless the operator repeats the exact preview phrase."""
    if confirmation != preview.confirmation_phrase:
        raise AppCommandError(
            "confirmation does not match preview",
            command=f"confirm_data_product_{preview.operation}",
            dataset_id=preview.dataset_id,
        )
