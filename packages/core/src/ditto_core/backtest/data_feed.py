"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 从 execution/reality/market.py 导入.
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
ParquetDataFeed 是基于 parquet 文件的 DataFeed 实现.
ProviderBackedDataFeed 通过 kernel.DataProvider Protocol 获取数据.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import polars as pl
from ditto_kernel.identity import InstrumentId
from ditto_kernel.provider import BarQuery

from ditto_core.execution.reality.market import MarketSnapshot

if TYPE_CHECKING:
    from ditto_kernel.provider import DataProvider

__all__ = [
    "DataFeed",
    "MarketSnapshot",
    "ParquetDataFeed",
    "ProviderBackedDataFeed",
    "Slice",
]


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

    """

    trade_date: str
    step_time: datetime
    bars: dict[InstrumentId, MarketSnapshot]
    benchmark_close: float | None = None


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


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _row_to_snapshot(
    date: str,
    iid: InstrumentId,
    row: dict[str, Any],
) -> MarketSnapshot:
    """Convert a polars row dict (from ``to_dicts()``) to a MarketSnapshot."""
    return MarketSnapshot(
        trade_date=date,
        instrument_id=iid,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        prev_close=float(row["prev_close"]),
        volume=float(row["volume"]),
        amount=float(row["amount"]),
        is_suspended=bool(row["is_suspended"]),
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


# ---------------------------------------------------------------------------
# ParquetDataFeed
# ---------------------------------------------------------------------------


class ParquetDataFeed:
    """
    Parquet-backed DataFeed — reads market data from parquet files.

    每个标的对应一个 parquet 文件，命名约定: ``{instrument_id}.parquet``.
    文件须包含以下列: trade_date, open, high, low, close, prev_close,
    volume, amount, is_suspended. 可选列: limit_up, limit_down, avg_volume_20d.
    """

    def __init__(
        self,
        data_dir: str | Path,
        instrument_ids: list[InstrumentId],
        start_date: str,
        end_date: str,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._instrument_ids = list(instrument_ids)
        self._start_date = start_date
        self._end_date = end_date
        # Lazy-loaded: instrument_id → pl.DataFrame
        self._data: dict[InstrumentId, pl.DataFrame] | None = None

    # -- private helpers ---------------------------------------------------

    def _load(self) -> dict[InstrumentId, pl.DataFrame]:
        """Lazy-load all parquet files into memory."""
        if self._data is not None:
            return self._data

        data: dict[InstrumentId, pl.DataFrame] = {}
        for iid in self._instrument_ids:
            path = self._data_dir / f"{iid}.parquet"
            if not path.exists():
                continue
            df = pl.read_parquet(path)
            data[iid] = df
        self._data = data
        return data

    # -- public interface --------------------------------------------------

    def trading_days(self) -> list[str]:
        """Return sorted list of unique trade dates in [start_date, end_date]."""
        data = self._load()
        all_dates: set[str] = set()
        for df in data.values():
            dates = df["trade_date"].cast(pl.String)
            all_dates.update(dates.to_list())

        filtered = {d for d in all_dates if self._start_date <= d <= self._end_date}
        return sorted(filtered)

    def get_slice(self, date: str) -> Slice:
        """
        Build Slice with all instruments' data for the given date.

        step_time is set to 15:00:00 (A-share close).
        Instruments with no data for the date are excluded from bars.
        """
        data = self._load()
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        step_time = date_obj.replace(hour=15, minute=0, second=0)

        bars: dict[InstrumentId, MarketSnapshot] = {}
        for iid, df in data.items():
            row = df.filter(pl.col("trade_date") == date)
            if row.height == 0:
                continue
            bars[iid] = _row_to_snapshot(date, iid, row.to_dicts()[0])

        return Slice(trade_date=date, step_time=step_time, bars=bars)


# ---------------------------------------------------------------------------
# ProviderBackedDataFeed
# ---------------------------------------------------------------------------


class ProviderBackedDataFeed:
    """
    DataFeed backed by kernel.DataProvider Protocol.

    通过 DataProvider.get_bars() 加载全量行情数据，
    通过 DataProvider.get_schedule() 获取交易日历。
    适用于 BacktestProvider / LiveProvider 等实现。

    构造参数由 app 层（port/registry）注入。
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
        if isinstance(result, pl.DataFrame):
            self._bars_df = result
        else:
            self._bars_df = pl.DataFrame()
        return self._bars_df

    # -- public interface --------------------------------------------------

    def trading_days(self) -> list[str]:
        """Return sorted trading days from DataProvider.get_schedule()."""
        if self._trading_days_cache is not None:
            return self._trading_days_cache

        schedule = self._provider.get_schedule(self._start_date, self._end_date)
        if isinstance(schedule, pl.DataFrame) and "trade_date" in schedule.columns:
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
        step_time = date_obj.replace(hour=15, minute=0, second=0)

        day_df = df.filter(pl.col("trade_date") == date)

        bars: dict[InstrumentId, MarketSnapshot] = {}
        benchmark_close: float | None = None

        for row in day_df.to_dicts():
            iid_raw = row.get("instrument_id")
            iid = InstrumentId(int(iid_raw)) if iid_raw is not None else None
            if iid is None:
                continue

            bars[iid] = _row_to_snapshot(date, iid, row)

            if self._benchmark_id is not None and iid == self._benchmark_id:
                benchmark_close = float(row["close"])

        return Slice(
            trade_date=date,
            step_time=step_time,
            bars=bars,
            benchmark_close=benchmark_close,
        )
