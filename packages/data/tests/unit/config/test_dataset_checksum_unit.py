"""Tests for deterministic dataset checksum ordering."""

import pytest
from ditto_data.config.dataset_checksum import dataset_sort_keys


@pytest.mark.unit
def test_workstation_context_datasets_use_catalog_primary_keys() -> None:
    """New PIT products must not silently fall back to input row order."""
    assert dataset_sort_keys("global_index_daily") == (
        "source_ticker",
        "trade_date",
        "knowledge_date",
    )
    assert dataset_sort_keys("industry_classification") == (
        "source",
        "classification_version",
        "industry_id",
        "knowledge_date",
    )
    assert dataset_sort_keys("industry_mapping") == (
        "source",
        "classification_version",
        "instrument_id",
        "industry_id",
        "industry_date",
        "knowledge_date",
    )
