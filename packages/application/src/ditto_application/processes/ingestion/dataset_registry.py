"""Dataset registry for application ingestion routing."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Literal

import polars as pl
from ditto_data.catalog import default_dataset_metadata
from ditto_data.models import FX_CODE_TO_INSTRUMENT_ID, Dataset, DateScheduleType
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.exceptions import AppProcessError  # noqa: RUF100
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "DailyFetchContext",
    "DailyFetchFactory",
    "DailyFetchHandler",
    "DatasetRegistration",
    "DatasetRegistry",
    "InstrumentFetchContext",
    "InstrumentFetchFactory",
    "InstrumentFetchHandler",
    "WriteKind",
    "default_dataset_registry",
]


@dataclass(frozen=True)
class DailyFetchContext:
    """Runtime inputs for date-level fetch handlers."""

    fetchers: SourceFetchers
    trade_date: str
    fetch_commodity_daily: Callable[[str], pl.DataFrame]
    get_cached_index_codes: Callable[[], list[str]]


@dataclass(frozen=True)
class InstrumentFetchContext:
    """Runtime inputs for instrument-level fetch handlers."""

    fetchers: SourceFetchers
    source_ticker: str
    params: InstrumentIngestParams


DailyFetchHandler = Callable[[], pl.DataFrame]
DailyFetchFactory = Callable[[DailyFetchContext], DailyFetchHandler]
InstrumentFetchHandler = Callable[[], pl.DataFrame]
InstrumentFetchFactory = Callable[[InstrumentFetchContext], InstrumentFetchHandler]


class WriteKind(StrEnum):
    """Supported ingestion writer routes."""

    UNSUPPORTED = "unsupported"
    TRADED_BARS = "traded_bars"
    INSTRUMENT_CODE_BARS = "instrument_code_bars"
    STOCK_STATUS = "stock_status"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"
    FUNDAMENTAL = "fundamental"
    CAPITAL = "capital"
    MACRO = "macro"
    CALENDAR = "calendar"
    BASIC = "basic"


@dataclass(frozen=True)
class DatasetRegistration:
    """Operational route metadata for one Dataset value."""

    dataset: Dataset
    write_kind: WriteKind
    date_schedule: DateScheduleType = DateScheduleType.TRADING_DAYS
    write_dataset: str | None = None
    daily_fetch_factory: DailyFetchFactory | None = None
    instrument_fetch_factory: InstrumentFetchFactory | None = None
    metadata_dataset: bool = False
    basic_asset_class: Literal["stock", "etf", "index"] | None = None

    def __post_init__(self) -> None:
        """Validate registration consistency."""
        if (
            self.write_kind
            in {
                WriteKind.TRADED_BARS,
                WriteKind.INSTRUMENT_CODE_BARS,
            }
            and self.write_dataset is None
        ):
            raise AppProcessError(
                f"write_dataset is required for {self.write_kind.value}",
                field="write_kind",
                value=self.write_kind.value,
            )
        if self.write_kind == WriteKind.BASIC and self.basic_asset_class is None:
            raise AppProcessError(
                "basic_asset_class is required for basic datasets",
                field="basic_asset_class",
                value=None,
            )

    @property
    def supports_instrument_ingestion(self) -> bool:
        """Return whether this dataset has an instrument-level fetch route."""
        return self.instrument_fetch_factory is not None

    @property
    def requires_year_partition(self) -> bool:
        """Return whether write routing needs a year from trade_date."""
        return not self.metadata_dataset


class DatasetRegistry:
    """Mutable registry used to declare ingestion routing once."""

    def __init__(
        self,
        registrations: tuple[DatasetRegistration, ...] = (),
    ) -> None:
        self._registrations: dict[Dataset, DatasetRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: DatasetRegistration) -> None:
        """Register one dataset route."""
        if registration.dataset in self._registrations:
            raise AppProcessError(
                f"Dataset already registered: {registration.dataset.value}",
                field="dataset",
                value=registration.dataset.value,
            )
        self._registrations[registration.dataset] = registration

    def validate_catalog_capabilities(self) -> None:
        """Validate all registered routes against data-owned catalog capabilities."""
        for registration in self._registrations.values():
            _validate_catalog_capability(registration)

    def require(self, dataset: Dataset) -> DatasetRegistration:
        """Return a registration or raise a clear error."""
        try:
            return self._registrations[dataset]
        except KeyError:
            raise AppProcessError(
                f"Dataset is not registered: {dataset.value}",
                field="dataset",
                value=dataset.value,
            ) from None

    def datasets(self) -> Iterator[Dataset]:
        """Yield registered dataset IDs in insertion order."""
        return iter(self._registrations)

    def registrations(self) -> tuple[DatasetRegistration, ...]:
        """Return all registrations in insertion order."""
        return tuple(self._registrations.values())

    def supported_instrument_datasets(self) -> frozenset[Dataset]:
        """Return datasets with instrument-level fetch routes."""
        return frozenset(
            registration.dataset
            for registration in self._registrations.values()
            if registration.supports_instrument_ingestion
        )

    def daily_fetch_handlers(
        self,
        ctx: DailyFetchContext,
    ) -> dict[Dataset, DailyFetchHandler]:
        """Build date-level fetch handlers from registrations."""
        handlers: dict[Dataset, DailyFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.daily_fetch_factory is not None:
                handlers[registration.dataset] = registration.daily_fetch_factory(ctx)
        return handlers

    def instrument_fetch_handlers(
        self,
        ctx: InstrumentFetchContext,
    ) -> dict[Dataset, InstrumentFetchHandler]:
        """Build instrument-level fetch handlers from registrations."""
        handlers: dict[Dataset, InstrumentFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.instrument_fetch_factory is not None:
                handlers[registration.dataset] = registration.instrument_fetch_factory(
                    ctx
                )
        return handlers


def _by_instrument(
    method: Callable[..., pl.DataFrame],
    ctx: InstrumentFetchContext,
) -> pl.DataFrame:
    return method(
        source_ticker=ctx.source_ticker,
        start_date=ctx.params.start_date,
        end_date=ctx.params.end_date,
    )


# ---------------------------------------------------------------------------
# Fetch-factory helpers — eliminate the double-lambda boilerplate
# ---------------------------------------------------------------------------


def _daily_fetch(group: str, method: str) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>(ctx.trade_date)``."""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        fn = getattr(fetcher, method)
        return lambda: fn(ctx.trade_date)

    return factory


