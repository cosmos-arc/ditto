"""Dataset registry unit tests."""

from __future__ import annotations

import pytest
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    DatasetRegistry,
    WriteKind,
)
from ditto_data.models import Dataset


@pytest.mark.unit
class TestDatasetRegistryCore:
    """Registry container behavior."""

    def test_register_and_require_registration(self) -> None:
        registry = DatasetRegistry()
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        registry.register(registration)

        assert registry.require(Dataset.STOCK_DAILY) is registration
        assert list(registry.datasets()) == [Dataset.STOCK_DAILY]

    def test_duplicate_registration_raises_value_error(self) -> None:
        registry = DatasetRegistry()
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        registry.register(registration)

        with pytest.raises(ValueError, match="Dataset already registered: stock_daily"):
            registry.register(registration)

    def test_requires_registered_dataset(self) -> None:
        registry = DatasetRegistry()

        with pytest.raises(KeyError, match="Dataset is not registered: stock_daily"):
            registry.require(Dataset.STOCK_DAILY)

    def test_requires_write_dataset_for_bars(self) -> None:
        with pytest.raises(ValueError, match="write_dataset is required"):
            DatasetRegistration(
                dataset=Dataset.STOCK_DAILY,
                write_kind=WriteKind.TRADED_BARS,
            )

    def test_basic_registration_requires_asset_class(self) -> None:
        with pytest.raises(ValueError, match="basic_asset_class is required"):
            DatasetRegistration(
                dataset=Dataset.STOCK_BASIC,
                write_kind=WriteKind.BASIC,
            )
