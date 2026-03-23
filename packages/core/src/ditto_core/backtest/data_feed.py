"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 从 execution/reality/market.py 导入.
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
ParquetDataFeed 是基于 parquet 文件的 DataFeed 实现.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import polars as pl

from ditto_core.execution.reality.market import MarketSnapshot

__all__ = ["DataFeed", "MarketSnapshot", "ParquetDataFeed", "Slice"]


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
    bars: dict[str, MarketSnapshot]
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
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._instrument_ids = list(instrument_ids)
        self._start_date = start_date
        self._end_date = end_date
        # Lazy-loaded: instrument_id → pl.DataFrame
        self._data: dict[str, pl.DataFrame] | None = None

    # -- private helpers ---------------------------------------------------

    def _load(self) -> dict[str, pl.DataFrame]:
        """Lazy-load all parquet files into memory."""
        if self._data is not None:
            return self._data

        data: dict[str, pl.DataFrame] = {}
        for iid in self._instrument_ids:
            path = self._data_dir / f"{iid}.parquet"
            if not path.exists():
                continue
            df = pl.read_parquet(path)
            data[iid] = df
        self._data = data
        return data

    @staticmethod
    def _row_to_snapshot(
        date: str,
        iid: str,
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
            limit_up=(
                float(row["limit_up"]) if row.get("limit_up") is not None else None
            ),
            limit_down=(
                float(row["limit_down"]) if row.get("limit_down") is not None else None
            ),
            avg_volume_20d=(
                float(row["avg_volume_20d"])
                if row.get("avg_volume_20d") is not None
                else None
            ),
        )

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

        bars: dict[str, MarketSnapshot] = {}
        for iid, df in data.items():
            row = df.filter(pl.col("trade_date") == date)
            if row.height == 0:
                continue
            bars[iid] = self._row_to_snapshot(date, iid, row.to_dicts()[0])

        return Slice(trade_date=date, step_time=step_time, bars=bars)
