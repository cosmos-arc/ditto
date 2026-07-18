"""Dataset registry unit tests."""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    DatasetRegistry,
    WriteKind,
    default_dataset_registry,
)
from ditto_data.catalog import default_dataset_metadata
from ditto_data.models import Dataset, DateScheduleType


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

    def test_duplicate_registration_raises_app_error(self) -> None:
        registry = DatasetRegistry()
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        registry.register(registration)

        with pytest.raises(
            AppProcessError, match="Dataset already registered: stock_daily"
        ):
            registry.register(registration)

    def test_requires_registered_dataset(self) -> None:
        registry = DatasetRegistry()

        with pytest.raises(
            AppProcessError, match="Dataset is not registered: stock_daily"
        ):
            registry.require(Dataset.STOCK_DAILY)

    def test_requires_write_dataset_for_bars(self) -> None:
        with pytest.raises(AppProcessError, match="write_dataset is required"):
            DatasetRegistration(
                dataset=Dataset.STOCK_DAILY,
                write_kind=WriteKind.TRADED_BARS,
            )

    def test_basic_registration_requires_asset_class(self) -> None:
        with pytest.raises(AppProcessError, match="basic_asset_class is required"):
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

    def test_fund_adj_has_a_dedicated_etf_write_route(self) -> None:
        registration = default_dataset_registry().require(Dataset.FUND_ADJ)

        assert registration.write_kind is WriteKind.FUND_ADJ
        assert registration.write_kind is not WriteKind.ADJ_FACTOR


@pytest.mark.unit
class TestDatasetRegistryConformance:
    """Cross-route invariants for default registrations."""

    def test_every_instrument_supported_dataset_has_instrument_factory(self) -> None:
        registry = default_dataset_registry()

        for dataset in registry.supported_instrument_datasets():
            registration = registry.require(dataset)
            assert registration.instrument_fetch_factory is not None

    def test_every_date_fetchable_registration_has_daily_factory(self) -> None:
        registry = default_dataset_registry()
        date_fetchable = {
            Dataset.CALENDAR,
            Dataset.STOCK_BASIC,
            Dataset.ETF_BASIC,
            Dataset.INDEX_BASIC,
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
            Dataset.MACRO_INDICATORS,
            Dataset.CORPORATE_ACTIONS,
            Dataset.FX_DAILY,
            Dataset.COMMODITY_DAILY,
        }

        for dataset in date_fetchable:
            assert registry.require(dataset).daily_fetch_factory is not None

    def test_index_weight_is_registered_but_has_no_runtime_route(self) -> None:
        registration = default_dataset_registry().require(Dataset.INDEX_WEIGHT)

        assert registration.daily_fetch_factory is None
        assert registration.instrument_fetch_factory is None
        assert registration.write_kind is WriteKind.UNSUPPORTED

    def test_registrations_match_catalog_source_capabilities(self) -> None:
        registry = default_dataset_registry()
        metadata = default_dataset_metadata()

        for registration in registry.registrations():
            capability = metadata[registration.dataset.value]

            assert registration.date_schedule.value == capability.schedule
            assert (
                registration.daily_fetch_factory is not None
            ) == capability.supports_date_ingestion
            assert (
                registration.instrument_fetch_factory is not None
            ) == capability.supports_instrument_ingestion


@pytest.mark.unit
class TestDateScheduleField:
    """date_schedule field on DatasetRegistration."""

    def test_default_date_schedule_is_trading_days(self) -> None:
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        assert registration.date_schedule is DateScheduleType.TRADING_DAYS

    def test_stock_daily_has_trading_days_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_DAILY)

        assert registration.date_schedule is DateScheduleType.TRADING_DAYS

    def test_fx_daily_has_natural_days_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.FX_DAILY)

        assert registration.date_schedule is DateScheduleType.NATURAL_DAYS

    def test_commodity_daily_has_source_defined_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.COMMODITY_DAILY)

        assert registration.date_schedule is DateScheduleType.SOURCE_DEFINED

    def test_macro_indicators_has_source_defined_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.MACRO_INDICATORS)

        assert registration.date_schedule is DateScheduleType.SOURCE_DEFINED

    def test_calendar_defaults_to_trading_days(self) -> None:
        registration = default_dataset_registry().require(Dataset.CALENDAR)

        assert registration.date_schedule is DateScheduleType.TRADING_DAYS
