"""
DataProvider implementation — ServiceBackedDataProvider.

Facade pattern: composes MarketService + MetadataService + DerivedQueryService,
satisfying the DataProvider Protocol for unified data access.
"""

from __future__ import annotations

from collections.abc import Sequence
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


def _freshness_key(window: _CatalogSnapshotWindow) -> tuple[str, bytes]:
    """Order windows by observed freshness, then immutable identity."""
    return (window.freshness_at.isoformat(), window.snapshot_id.encode())


def _lineage_frame(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.select(
        pl.col("source").cast(pl.String).alias("_lineage_source"),
        pl.col("source_ticker").cast(pl.String).alias("_lineage_ticker"),
        pl.col("trade_date").cast(pl.Date).alias("_lineage_date"),
    ).with_columns(
        pl.lit(None, dtype=pl.String).alias("_lineage_snapshot"),
        pl.lit(None, dtype=pl.String).alias("_lineage_freshness"),
    )


def _apply_exact(
    lineage: pl.DataFrame,
    windows: Sequence[tuple[tuple[object, ...], _CatalogSnapshotWindow]],
    on: Sequence[str],
    *,
    fallback_only: bool = False,
) -> pl.DataFrame:
    """Join the freshest exact-date window per key, fresher wins per row."""
    if not windows:
        return lineage
    lookup = pl.DataFrame(
        {
            **{
                name: [key[index] for key, _ in windows]
                for index, name in enumerate(on)
            },
            "_lookup_snapshot": [window.snapshot_id for _, window in windows],
            "_lookup_freshness": [_freshness_key(window)[0] for _, window in windows],
        },
        schema={
            **{name: pl.String for name in on if name != "_lineage_date"},
            **({"_lineage_date": pl.Date} if "_lineage_date" in on else {}),
            "_lookup_snapshot": pl.String,
            "_lookup_freshness": pl.String,
        },
    )
    joined = lineage.join(lookup, on=list(on), how="left")
    takes = (
        pl.col("_lineage_snapshot").is_null()
        if fallback_only
        else (
            pl.col("_lineage_freshness").is_null()
            | (
                pl.col("_lookup_freshness").is_not_null()
                & (pl.col("_lookup_freshness") > pl.col("_lineage_freshness"))
            )
        )
    )
    return _rewrite_lineage(
        joined,
        takes,
        pl.col("_lookup_snapshot"),
        pl.col("_lookup_freshness"),
    ).drop("_lookup_snapshot", "_lookup_freshness")


def _apply_ranged(
    lineage: pl.DataFrame,
    window: _CatalogSnapshotWindow,
    *,
    fallback_only: bool = False,
) -> pl.DataFrame:
    """Overlay one multi-date window where it outranks the current pick."""
    matches = (
        (pl.col("_lineage_source") == window.source)
        & (
            pl.lit(window.source_ticker is None)
            | (pl.col("_lineage_ticker") == window.source_ticker)
        )
        & (pl.col("_lineage_date") >= window.start_date)
        & (pl.col("_lineage_date") <= window.end_date)
    )
    takes = matches & (
        pl.col("_lineage_snapshot").is_null()
        if fallback_only
        else (
            pl.col("_lineage_freshness").is_null()
            | (pl.lit(_freshness_key(window)[0]) > pl.col("_lineage_freshness"))
        )
    )
    return _rewrite_lineage(
        lineage,
        takes,
        pl.lit(window.snapshot_id),
        pl.lit(_freshness_key(window)[0]),
    )


def _rewrite_lineage(
    lineage: pl.DataFrame,
    takes: pl.Expr,
    snapshot: pl.Expr,
    freshness: pl.Expr,
) -> pl.DataFrame:
    return lineage.with_columns(
        pl.when(takes)
        .then(
            pl.struct(
                snapshot.alias("_lineage_snapshot"),
                freshness.alias("_lineage_freshness"),
            )
        )
        .otherwise(pl.struct(pl.col("_lineage_snapshot"), pl.col("_lineage_freshness")))
        .struct.field("*")
    )


def _catalog_windows(
    catalog_reader: DataCatalogReader,
) -> tuple[_CatalogSnapshotWindow, ...]:
    return tuple(
        window
        for entry in catalog_reader.list_assets("market")
        if (window := _snapshot_window(entry)) is not None
    )


def _partition_windows(
    windows: tuple[_CatalogSnapshotWindow, ...],
) -> tuple[
    dict[tuple[str, str, date], _CatalogSnapshotWindow],
    dict[tuple[str, date], _CatalogSnapshotWindow],
    list[_CatalogSnapshotWindow],
]:
    """Split catalog windows into keyed exact-date and multi-date shapes."""
    keyed: dict[tuple[str, str, date], _CatalogSnapshotWindow] = {}
    wildcard_date: dict[tuple[str, date], _CatalogSnapshotWindow] = {}
    ranged: list[_CatalogSnapshotWindow] = []
    for window in windows:
        if window.start_date != window.end_date:
            ranged.append(window)
        elif window.source_ticker is None:
            key = (window.source, window.start_date)
            if key not in wildcard_date or _freshness_key(window) > _freshness_key(
                wildcard_date[key]
            ):
                wildcard_date[key] = window
        else:
            key = (window.source, window.source_ticker, window.start_date)
            if key not in keyed or _freshness_key(window) > _freshness_key(keyed[key]):
                keyed[key] = window
    return keyed, wildcard_date, ranged


def _attach_catalog_source_snapshots(
    frame: pl.DataFrame,
    catalog_reader: DataCatalogReader,
) -> pl.DataFrame:
    if frame.is_empty() or _SOURCE_SNAPSHOT_COLUMN in frame.columns:
        return frame
    required = {"trade_date", "source", "source_ticker"}
    if not required.issubset(frame.columns) or not (
        windows := _catalog_windows(catalog_reader)
    ):
        return frame.with_columns(
            pl.lit(None, dtype=pl.String).alias(_SOURCE_SNAPSHOT_COLUMN)
        )
    # Vectorized lineage. The former per-row Python scan scaled as rows x
    # catalog entries; exact-date windows (the common catalog shape) resolve
    # through joins and only the few multi-date windows iterate. Ticker-
    # specific windows (exact or ranged) form the preferred class, wildcard
    # windows the fallback, and within a class the freshest snapshot wins
    # per row, matching the original scan's precedence exactly.
    keyed, wildcard_date, ranged = _partition_windows(windows)
    lineage = _lineage_frame(frame)
    lineage = _apply_exact(
        lineage,
        tuple(keyed.items()),
        ["_lineage_source", "_lineage_ticker", "_lineage_date"],
    )
    for window in sorted(ranged, key=_freshness_key):
        if window.source_ticker is not None:
            lineage = _apply_ranged(lineage, window)
    lineage = _apply_exact(
        lineage,
        tuple(wildcard_date.items()),
        ["_lineage_source", "_lineage_date"],
        fallback_only=True,
    )
    for window in sorted(ranged, key=_freshness_key):
        if window.source_ticker is None:
            lineage = _apply_ranged(lineage, window, fallback_only=True)
    return frame.with_columns(
        lineage["_lineage_snapshot"].alias(_SOURCE_SNAPSHOT_COLUMN)
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
