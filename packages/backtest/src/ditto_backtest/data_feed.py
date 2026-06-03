"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 是 kernel trading 类型，仅用于数据容器字段。
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
ProviderBackedDataFeed 通过 DataProvider Protocol 获取数据.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import polars as pl
from ditto_data.provider import BarQuery, DataProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot as _MarketSnapshot

from ditto_backtest.provenance import aggregate_source_snapshot_id

__all__ = [
    "DataFeed",
    "ProviderBackedDataFeed",
    "Slice",
]

_SOURCE_SNAPSHOT_ID_COLUMN = "source_snapshot_id"


# ---------------------------------------------------------------------------
# Slice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slice:
    """
    某日所有标的的聚合视图.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        step_time: 回测步骤时间
        bars: instrument_id → MarketSnapshot
        benchmark_close: 基准收盘价 (None = 无基准)
        source_snapshot_ids: instrument_id → 上游数据快照 ID

    """

    trade_date: str
    step_time: datetime
    bars: dict[InstrumentId, _MarketSnapshot]
    benchmark_close: float | None = None
    source_snapshot_ids: dict[InstrumentId, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DataFeed Protocol
# ---------------------------------------------------------------------------


class DataFeed(Protocol):
    """市场数据源协议 — 提供交易日历和逐日切片。"""

    def trading_days(self) -> list[str]:
        """返回回测区间内的交易日列表 (YYYY-MM-DD)。"""
        ...

    def get_slice(self, date: str) -> Slice:
        """获取指定日期的市场数据切片。"""
        ...

    def get_history(
        self,
        instrument_ids: list[InstrumentId],
        as_of_date: str,
        lookback_days: int,
    ) -> pl.DataFrame:
        """
        获取指定标的历史行情窗口。

        返回 as_of_date 之前 lookback_days 个交易日的 OHLCV 数据，
        包含 trade_date 和 instrument_id 列用于分组和排序。
        """
        ...


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _row_to_snapshot(
    date: str,
    iid: InstrumentId,
    row: dict[str, Any],
) -> _MarketSnapshot:
    """Convert a polars row dict (from ``to_dicts()``) to a MarketSnapshot."""
    close = float(row["close"])
    volume = float(row.get("volume", 0))
    raw_amount = row.get("amount")
    amount = float(raw_amount) if raw_amount is not None else close * volume
    return _MarketSnapshot(
        trade_date=date,
        instrument_id=iid,
        open=float(row.get("open", close)),
        high=float(row.get("high", close)),
        low=float(row.get("low", close)),
        close=close,
        prev_close=float(row.get("prev_close", close)),
        volume=volume,
        amount=amount,
        is_suspended=bool(row.get("is_suspended", False)),
        limit_up=(float(row["limit_up"]) if row.get("limit_up") is not None else None),
        limit_down=(
            float(row["limit_down"]) if row.get("limit_down") is not None else None
        ),
        avg_volume_20d=(
            float(row["avg_volume_20d"])
            if row.get("avg_volume_20d") is not None
            else None
        ),
    )


def _source_snapshot_sets_by_instrument(
    df: pl.DataFrame,
    *,
    exclude_instrument_id: InstrumentId | None = None,
) -> dict[InstrumentId, set[str]]:
    """Collect exact source snapshot IDs from a bars DataFrame."""
    if df.is_empty() or _SOURCE_SNAPSHOT_ID_COLUMN not in df.columns:
        return {}

    snapshot_sets: dict[InstrumentId, set[str]] = {}
    for row in df.select(["instrument_id", _SOURCE_SNAPSHOT_ID_COLUMN]).to_dicts():
        iid_raw = row.get("instrument_id")
        if iid_raw is None:
            continue
        iid = InstrumentId(int(iid_raw))
        if exclude_instrument_id is not None and iid == exclude_instrument_id:
            continue

        snapshot_raw = row.get(_SOURCE_SNAPSHOT_ID_COLUMN)
        if snapshot_raw is None:
            continue
        snapshot_id = str(snapshot_raw).strip()
        if snapshot_id == "":
            continue
        snapshot_sets.setdefault(iid, set()).add(snapshot_id)
    return snapshot_sets


def _aggregate_source_snapshot_ids_by_instrument(
    df: pl.DataFrame,
    *,
    exclude_instrument_id: InstrumentId | None = None,
) -> dict[InstrumentId, str]:
    """Return one stable snapshot ID per instrument from exact source IDs."""
    result: dict[InstrumentId, str] = {}
    snapshot_sets = _source_snapshot_sets_by_instrument(
        df,
        exclude_instrument_id=exclude_instrument_id,
    )
    for iid, snapshot_ids in snapshot_sets.items():
        aggregate = aggregate_source_snapshot_id(snapshot_ids)
        if aggregate is not None:
            result[iid] = aggregate
    return result


# ---------------------------------------------------------------------------
# ProviderBackedDataFeed
# ---------------------------------------------------------------------------


class ProviderBackedDataFeed:
    """
    DataFeed backed by DataProvider Protocol.

    通过 DataProvider.get_bars() 加载全量行情数据，
    通过 DataProvider.get_schedule() 获取交易日历。
    适用于 ServiceBackedDataProvider 等实现。

    构造参数由 app 层注入。
    """

    def __init__(
        self,
        provider: DataProvider,
        *,
        tickers: tuple[str, ...],
        start_date: str,
        end_date: str,
        id_map: dict[str, InstrumentId],
        benchmark_id: InstrumentId | None = None,
    ) -> None:
        self._provider = provider
        self._tickers = tickers
        self._start_date = start_date
        self._end_date = end_date
        self._id_map = id_map
        self._benchmark_id = benchmark_id
        # Lazy-loaded caches
        self._bars_df: pl.DataFrame | None = None
        self._trading_days_cache: list[str] | None = None
        self._source_snapshot_ids_cache: dict[InstrumentId, str] | None = None

    def _load_bars(self) -> pl.DataFrame:
        """Lazy-load all bar data via DataProvider.get_bars()."""
        if self._bars_df is not None:
            return self._bars_df

        query = BarQuery(
            instruments=list(self._tickers),
            start=self._start_date,
            end=self._end_date,
        )
        result = self._provider.get_bars(query)
        self._bars_df = self._ensure_prev_close(result)
        return self._bars_df

    @staticmethod
    def _ensure_prev_close(df: pl.DataFrame) -> pl.DataFrame:
        """
        若数据不含 prev_close，则通过 shift(1) 按标的计算。

        首日（每个 instrument_id 的第一行）无历史 close，
        fill_null(close) 用当日 close 填充，即 prev_close == close。
        """
        if df.is_empty() or "prev_close" in df.columns:
            return df
        return df.sort(["instrument_id", "trade_date"]).with_columns(
            pl.col("close")
            .shift(1)
            .over("instrument_id")
            .fill_null(pl.col("close"))
            .alias("prev_close"),
        )

    # -- public interface --------------------------------------------------

    def trading_days(self) -> list[str]:
        """Return sorted trading days from DataProvider.get_schedule()."""
        if self._trading_days_cache is not None:
            return self._trading_days_cache

        schedule = self._provider.get_schedule(self._start_date, self._end_date)
        if "trade_date" in schedule.columns:
            self._trading_days_cache = sorted(
                schedule["trade_date"].cast(pl.String).to_list()
            )
        else:
            self._trading_days_cache = []
        return self._trading_days_cache

    def get_slice(self, date: str) -> Slice:
        """Build Slice for the given date from pre-loaded bar data."""
        df = self._load_bars()
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        step_time = date_obj.replace(
            hour=15,
            minute=0,
            second=0,
            tzinfo=UTC,
        )

        day_df = df.filter(pl.col("trade_date") == date)
        day_source_snapshot_ids = _aggregate_source_snapshot_ids_by_instrument(
            day_df,
            exclude_instrument_id=self._benchmark_id,
        )

        bars: dict[InstrumentId, _MarketSnapshot] = {}
        benchmark_close: float | None = None

        for row in day_df.to_dicts():
            iid_raw = row.get("instrument_id")
            iid = InstrumentId(int(iid_raw)) if iid_raw is not None else None
            if iid is None:
                continue

            if self._benchmark_id is not None and iid == self._benchmark_id:
                benchmark_close = float(row["close"])
                continue  # benchmark 不进入 bars

            bars[iid] = _row_to_snapshot(date, iid, row)

        return Slice(
            trade_date=date,
            step_time=step_time,
            bars=bars,
            benchmark_close=benchmark_close,
            source_snapshot_ids={
                iid: day_source_snapshot_ids[iid]
                for iid in bars
                if iid in day_source_snapshot_ids
            },
        )

    def source_snapshot_ids(self) -> dict[InstrumentId, str]:
        """Return stable source snapshot IDs exposed by the provider, if any."""
        if self._source_snapshot_ids_cache is not None:
            return self._source_snapshot_ids_cache

        self._source_snapshot_ids_cache = _aggregate_source_snapshot_ids_by_instrument(
            self._load_bars(),
            exclude_instrument_id=self._benchmark_id,
        )
        return self._source_snapshot_ids_cache

    def get_history(
        self,
        instrument_ids: list[InstrumentId],
        as_of_date: str,
        lookback_days: int,
    ) -> pl.DataFrame:
        """
        获取指定标的历史行情窗口。

        从预加载的 _bars_df 中过滤:
        - instrument_id IN (instrument_ids)
        - trade_date < as_of_date
        - 按 trade_date desc 限制 lookback_days 行
        返回按 (instrument_id, trade_date) 排序的 DataFrame。
        """
        df = self._load_bars()
        if df.is_empty() or lookback_days <= 0:
            return df.clear()

        iid_values = [int(iid) for iid in instrument_ids]
        filtered = df.filter(
            (pl.col("instrument_id").is_in(iid_values))
            # PIT: strict < 排除当日数据，防止未来数据泄露到因子回看窗口
            & (pl.col("trade_date") < as_of_date),
        )

        # 按 instrument_id 分组，每组取最近 lookback_days 个交易日
        result = (
            filtered.sort(["instrument_id", "trade_date"])
            .group_by("instrument_id", maintain_order=True)
            .tail(lookback_days)
        )

        return result
