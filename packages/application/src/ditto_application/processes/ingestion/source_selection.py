"""Auto source selection coordinator for ingestion."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from ditto_data.catalog import DataCatalogReader
from ditto_data.models.ingestion import IngestionResult
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.catalog_freshness import select_ingestion_source
from ditto_application.exceptions import AppProcessError

__all__ = [
    "AUTO_SOURCE_NAME",
    "AutoSourceIngestionCoordinator",
    "IngestionCoordinatorLike",
]

AUTO_SOURCE_NAME = "auto"
type DateRangeLister = Callable[[str, str, str], list[str]]


class IngestionCoordinatorLike(Protocol):
    """Subset of ingestion coordinator behavior used by apps/process wrappers."""

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one date."""
        ...

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """Ingest a date range."""
        ...

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one instrument range."""
        ...

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """Backfill adjustment factors."""
        ...


class AutoSourceIngestionCoordinator:
    """Choose a concrete source coordinator per date-level ingestion request."""

    def __init__(
        self,
        coordinators: Mapping[str, IngestionCoordinatorLike],
        *,
        catalog_reader: DataCatalogReader | None,
        date_range_lister: DateRangeLister | None = None,
        default_source: str = "tushare",
    ) -> None:
        if not coordinators:
            raise AppProcessError(
                "source=auto requires at least one concrete coordinator",
                field="coordinators",
                value=(),
            )
        self._coordinators = {
            source_name.lower(): coordinator
            for source_name, coordinator in coordinators.items()
        }
        self._catalog_reader = catalog_reader
        self._date_range_lister = date_range_lister
        normalized_default_source = default_source.lower()
        self._default_source = (
            normalized_default_source
            if normalized_default_source in self._coordinators
            else next(iter(self._coordinators))
        )

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """Select source by dataset/date freshness, then delegate ingestion."""
        source = select_ingestion_source(
            dataset=dataset,
            trade_date=trade_date,
            available_sources=tuple(self._coordinators),
            catalog_reader=self._catalog_reader,
        )
        return self._coordinators[source].ingest_date(dataset, trade_date, force)

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """Select and delegate source per date when a date lister is available."""
        if self._date_range_lister is None:
            return self._coordinators[self._default_source].ingest_range(
                dataset,
                start_date,
                end_date,
                force,
            )
        return [
            self.ingest_date(dataset, trade_date, force)
            for trade_date in self._date_range_lister(dataset, start_date, end_date)
        ]

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """Select source by instrument request freshness, then delegate ingestion."""
        source = self._source_for_instrument_request(dataset, params)
        return self._coordinators[source].ingest_by_instrument(
            dataset,
            params,
            force,
        )

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """Delegate adj-factor backfill to the default source coordinator."""
        return self._coordinators[self._default_source].backfill_adj_factor(
            instrument_id,
            start,
            end,
        )

    def _source_for_instrument_request(
        self,
        dataset: str,
        params: InstrumentIngestParams,
    ) -> str:
        trade_date = self._selection_date_for_instrument_request(params)
        if trade_date is None:
            return self._default_source
        return select_ingestion_source(
            dataset=dataset,
            trade_date=trade_date,
            available_sources=tuple(self._coordinators),
            catalog_reader=self._catalog_reader,
        )

    @staticmethod
    def _selection_date_for_instrument_request(
        params: InstrumentIngestParams,
    ) -> str | None:
        if params.end_date:
            return params.end_date
        if params.start_date:
            return params.start_date
        return None
