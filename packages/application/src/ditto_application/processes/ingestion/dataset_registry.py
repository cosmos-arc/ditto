"""Dataset registry for application ingestion routing."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import polars as pl
from ditto_data.models import FX_CODE_TO_INSTRUMENT_ID, Dataset
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


def default_dataset_registry() -> DatasetRegistry:
    """Build the default application ingestion registry."""
    registry = DatasetRegistry()

    registry.register(
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
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="stock",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_stock_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ETF_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="etf",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_etf_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INDEX_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="index",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_index_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_stock_daily(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.market.fetch_stock_daily, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ETF_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="etf_daily",
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_etf_daily(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.market.fetch_etf_daily, ctx)
            ),
        )
    )
    registry.register(
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
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.market.fetch_index_daily, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_STATUS,
            write_kind=WriteKind.STOCK_STATUS,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_stock_status(ctx.trade_date)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ADJ_FACTOR,
            write_kind=WriteKind.ADJ_FACTOR,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_adj_factor(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_adj_factor_by_ticker(
                    ts_code=ctx.source_ticker,
                    start_date=ctx.params.start_date.replace("-", ""),
                    end_date=ctx.params.end_date.replace("-", ""),
                )
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.FUND_ADJ,
            write_kind=WriteKind.ADJ_FACTOR,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.market.fetch_fund_adj(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.market.fetch_fund_adj, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.BALANCE_SHEET,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.fundamental.fetch_balance_sheet(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(
                    ctx.fetchers.fundamental.fetch_balance_sheet, ctx
                )
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INCOME_STATEMENT,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.fundamental.fetch_income_statement(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(
                    ctx.fetchers.fundamental.fetch_income_statement, ctx
                )
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.CASH_FLOW,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.fundamental.fetch_cash_flow(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.fundamental.fetch_cash_flow, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.DIVIDEND,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.fundamental.fetch_dividend(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.fundamental.fetch_dividend, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.CORPORATE_ACTIONS,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.fundamental.fetch_corporate_actions(ctx.trade_date)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.VALUATION_METRICS,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.capital.fetch_valuation_metrics(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(
                    ctx.fetchers.capital.fetch_valuation_metrics, ctx
                )
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.MARGIN_TRADING,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.capital.fetch_margin_trading(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.capital.fetch_margin_trading, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.PLEDGE_RATIO,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.capital.fetch_pledge_ratio(ctx.trade_date)
            ),
            instrument_fetch_factory=lambda ctx: (
                lambda: _by_instrument(ctx.fetchers.capital.fetch_pledge_ratio, ctx)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.MACRO_INDICATORS,
            write_kind=WriteKind.MACRO,
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.macro.fetch_macro_indicators(ctx.trade_date)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.FX_DAILY,
            write_kind=WriteKind.INSTRUMENT_CODE_BARS,
            write_dataset="fx_daily",
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetchers.macro.fetch_fx_daily(
                    ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
                    start_date=ctx.trade_date,
                    end_date=ctx.trade_date,
                )
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.COMMODITY_DAILY,
            write_kind=WriteKind.INSTRUMENT_CODE_BARS,
            write_dataset="commodity_daily",
            daily_fetch_factory=lambda ctx: (
                lambda: ctx.fetch_commodity_daily(ctx.trade_date)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INDEX_WEIGHT,
            write_kind=WriteKind.UNSUPPORTED,
        )
    )
    return registry
