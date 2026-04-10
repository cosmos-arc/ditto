"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 从 execution/reality/market.py 导入.
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
ProviderBackedDataFeed 通过 DataProvider Protocol 获取数据.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import polars as pl
from ditto_data.provider import BarQuery, DataProvider
from ditto_kernel.identity import InstrumentId

from ditto_engine.execution.reality.market import MarketSnapshot

__all__ = [
    "DataFeed",
    "MarketSnapshot",
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
    close = float(row["close"])
    volume = float(row.get("volume", 0))
    raw_amount = row.get("amount")
    amount = float(raw_amount) if raw_amount is not None else close * volume
    return MarketSnapshot(
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

        bars: dict[InstrumentId, MarketSnapshot] = {}
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
        )
