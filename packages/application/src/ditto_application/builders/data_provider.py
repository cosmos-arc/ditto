"""
DataProvider implementation — ServiceBackedDataProvider.

Facade pattern: composes MarketService + MetadataService + DerivedQueryService,
satisfying the DataProvider Protocol for unified data access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import polars as pl
from ditto_data.catalog import DataCatalogEntry, DataCatalogReader
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_data.services.market_service import AdjType, MarketBarsQuery, MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_features.services import DerivedQueryService

__all__ = ["ServiceBackedDataProvider"]

_SOURCE_SNAPSHOT_COLUMN = "source_snapshot_id"


@dataclass(frozen=True, slots=True)
class _CatalogSnapshotWindow:
    source: str
    source_ticker: str | None
    start_date: date
    end_date: date
    snapshot_id: str
    freshness_at: datetime

    def contains(self, *, source: str, source_ticker: str, trade_date: date) -> bool:
        return (
            self.source == source
            and self.source_ticker in {None, source_ticker}
            and self.start_date <= trade_date <= self.end_date
        )


def _partition_values(entry: DataCatalogEntry) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in entry.asset.partition_keys:
        key, separator, value = raw.partition("=")
        if separator and key and value:
            values[key] = value
    return values


def _snapshot_window(entry: DataCatalogEntry) -> _CatalogSnapshotWindow | None:
    snapshot_id = entry.source_snapshot_id
    if snapshot_id is None or not snapshot_id.strip():
        return None
    values = _partition_values(entry)
    exact_date = values.get("trade_date")
    start_text = exact_date or values.get("start_date")
    end_text = exact_date or values.get("end_date")
    if start_text is None or end_text is None:
        return None
    try:
        start_date = date.fromisoformat(start_text)
        end_date = date.fromisoformat(end_text)
    except ValueError:
        return None
    if start_date > end_date:
        return None
    return _CatalogSnapshotWindow(
        source=entry.source,
        source_ticker=values.get("source_ticker"),
        start_date=start_date,
        end_date=end_date,
        snapshot_id=snapshot_id,
        freshness_at=entry.freshness_at,
    )


def _resolve_snapshot_id(
    windows: tuple[_CatalogSnapshotWindow, ...],
    *,
    source: str,
    source_ticker: str,
    trade_date: date,
) -> str | None:
    matching = tuple(
        item
        for item in windows
        if item.contains(
            source=source,
            source_ticker=source_ticker,
            trade_date=trade_date,
        )
    )
    exact = tuple(item for item in matching if item.source_ticker == source_ticker)
    eligible = exact or matching
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (item.freshness_at.isoformat(), item.snapshot_id.encode()),
    ).snapshot_id


def _attach_catalog_source_snapshots(
    frame: pl.DataFrame,
    catalog_reader: DataCatalogReader,
) -> pl.DataFrame:
    if frame.is_empty() or _SOURCE_SNAPSHOT_COLUMN in frame.columns:
        return frame
    required = {"trade_date", "source", "source_ticker"}
    if not required.issubset(frame.columns):
        return frame.with_columns(
            pl.lit(None, dtype=pl.String).alias(_SOURCE_SNAPSHOT_COLUMN)
        )
    windows = tuple(
        window
        for entry in catalog_reader.list_assets("market")
        if (window := _snapshot_window(entry)) is not None
    )
    snapshot_ids: list[str | None] = []
    for row in frame.select(sorted(required)).to_dicts():
        raw_date = row["trade_date"]
        trade_date = (
            raw_date
            if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date))
        )
        snapshot_ids.append(
            _resolve_snapshot_id(
                windows,
                source=str(row["source"]),
                source_ticker=str(row["source_ticker"]),
                trade_date=trade_date,
            )
        )
    return frame.with_columns(
        pl.Series(_SOURCE_SNAPSHOT_COLUMN, snapshot_ids, dtype=pl.String)
    )


class ServiceBackedDataProvider:
    """
    组合 MarketService + MetadataService + DerivedQueryService 的 DataProvider 实现.

    命名为 ServiceBacked（Facade 模式）而非 Adapter（非接口转换）。
    """

    def __init__(
        self,
        *,
        market_service: MarketService,
        metadata_service: MetadataService,
        derived_service: DerivedQueryService,
        catalog_reader: DataCatalogReader | None = None,
    ) -> None:
        self._market = market_service
        self._metadata = metadata_service
        self._derived = derived_service
        self._catalog = catalog_reader

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        """
        获取行情数据.

        自动将 string ticker 解析为 int instrument_id，
        然后委托给 MarketService.find_bars。
        """
        ticker_to_id = self._metadata.instrument.resolve_instrument_ids_batch(
            identifiers=list(query.instruments),
            source="tushare",
            asof=query.asof,
        )
        instrument_ids = [
            ticker_to_id[ticker]
            for ticker in query.instruments
            if ticker in ticker_to_id
        ]

        if not instrument_ids:
            return pl.DataFrame()

        bars_query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=query.start,
            end=query.end,
            adj=AdjType.from_string(query.adj),
        )
        bars = self._market.find_bars(bars_query)
        if self._catalog is None:
            return bars
        return _attach_catalog_source_snapshots(bars, self._catalog)

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        """获取标的列表."""
        return self._metadata.find_securities(
            None,
            asset_class=query.asset_class,
            exchange=query.exchange,
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        """获取交易日历."""
        return self._metadata.calendar.list_calendar_range(start, end, only_open=True)

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """获取因子数据."""
        ticker_to_id = self._metadata.instrument.resolve_instrument_ids_batch(
            identifiers=list(instruments),
            source="tushare",
            asof=asof,
        )
        instrument_ids = tuple(
            ticker_to_id[t] for t in instruments if t in ticker_to_id
        )

        if not instrument_ids:
            return pl.DataFrame()

        return self._derived.query_for_evaluation(
            derived_ids=(name,),
            instrument_ids=instrument_ids,
            start=start,
            end=end,
        )
