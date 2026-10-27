"""Dataset registry unit tests."""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.dataset_registry import (
    DailyFetchContext,
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

    def test_workstation_context_products_have_real_source_defined_routes(self) -> None:
        registry = default_dataset_registry()

        expected = {
            Dataset.GLOBAL_INDEX_DAILY: WriteKind.GLOBAL_INDEX_BARS,
            Dataset.INDUSTRY_CLASSIFICATION: WriteKind.INDUSTRY_CLASSIFICATION,
            Dataset.INDUSTRY_MAPPING: WriteKind.INDUSTRY_MAPPING,
        }
        for dataset, write_kind in expected.items():
            registration = registry.require(dataset)
            assert registration.date_schedule is DateScheduleType.SOURCE_DEFINED
            assert registration.daily_fetch_factory is not None
            assert registration.write_kind is write_kind


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
            Dataset.GLOBAL_INDEX_DAILY,
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
            Dataset.INDEX_WEIGHT,
            Dataset.INDUSTRY_CLASSIFICATION,
            Dataset.INDUSTRY_MAPPING,
        }

        for dataset in date_fetchable:
            assert registry.require(dataset).daily_fetch_factory is not None

    def test_index_weight_has_a_daily_fetch_and_write_route(self) -> None:
        registration = default_dataset_registry().require(Dataset.INDEX_WEIGHT)

        assert registration.daily_fetch_factory is not None
        assert registration.instrument_fetch_factory is not None
        assert registration.write_kind is WriteKind.INDEX_WEIGHT

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

    def test_dividend_uses_natural_days_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.DIVIDEND)

        assert registration.date_schedule is DateScheduleType.NATURAL_DAYS

    def test_corporate_actions_uses_natural_days_schedule(self) -> None:
        registration = default_dataset_registry().require(Dataset.CORPORATE_ACTIONS)

        assert registration.date_schedule is DateScheduleType.NATURAL_DAYS

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

    def test_calendar_declares_its_real_daily_fetch_interval(self) -> None:
        registration = default_dataset_registry().require(Dataset.CALENDAR)

        assert registration.request_bounds is not None
        assert registration.request_bounds("2026-09-25") == (
            "2026-01-01",
            "2027-01-31",
        )


@pytest.mark.unit
class TestIndexWeightUniverse:
    """index_weight 端点服务宇宙（#196 全宇宙探针收窄）."""

    def test_universe_alias_applies_and_excludes_sw(self) -> None:
        from ditto_application.processes.ingestion.dataset_registry import (
            INDEX_WEIGHT_UNIVERSE,
            MARKET_INDEX_CODES,
            STYLE_INDEX_CODES,
        )

        # 000985 权重端点仅认 .CSI 后缀（实测 .SH 0 行、.CSI 5121 行）
        assert "000985.CSI" in INDEX_WEIGHT_UNIVERSE
        assert "000985.SH" not in INDEX_WEIGHT_UNIVERSE
        # SW 行业指数无权重数据（156/178 空响应），不进宇宙
        assert not any(code.endswith(".SI") for code in INDEX_WEIGHT_UNIVERSE)
        assert len(INDEX_WEIGHT_UNIVERSE) == len(MARKET_INDEX_CODES) + len(
            STYLE_INDEX_CODES
        )

    def test_daily_fetch_iterates_weight_universe_not_cached_codes(self) -> None:
        from unittest.mock import MagicMock

        from ditto_application.processes.ingestion.dataset_registry import (
            INDEX_WEIGHT_UNIVERSE,
        )
        from ditto_application.processes.ingestion.types import SourceFetchers

        capital = MagicMock()
        registration = default_dataset_registry().require(Dataset.INDEX_WEIGHT)
        assert registration.daily_fetch_factory is not None
        context = DailyFetchContext(
            fetchers=SourceFetchers(
                metadata=MagicMock(),
                market=MagicMock(),
                fundamental=MagicMock(),
                capital=capital,
                macro=MagicMock(),
            ),
            trade_date="2026-09-30",
            fetch_commodity_daily=MagicMock(),
            get_cached_index_codes=MagicMock(return_value=["801010.SI"]),
        )

        registration.daily_fetch_factory(context)()

        requested = [call.args[0] for call in capital.fetch_index_weight.call_args_list]
        assert requested == list(INDEX_WEIGHT_UNIVERSE)
        context.get_cached_index_codes.assert_not_called()

    def test_global_index_daily_fetches_lookback_window(self) -> None:
        """全球指数按回看窗口拉取（美/欧股 T+1 凌晨才收盘，单日恒缺）."""
        from unittest.mock import MagicMock

        from ditto_application.processes.ingestion.types import SourceFetchers

        market = MagicMock()
        registration = default_dataset_registry().require(Dataset.GLOBAL_INDEX_DAILY)
        assert registration.daily_fetch_factory is not None
        context = DailyFetchContext(
            fetchers=SourceFetchers(
                metadata=MagicMock(),
                market=market,
                fundamental=MagicMock(),
                capital=MagicMock(),
                macro=MagicMock(),
            ),
            trade_date="2026-09-30",
            fetch_commodity_daily=MagicMock(),
            get_cached_index_codes=MagicMock(return_value=[]),
        )

        registration.daily_fetch_factory(context)()

        market.fetch_global_index_daily.assert_called_once()
        codes, start, end = market.fetch_global_index_daily.call_args.args
        assert start == "2026-09-23"
        assert end == "2026-09-30"
        assert codes  # 21 码篮子非空

    def test_name_history_fetches_lookback_window(self) -> None:
        """namechange 事件流按回看窗口拉取（全量翻页经代理确定性损坏）."""
        from unittest.mock import MagicMock

        from ditto_application.processes.ingestion.types import SourceFetchers

        market = MagicMock()
        registration = default_dataset_registry().require(Dataset.NAME_CHANGE)
        assert registration.daily_fetch_factory is not None
        context = DailyFetchContext(
            fetchers=SourceFetchers(
                metadata=MagicMock(),
                market=market,
                fundamental=MagicMock(),
                capital=MagicMock(),
                macro=MagicMock(),
            ),
            trade_date="2026-09-30",
            fetch_commodity_daily=MagicMock(),
            get_cached_index_codes=MagicMock(return_value=[]),
        )

        registration.daily_fetch_factory(context)()

        market.fetch_name_history.assert_called_once_with(
            start_date="2026-08-16", end_date="2026-09-30"
        )

    def test_fund_portfolio_fetches_market_wide_single_request(self) -> None:
        """fund_portfolio 日更=市场级单请求（逐标的 1,864 循环超时且烧配额）."""
        from unittest.mock import MagicMock

        from ditto_application.processes.ingestion.types import SourceFetchers

        fundamental = MagicMock()
        registration = default_dataset_registry().require(Dataset.FUND_PORTFOLIO)
        assert registration.daily_fetch_factory is not None
        context = DailyFetchContext(
            fetchers=SourceFetchers(
                metadata=MagicMock(),
                market=MagicMock(),
                fundamental=fundamental,
                capital=MagicMock(),
                macro=MagicMock(),
            ),
            trade_date="2026-09-30",
            fetch_commodity_daily=MagicMock(),
            get_cached_index_codes=MagicMock(return_value=[]),
        )

        registration.daily_fetch_factory(context)()

        fundamental.fetch_fund_portfolio.assert_called_once_with(
            trade_date="2026-09-30"
        )
