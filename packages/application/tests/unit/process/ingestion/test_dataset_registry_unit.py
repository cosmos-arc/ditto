"""Dataset registry unit tests."""

from __future__ import annotations

import pytest
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    DatasetRegistry,
    WriteKind,
    default_dataset_registry,
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


@pytest.mark.unit
class TestDefaultDatasetRegistry:
    """Default route coverage."""

    def test_registers_every_dataset_enum_value(self) -> None:
        registry = default_dataset_registry()

        assert set(registry.datasets()) == set(Dataset)

    def test_stock_daily_route_declares_fetch_and_write_metadata(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_DAILY)

        assert registration.write_kind is WriteKind.TRADED_BARS
        assert registration.write_dataset == "stock_daily"
        assert registration.daily_fetch_factory is not None
        assert registration.instrument_fetch_factory is not None
        assert registration.supports_instrument_ingestion is True
        assert registration.requires_year_partition is True

    def test_calendar_route_is_metadata_without_year_partition(self) -> None:
        registration = default_dataset_registry().require(Dataset.CALENDAR)

        assert registration.write_kind is WriteKind.CALENDAR
        assert registration.metadata_dataset is True
        assert registration.requires_year_partition is False

    def test_stock_basic_route_declares_basic_asset_class(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_BASIC)

        assert registration.write_kind is WriteKind.BASIC
        assert registration.basic_asset_class == "stock"
        assert registration.metadata_dataset is True

    def test_stock_status_is_not_instrument_supported(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_STATUS)

        assert registration.daily_fetch_factory is not None
        assert registration.instrument_fetch_factory is None
        assert registration.supports_instrument_ingestion is False
