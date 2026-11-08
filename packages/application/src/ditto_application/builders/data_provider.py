"""
DataProvider implementation — ServiceBackedDataProvider.

Facade pattern: composes MarketService + MetadataService + DerivedQueryService,
satisfying the DataProvider Protocol for unified data access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from hashlib import sha256

import orjson
import polars as pl
from ditto_backtest.provenance import aggregate_source_snapshot_id
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_completion import checkpoint_matches_snapshot
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.models.common import InstrumentIdRange
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_data.services.market_service import AdjType, MarketBarsQuery, MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_features.services import DerivedQueryService

from ditto_application.catalog_freshness import dataset_namespace, observed_at
from ditto_application.exceptions import AppBuilderError

__all__ = ["ServiceBackedDataProvider"]

_SOURCE_SNAPSHOT_COLUMN = "source_snapshot_id"


@dataclass(frozen=True, slots=True)
class _CatalogSnapshotWindow:
    source: str
    source_ticker: str | None
    start_date: date
    end_date: date
    snapshot_id: str
    observed_at: datetime
    consumable: bool = False

    def contains(self, *, source: str, source_ticker: str, trade_date: date) -> bool:
        return (
            self.source == source
            and self.source_ticker in {None, source_ticker}
            and self.start_date <= trade_date <= self.end_date
        )


def _partition_values(partition_keys: tuple[str, ...]) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in partition_keys:
        key, separator, value = raw.partition("=")
        if separator and key and value:
            values[key] = value
    return values


def _metadata_value(snapshot: ProviderSnapshot, key: str) -> str | None:
    for name, value in snapshot.response_metadata:
        if name == key:
            return value
    return None


def _optional_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _snapshot_window(snapshot: ProviderSnapshot) -> _CatalogSnapshotWindow | None:
    """
    Lineage window for one provider snapshot.

    窗口区间优先解析自 canonical_asset partition_keys(升级前的遗留行),
    数据集级 canonical 资产后回退到 snapshot.request_start/end;排序时钟
    采用 #393 观察事件,内容首次可见时间兜底。
    """
    if not snapshot.snapshot_id.strip():
        return None
    values = _partition_values(snapshot.canonical_asset.partition_keys)
    exact_date = values.get("trade_date")
    start_text = exact_date or values.get("start_date") or snapshot.request_start
    end_text = exact_date or values.get("end_date") or snapshot.request_end
    start_date = _optional_iso_date(start_text)
    end_date = _optional_iso_date(end_text)
    if start_date is None or end_date is None or start_date > end_date:
        return None
    source_ticker = _metadata_value(snapshot, "source_ticker") or values.get(
        "source_ticker"
    )
    return _CatalogSnapshotWindow(
        source=snapshot.source,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
        snapshot_id=snapshot.snapshot_id,
        observed_at=observed_at(snapshot),
    )


def _freshness_key(window: _CatalogSnapshotWindow) -> tuple[str, bytes]:
    """Order windows by observed recency, then immutable identity."""
    return (window.observed_at.isoformat(), window.snapshot_id.encode())


def _freshness(window: _CatalogSnapshotWindow) -> str:
    """Single sortable key preserving the observation/identity tie-break."""
    return f"{window.observed_at.isoformat()}|{window.snapshot_id}"


def _lineage_frame(frame: pl.DataFrame) -> pl.DataFrame:
    return (
        frame.select(
            pl.col("source").cast(pl.String).alias("_lineage_source"),
            pl.col("source_ticker").cast(pl.String).alias("_lineage_ticker"),
            pl.col("trade_date").cast(pl.Date).alias("_lineage_date"),
        )
        .with_row_index("_lineage_row")
        .with_columns(
            pl.lit(None, dtype=pl.String).alias("_lineage_snapshot"),
            pl.lit(None, dtype=pl.String).alias("_lineage_freshness"),
            pl.lit(None, dtype=pl.String).alias("_lineage_class"),
        )
    )


def _apply_exact(
    lineage: pl.DataFrame,
    windows: Sequence[tuple[tuple[object, ...], _CatalogSnapshotWindow]],
    on: Sequence[str],
    *,
    lineage_class: str,
) -> pl.DataFrame:
    """Join the freshest exact-date window per key within one class."""
    if not windows:
        return lineage
    lookup = pl.DataFrame(
        {
            **{
                name: [key[index] for key, _ in windows]
                for index, name in enumerate(on)
            },
            "_lookup_snapshot": [window.snapshot_id for _, window in windows],
            "_lookup_freshness": [_freshness(window) for _, window in windows],
        },
        schema={
            **{name: pl.String for name in on if name != "_lineage_date"},
            **({"_lineage_date": pl.Date} if "_lineage_date" in on else {}),
            "_lookup_snapshot": pl.String,
            "_lookup_freshness": pl.String,
        },
    )
    joined = lineage.join(lookup, on=list(on), how="left")
    takes = _takes(joined, lineage_class, pl.col("_lookup_freshness"))
    rewritten = _rewrite_lineage(
        joined,
        takes,
        pl.col("_lookup_snapshot"),
        pl.col("_lookup_freshness"),
        lineage_class,
    )
    return rewritten.drop("_lookup_snapshot", "_lookup_freshness").sort("_lineage_row")


def _apply_ranged(
    lineage: pl.DataFrame,
    window: _CatalogSnapshotWindow,
    *,
    lineage_class: str,
) -> pl.DataFrame:
    """Overlay one multi-date window within its lineage class."""
    matches = (
        (pl.col("_lineage_source") == window.source)
        & (
            pl.lit(window.source_ticker is None)
            | (pl.col("_lineage_ticker") == window.source_ticker)
        )
        & (pl.col("_lineage_date") >= window.start_date)
        & (pl.col("_lineage_date") <= window.end_date)
    )
    takes = matches & _takes(lineage, lineage_class, pl.lit(_freshness(window)))
    return _rewrite_lineage(
        lineage,
        takes,
        pl.lit(window.snapshot_id),
        pl.lit(_freshness(window)),
        lineage_class,
    )


def _takes(lineage: pl.DataFrame, lineage_class: str, freshness: pl.Expr) -> pl.Expr:
    """
    A window takes the row only within its own lineage class.

    Ticker-specific windows never lose to wildcard ones regardless of
    freshness, while fresher candidates replace older picks of the same
    class — the original scan's precedence.
    """
    return pl.col("_lineage_snapshot").is_null() | (
        (pl.col("_lineage_class") == pl.lit(lineage_class))
        & (freshness.is_not_null() & (freshness > pl.col("_lineage_freshness")))
    )


def _rewrite_lineage(
    lineage: pl.DataFrame,
    takes: pl.Expr,
    snapshot: pl.Expr,
    freshness: pl.Expr,
    lineage_class: str,
) -> pl.DataFrame:
    return lineage.with_columns(
        pl.when(takes)
        .then(
            pl.struct(
                snapshot.alias("_lineage_snapshot"),
                freshness.alias("_lineage_freshness"),
                pl.lit(lineage_class).alias("_lineage_class"),
            )
        )
        .otherwise(
            pl.struct(
                pl.col("_lineage_snapshot"),
                pl.col("_lineage_freshness"),
                pl.col("_lineage_class"),
            )
        )
        .struct.field("*")
    )


_BAR_DATASETS = frozenset({"stock_daily", "etf_daily", "index_daily"})


def _catalog_windows(
    snapshot_reader: ProviderSnapshotReader,
    dataset_id: str | None,
    lifecycle: PartitionLifecycleReader | None,
) -> tuple[_CatalogSnapshotWindow, ...]:
    """
    Daily-bar lineage windows for the expected dataset.

    #394:窗口来自 provider snapshots 的数据集级 canonical 资产。带期望
    dataset 时只有该数据集的快照参与;否则任一日线数据集都可能(遗留
    调用方),防止相邻数据集的更新快照抢占同一 source/ticker/date 窗口
    盖错 lineage。
    """
    allowed = {dataset_id} if dataset_id is not None else _BAR_DATASETS
    windows: list[_CatalogSnapshotWindow] = []
    for dataset in sorted(allowed):
        canonical = DataAssetRef(
            dataset_id=dataset,
            namespace=dataset_namespace(dataset),
            partition_keys=(),
        )
        completed = {
            checkpoint.complete_evidence_id: checkpoint
            for checkpoint in (
                lifecycle.list_complete(dataset_id=dataset) if lifecycle else ()
            )
        }
        windows.extend(
            replace(
                window,
                consumable=snapshot.payload_retained
                and (checkpoint := completed.get(snapshot.snapshot_id)) is not None
                and checkpoint_matches_snapshot(checkpoint, snapshot),
            )
            for snapshot in snapshot_reader.list_snapshots(canonical_asset=canonical)
            if (window := _snapshot_window(snapshot)) is not None
        )
    return tuple(windows)


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
    snapshot_reader: ProviderSnapshotReader,
    dataset_id: str | None = None,
    lifecycle: PartitionLifecycleReader | None = None,
) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    if _SOURCE_SNAPSHOT_COLUMN in frame.columns:
        for identity in frame[_SOURCE_SNAPSHOT_COLUMN].drop_nulls().unique():
            snapshot = snapshot_reader.get_snapshot(str(identity))
            if snapshot is None or (
                dataset_id is not None and snapshot.dataset_id != dataset_id
            ):
                raise AppBuilderError(
                    f"source snapshot {identity!r} does not identify dataset "
                    + f"{dataset_id}"
                )
        return frame
    required = {"trade_date", "source", "source_ticker"}
    if not required.issubset(frame.columns) or not (
        windows := _catalog_windows(snapshot_reader, dataset_id, lifecycle)
    ):
        return frame.with_columns(
            pl.lit(None, dtype=pl.String).alias(_SOURCE_SNAPSHOT_COLUMN)
        )
    # Vectorized lineage. Exact-date windows (the common snapshot shape) resolve
    # through joins and only the few multi-date windows iterate. Ticker-specific
    # windows (exact or ranged) form the preferred class, wildcard windows the
    # fallback, and within a class the most recently observed snapshot wins per
    # row;无覆盖窗口的行保持 null lineage,由下游 PIT 边界 fail-closed。
    keyed, wildcard_date, ranged = _partition_windows(windows)
    lineage = _lineage_frame(frame)
    lineage = _apply_exact(
        lineage,
        tuple(keyed.items()),
        ["_lineage_source", "_lineage_ticker", "_lineage_date"],
        lineage_class="ticker",
    )
    for window in sorted(ranged, key=_freshness_key):
        if window.source_ticker is not None:
            lineage = _apply_ranged(lineage, window, lineage_class="ticker")
    lineage = _apply_exact(
        lineage,
        tuple(wildcard_date.items()),
        ["_lineage_source", "_lineage_date"],
        lineage_class="wildcard",
    )
    for window in sorted(ranged, key=_freshness_key):
        if window.source_ticker is None:
            lineage = _apply_ranged(lineage, window, lineage_class="wildcard")
    # A canonical write can precede snapshot registration. Durable write intents
    # therefore also block lineage until recovery completes, even without a snapshot.
    pending = [
        (pl.col("_lineage_source") == checkpoint.source)
        & pl.col("_lineage_date").is_between(
            date.fromisoformat(checkpoint.request_start),
            date.fromisoformat(checkpoint.request_end),
        )
        for dataset in sorted({dataset_id} if dataset_id else _BAR_DATASETS)
        for checkpoint in (
            lifecycle.list_incomplete(dataset_id=dataset) if lifecycle else ()
        )
    ]
    blocked = pl.any_horizontal(pending) if pending else pl.lit(False)
    resolved = lineage.select(
        "_lineage_row",
        pl.when(
            pl.col("_lineage_snapshot").is_in(
                [window.snapshot_id for window in windows if window.consumable]
            )
            & ~blocked
        )
        .then(pl.col("_lineage_snapshot"))
        .otherwise(None)
        .alias(_SOURCE_SNAPSHOT_COLUMN),
    ).sort("_lineage_row")
    return (
        frame.with_row_index("_lineage_row")
        .join(resolved, on="_lineage_row", how="left")
        .drop("_lineage_row")
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
        snapshot_reader: ProviderSnapshotReader | None = None,
        lifecycle_reader: PartitionLifecycleReader | None = None,
    ) -> None:
        self._market = market_service
        self._metadata = metadata_service
        self._derived = derived_service
        self._snapshots = snapshot_reader
        self._lifecycle = lifecycle_reader

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
            # PIT cutoff 必须贯穿复权因子读取（审计 #684 批B #8）：缺失时
            # asof=None 走不过滤 join，cutoff 后发布的因子修订会泄漏进
            # 历史回放窗口。
            asof=query.asof,
        )
        bars = self._market.find_bars(bars_query)
        if self._snapshots is None and not query.with_execution_state:
            return bars
        dataset_id = f"{InstrumentIdRange.detect_asset_class(instrument_ids)}_daily"
        if query.dataset_id is not None and query.dataset_id != dataset_id:
            raise AppBuilderError(
                f"requested dataset {query.dataset_id} disagrees with {dataset_id} "
                + f"for instruments {instrument_ids}"
            )
        if self._snapshots is not None:
            bars = _attach_catalog_source_snapshots(
                bars, self._snapshots, dataset_id, self._lifecycle
            )
        if query.adj in {"qfq", "hfq"} and self._snapshots is not None:
            bars = self._adjusted_history_evidence(
                bars, query, instrument_ids, dataset_id
            )
        if query.with_execution_state and dataset_id == "stock_daily":
            bars = self._stock_execution_state(bars, query, instrument_ids)
        if query.with_execution_state:
            bars = self._adjustment_state(bars, query, instrument_ids, dataset_id)
        return bars

    def _adjusted_history_evidence(
        self,
        bars: pl.DataFrame,
        query: BarQuery,
        instrument_ids: list[int],
        dataset_id: str,
    ) -> pl.DataFrame:
        """
        Bind the visible factor input window used by MarketService adjustment.

        Preserve all visible candidates (including the qfq baseline), not a second
        implementation of revision selection. Actual adjusted OHLC is hashed by
        the consuming feed alongside this factor-window hash.
        """
        if bars.is_empty() or dataset_id == "index_daily":
            return bars
        if self._snapshots is None:
            raise AppBuilderError("missing adjustment snapshot reader")
        factors = (
            self._market.get_adj_factors(query.start, query.end)
            if dataset_id == "stock_daily"
            else self._market.get_fund_adj(query.start, query.end)
        )
        if (
            factors is None
            or factors.is_empty()
            or "knowledge_date" not in factors.columns
        ):
            raise AppBuilderError("missing adjustment history/knowledge_date")
        factors = factors.filter(pl.col("instrument_id").is_in(instrument_ids))
        if query.asof is not None:
            factors = factors.filter(
                pl.col("knowledge_date").cast(pl.Date) <= date.fromisoformat(query.asof)
            )
        factors = _attach_catalog_source_snapshots(
            factors,
            self._snapshots,
            "adj_factor" if dataset_id == "stock_daily" else "fund_adj",
            self._lifecycle,
        )
        if factors.is_empty() or factors["source_snapshot_id"].null_count():
            raise AppBuilderError("missing adjustment history lineage")
        evidence: list[dict[str, int | str | None]] = []
        for key, group in factors.partition_by("instrument_id", as_dict=True).items():
            rows = group.sort(["trade_date", "knowledge_date"]).select(
                sorted(group.columns)
            )
            evidence.append(
                {
                    "instrument_id": int(key[0]),
                    "adjustment_input_hash": "sha256:"
                    + sha256(
                        orjson.dumps(rows.to_dicts(), option=orjson.OPT_SORT_KEYS)
                    ).hexdigest(),
                    "adjustment_source_snapshot_id": aggregate_source_snapshot_id(
                        rows["source_snapshot_id"].to_list()
                    ),
                }
            )
        return bars.join(
            pl.DataFrame(evidence), on="instrument_id", how="left", validate="m:1"
        )

    def _adjustment_state(
        self,
        bars: pl.DataFrame,
        query: BarQuery,
        instrument_ids: list[int],
        dataset_id: str,
    ) -> pl.DataFrame:
        """Keep actual adjustment provenance; no silent missing-factor coverage."""
        if self._snapshots is None:
            raise AppBuilderError("adjustment inputs require source snapshot evidence")
        stock = dataset_id == "stock_daily"
        factors = (
            self._market.get_adj_factors(query.start, query.end)
            if stock
            else self._market.get_fund_adj(query.start, query.end)
        )
        if factors is None or factors.is_empty():
            raise AppBuilderError(f"missing adjustment inputs for {instrument_ids}")
        factors = factors.filter(pl.col("instrument_id").is_in(instrument_ids))
        factors = _attach_catalog_source_snapshots(
            factors,
            self._snapshots,
            "adj_factor" if stock else "fund_adj",
            self._lifecycle,
        )
        keys = ["instrument_id", "trade_date"]
        factors = factors.sort([*keys, "knowledge_date"]).unique(
            subset=keys, keep="last"
        )
        joined = bars.join(
            factors.select(
                *keys,
                "adj_factor",
                pl.col("knowledge_date").alias("adjustment_knowledge_date"),
                pl.col("source_snapshot_id").alias("adjustment_source_snapshot_id"),
            ),
            on=keys,
            how="left",
            validate="1:1",
        )
        bad = joined.filter(
            pl.col("adj_factor").is_null()
            | (pl.col("adj_factor") <= 0)
            | ~pl.col("adj_factor").is_finite()
            | pl.col("adjustment_source_snapshot_id").is_null()
        )
        if not bad.is_empty():
            raise AppBuilderError(
                "missing adjustment input/lineage: "
                + f"{bad.select(keys).head(10).to_dicts()}"
            )
        return joined

    def _stock_execution_state(
        self, bars: pl.DataFrame, query: BarQuery, instrument_ids: list[int]
    ) -> pl.DataFrame:
        """Actual daily status/limits; unknown state never becomes tradable."""
        if self._snapshots is None:
            raise AppBuilderError(
                "stock execution state requires source snapshot evidence"
            )
        keys = ["instrument_id", "trade_date"]
        status = self._market.get_stock_status(query.start, query.end).filter(
            pl.col("instrument_id").is_in(instrument_ids)
        )
        limits = self._market.get_stock_limits(query.start, query.end).filter(
            pl.col("instrument_id").is_in(instrument_ids)
        )
        for dataset, frame in (("stock_status", status), ("stock_limit", limits)):
            if frame.is_empty():
                raise AppBuilderError(f"missing {dataset} inputs for {instrument_ids}")
        status = _attach_catalog_source_snapshots(
            status, self._snapshots, "stock_status", self._lifecycle
        )
        limits = _attach_catalog_source_snapshots(
            limits, self._snapshots, "stock_limit", self._lifecycle
        )
        missing_quotes = status.filter(pl.col("is_suspended")).join(
            bars.select(keys), on=keys, how="anti"
        )
        if not missing_quotes.is_empty():
            raise AppBuilderError(
                "verified suspension without valuation quote; "
                + "positions cannot disappear: "
                + f"{missing_quotes.select(keys).head(10).to_dicts()}"
            )
        joined = bars.join(
            status.select(
                *keys,
                "is_suspended",
                "is_st",
                "list_status",
                pl.col("source_snapshot_id").alias("status_source_snapshot_id"),
            ),
            on=keys,
            how="left",
            validate="1:1",
        ).join(
            limits.select(
                *keys,
                pl.col("up_limit").alias("limit_up"),
                pl.col("down_limit").alias("limit_down"),
                pl.col("source_snapshot_id").alias("limit_source_snapshot_id"),
            ),
            on=keys,
            how="left",
            validate="1:1",
        )
        required = (
            "is_suspended",
            "is_st",
            "list_status",
            "limit_up",
            "limit_down",
            "status_source_snapshot_id",
            "limit_source_snapshot_id",
        )
        bad = joined.filter(
            pl.any_horizontal(pl.col(name).is_null() for name in required)
            | (pl.col("list_status") != "L")
        )
        if not bad.is_empty():
            raise AppBuilderError(
                "missing status/limit/lineage or unresolved exit: "
                + f"{bad.select(keys).head(10).to_dicts()}"
            )
        return joined

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
