"""Dataset registry for application ingestion routing."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import polars as pl
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams

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
            raise ValueError(f"write_dataset is required for {self.write_kind.value}")
        if self.write_kind == WriteKind.BASIC and self.basic_asset_class is None:
            raise ValueError("basic_asset_class is required for basic datasets")

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
            raise ValueError(
                f"Dataset already registered: {registration.dataset.value}"
            )
        self._registrations[registration.dataset] = registration

    def require(self, dataset: Dataset) -> DatasetRegistration:
        """Return a registration or raise a clear error."""
        try:
            return self._registrations[dataset]
        except KeyError:
            raise KeyError(f"Dataset is not registered: {dataset.value}") from None

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
