"""Source capability policy for ingestion routes."""

from __future__ import annotations

from ditto_data.catalog import default_dataset_metadata
from ditto_data.models import Dataset

from ditto_application.exceptions import AppProcessError

__all__ = ["UnsupportedIngestionSourceError", "ensure_source_supported"]


class UnsupportedIngestionSourceError(AppProcessError):
    """Configured source cannot drive the requested ingestion dataset."""


def ensure_source_supported(dataset: Dataset, source_name: str) -> None:
    """Ensure configured source is allowed to drive this dataset route."""
    metadata = default_dataset_metadata()[dataset.value]
    if metadata.supports_source(source_name):
        return
    raise UnsupportedIngestionSourceError(
        f"Data source '{source_name}' does not support dataset {dataset.value}",
        field="source_name",
        value=source_name,
        dataset=dataset.value,
        supported=list(metadata.supported_sources),
    )