def _instrument_fetch(group: str, method: str) -> InstrumentFetchFactory:
    """Instrument route via ``_by_instrument``."""

    def factory(ctx: InstrumentFetchContext) -> InstrumentFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        return lambda: _by_instrument(getattr(fetcher, method), ctx)

    return factory


def _property_fetch(group: str, method: str) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>`` — no call, just a property ref."""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        return getattr(getattr(ctx.fetchers, group), method)

    return factory


# ---------------------------------------------------------------------------
# Domain-grouped registration sub-lists（模块级常量）
# ---------------------------------------------------------------------------

# fmt: off

_METADATA_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.CALENDAR,
        write_kind=WriteKind.CALENDAR,
        metadata_dataset=True,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.metadata.fetch_calendar(
                ctx.trade_date[:4] + "-01-01",
                ctx.trade_date[:4] + "-12-31",
            )
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.STOCK_BASIC,
        write_kind=WriteKind.BASIC,
        basic_asset_class="stock",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_stock_basic"),
    ),
    DatasetRegistration(
        dataset=Dataset.ETF_BASIC,
        write_kind=WriteKind.BASIC,
        basic_asset_class="etf",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_etf_basic"),
    ),
    DatasetRegistration(
        dataset=Dataset.INDEX_BASIC,
        write_kind=WriteKind.BASIC,
        basic_asset_class="index",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_index_basic"),
    ),
)

_TRADED_BARS_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.STOCK_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="stock_daily",
        daily_fetch_factory=_daily_fetch("market", "fetch_stock_daily"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_stock_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.ETF_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="etf_daily",
        daily_fetch_factory=_daily_fetch("market", "fetch_etf_daily"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_etf_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.INDEX_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="index_daily",
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.market.fetch_index_daily(
                ctx.trade_date,
                ts_codes=ctx.get_cached_index_codes(),
            )
        ),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_index_daily"),
    ),
)

_MARKET_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.STOCK_STATUS,
        write_kind=WriteKind.STOCK_STATUS,
        daily_fetch_factory=_daily_fetch("market", "fetch_stock_status"),
    ),
)

_ADJ_FACTOR_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.ADJ_FACTOR,
        write_kind=WriteKind.ADJ_FACTOR,
        daily_fetch_factory=_daily_fetch("market", "fetch_adj_factor"),
        instrument_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.market.fetch_adj_factor_by_ticker(
                ts_code=ctx.source_ticker,
                start_date=ctx.params.start_date.replace("-", ""),
                end_date=ctx.params.end_date.replace("-", ""),
            )
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.FUND_ADJ,
        write_kind=WriteKind.FUND_ADJ,
        daily_fetch_factory=_daily_fetch("market", "fetch_fund_adj"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_fund_adj"),
    ),
)

_FUNDAMENTAL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.BALANCE_SHEET,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_balance_sheet"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_balance_sheet"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.INCOME_STATEMENT,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_income_statement"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_income_statement"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.CASH_FLOW,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_cash_flow"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_cash_flow"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.DIVIDEND,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_dividend"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_dividend"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.CORPORATE_ACTIONS,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_corporate_actions"),
    ),
)

_CAPITAL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.VALUATION_METRICS,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_valuation_metrics"),
        instrument_fetch_factory=_instrument_fetch(
            "capital", "fetch_valuation_metrics"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.MARGIN_TRADING,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_margin_trading"),
        instrument_fetch_factory=_instrument_fetch(
            "capital", "fetch_margin_trading"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.PLEDGE_RATIO,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_pledge_ratio"),
        instrument_fetch_factory=_instrument_fetch("capital", "fetch_pledge_ratio"),
    ),
)

_MACRO_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.MACRO_INDICATORS,
        write_kind=WriteKind.MACRO,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=_daily_fetch("macro", "fetch_macro_indicators"),
    ),
)

_FX_COMMODITY_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.FX_DAILY,
        write_kind=WriteKind.INSTRUMENT_CODE_BARS,
        write_dataset="fx_daily",
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.macro.fetch_fx_daily(
                ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
                start_date=ctx.trade_date,
                end_date=ctx.trade_date,
            )
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.COMMODITY_DAILY,
        write_kind=WriteKind.INSTRUMENT_CODE_BARS,
        write_dataset="commodity_daily",
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetch_commodity_daily(ctx.trade_date)
        ),
    ),
)

_PLACEHOLDER_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.INDEX_WEIGHT,
        write_kind=WriteKind.UNSUPPORTED,
    ),
)

# fmt: on

_ALL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    _METADATA_REGISTRATIONS
    + _TRADED_BARS_REGISTRATIONS
    + _MARKET_REGISTRATIONS
    + _ADJ_FACTOR_REGISTRATIONS
    + _FUNDAMENTAL_REGISTRATIONS
    + _CAPITAL_REGISTRATIONS
    + _MACRO_REGISTRATIONS
    + _FX_COMMODITY_REGISTRATIONS
    + _PLACEHOLDER_REGISTRATIONS
)


@cache
def default_dataset_registry() -> DatasetRegistry:
    """Build (once) and return the default application ingestion registry."""
    registry = DatasetRegistry()
    for registration in _ALL_REGISTRATIONS:
        registry.register(registration)
    registry.validate_catalog_capabilities()
    return registry


def _validate_catalog_capability(registration: DatasetRegistration) -> None:
    """Validate app routing against data-owned catalog capabilities."""
    metadata = default_dataset_metadata()[registration.dataset.value]
    if registration.date_schedule.value != metadata.schedule:
        raise AppProcessError(
            "Dataset route schedule does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_schedule=registration.date_schedule.value,
            catalog_schedule=metadata.schedule,
        )
    has_date_route = registration.daily_fetch_factory is not None
    if has_date_route != metadata.supports_date_ingestion:
        raise AppProcessError(
            "Dataset date route does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_supports_date=has_date_route,
            catalog_supports_date=metadata.supports_date_ingestion,
        )
    has_instrument_route = registration.instrument_fetch_factory is not None
    if has_instrument_route != metadata.supports_instrument_ingestion:
        raise AppProcessError(
            "Dataset instrument route does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_supports_instrument=has_instrument_route,
            catalog_supports_instrument=metadata.supports_instrument_ingestion,
        )
