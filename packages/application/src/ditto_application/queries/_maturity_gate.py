"""Shared maturity gate for application query facades."""

from __future__ import annotations

from collections.abc import Iterable

from ditto_data.catalog.promotion import DatasetMaturityPromotionReader

from ditto_application.catalog_maturity import blocked_catalog_datasets
from ditto_application.exceptions import AppQueryError

__all__ = ["assert_query_datasets_allowed"]


def assert_query_datasets_allowed(
    dataset_ids: Iterable[str],
    *,
    allow_experimental_data: bool,
    maturity_promotion_reader: DatasetMaturityPromotionReader | None,
    context: str,
) -> None:
    """Fail closed when a query path would read non-initial-focus datasets."""
    blocked = blocked_catalog_datasets(
        dataset_ids,
        allow_experimental_data=allow_experimental_data,
        maturity_promotion_reader=maturity_promotion_reader,
    )
    if not blocked:
        return
    joined = ", ".join(blocked)
    msg = (
        f"{context} requires experimental dataset or other non-initial-focus "
        f"dataset maturity: {joined}. Set allow_experimental_data=True only "
        f"for explicit research use."
    )
    raise AppQueryError(msg)
