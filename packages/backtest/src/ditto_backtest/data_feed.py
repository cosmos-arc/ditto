"""
DataFeed — 市场数据切片协议 + 数据容器.

MarketSnapshot 是 kernel trading 类型，仅用于数据容器字段。
Slice 是某日所有标的的聚合视图, 由 DataFeed 提供.
ProviderBackedDataFeed 通过 DataProvider Protocol 获取数据.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import polars as pl
from ditto_data.provider import BarQuery, DataProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot as _MarketSnapshot

from ditto_backtest.provenance import aggregate_source_snapshot_id

__all__ = [
    "ClassificationSnapshotFn",
    "DataFeed",
    "FeedInputRequirements",
    "FundamentalSnapshotFn",
    "ProviderBackedDataFeed",
    "Slice",
    "SnapshotProviders",
]

_SOURCE_SNAPSHOT_ID_COLUMN = "source_snapshot_id"

# 基本面快照函数类型 — backtest 只委托；PIT 查询/因子计算由 application 层闭包提供。
# 与 ditto_application.processes.execution.fundamental_snapshot 同型（结构相等）。
FundamentalSnapshotFn = Callable[[Sequence[InstrumentId], date], pl.DataFrame]

# 分类快照函数类型 — backtest 只委托；PIT 行业查询由 application 层闭包提供。
# 与 ditto_application.processes.execution.classification_snapshot 同型（结构相等）。
ClassificationSnapshotFn = Callable[[Sequence[InstrumentId], date], pl.DataFrame]


@dataclass(frozen=True)
class SnapshotProviders:
    """
    ProviderBackedDataFeed 的截面快照数据通道集合.

    backtest 只做数据通道委托;PIT 查询与因子/分类列预计算由 application 层
    注入的闭包负责。各快照语义独立(基本面 vs 行业分类),分别命名。
    """

    fundamental: FundamentalSnapshotFn | None = None
    classification: ClassificationSnapshotFn | None = None
    require_source_snapshot_lineage: bool = False
    market: Callable[[pl.DataFrame], pl.DataFrame] | None = None
    requirements: FeedInputRequirements | None = None


@dataclass(frozen=True)
class FeedInputRequirements:
    """Complete frozen-pool inputs for an ordinary catalog run."""

    start_date: str
    warmup_days: int
    knowledge_lag_days: int = 1
    benchmark_ticker: str | None = None


# get_fundamental_snapshot 无注入 fn 或无数据时返回的空 schema。
_EMPTY_FUNDAMENTAL_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "roe": pl.Float64,
    "net_margin": pl.Float64,
    "eps": pl.Float64,
}

# get_classification_snapshot 无注入 fn 或无数据时返回的空 schema。
# sector_id 是行业分类代码（如申万 "801010"），供 stock_sector_rotation 结构列
# 校验与因子中性化（neutralize_by="sector_id"）使用。
_EMPTY_CLASSIFICATION_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "sector_id": pl.Utf8,
}


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

    def get_fundamental_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        获取指定标的在 as_of_date 的基本面截面快照（PIT）。

        返回 schema: instrument_id, roe, net_margin, eps。
        无数据返回空 schema DataFrame。backtest 只委托注入的 fn，
        不含 PIT 查询/因子计算业务逻辑（由 application 层闭包提供）。
        """
        ...

    def get_classification_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        获取指定标的在 as_of_date 的行业分类截面快照（PIT）。

        返回 schema: instrument_id, sector_id。
        无数据返回空 schema DataFrame。backtest 只委托注入的 fn，
        PIT 行业查询（industry_mapping）由 application 层闭包提供。
        sector_id 供 stock_sector_rotation 结构列校验与因子中性化使用。
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
    source_columns = [
        column
        for column in df.columns
        if column == _SOURCE_SNAPSHOT_ID_COLUMN
        or column.endswith("_source_snapshot_id")
    ]
    for row in df.select(["instrument_id", *source_columns]).to_dicts():
        iid_raw = row.get("instrument_id")
        if iid_raw is None:
            continue
        iid = InstrumentId(int(iid_raw))
        if exclude_instrument_id is not None and iid == exclude_instrument_id:
            continue

        for column in source_columns:
            snapshot_raw = row.get(column)
            if snapshot_raw is not None and (snapshot_id := str(snapshot_raw).strip()):
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
        snapshot_providers: SnapshotProviders | None = None,
    ) -> None:
        self._provider = provider
        self._tickers = tickers
        self._start_date = start_date
        self._end_date = end_date
        self._id_map = id_map
        self._benchmark_id = benchmark_id
        self._snapshots = snapshot_providers or SnapshotProviders()
        self._requirements = self._snapshots.requirements
        self._benchmark_ticker = (
            self._requirements.benchmark_ticker if self._requirements else None
        )
        self._require_source_snapshot_lineage = (
            self._snapshots.require_source_snapshot_lineage
        )
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
            with_execution_state=self._requirements is not None,
        )
        result = self._provider.get_bars(query)
        if self._snapshots.market is not None:
            result = self._snapshots.market(result)
        if self._benchmark_ticker is not None:
            benchmark = self._provider.get_bars(
                BarQuery(
                    instruments=(self._benchmark_ticker,),
                    start=self._requirements.start_date
                    if self._requirements
                    else self._start_date,
                    end=self._end_date,
                    dataset_id="index_daily",
                )
            )
            result = pl.concat([result, benchmark], how="diagonal_relaxed")
        self._bars_df = self._ensure_prev_close(result)
        self._validate_required_source_snapshot_lineage(self._bars_df)
        return self._bars_df

    def validate_inputs(self) -> None:
        """Reject missing members/dates before the first order or return."""
        requirements = self._requirements
        if requirements is None:
            return
        days = self.trading_days()
        cutoff = (
            date.fromisoformat(requirements.start_date)
            - timedelta(days=requirements.knowledge_lag_days)
        ).isoformat()
        prior = [day for day in days if day < cutoff]
        if len(prior) < requirements.warmup_days:
            raise ValueError(
                f"insufficient warmup calendar before {cutoff}: {len(prior)} < "
                + f"{requirements.warmup_days}"
            )
        run_days = [
            day for day in days if requirements.start_date <= day <= self._end_date
        ]
        if not run_days:
            raise ValueError("backtest interval contains no trading days")
        required_days = (
            prior[-requirements.warmup_days :] + run_days
            if requirements.warmup_days
            else run_days
        )
        frame = self._load_bars()
        expected = [
            (int(iid), day) for iid in self._id_map.values() for day in required_days
        ]
        if self._benchmark_id is not None:
            expected.extend((int(self._benchmark_id), day) for day in run_days)
        expected_frame = pl.DataFrame(
            expected,
            schema={"instrument_id": pl.Int64, "trade_date": pl.String},
            orient="row",
        )
        if frame.is_empty():
            raise ValueError(f"missing backtest inputs: {expected[:10]}")
        actual = frame.with_columns(pl.col("trade_date").cast(pl.String))
        missing = expected_frame.join(
            actual.select("instrument_id", "trade_date"),
            on=["instrument_id", "trade_date"],
            how="anti",
        )
        if not missing.is_empty():
            raise ValueError(
                f"missing backtest member/date inputs ({missing.height}): "
                + f"{missing.head(10).to_dicts()}"
            )
        if actual.select("instrument_id", "trade_date").is_duplicated().any():
            raise ValueError("duplicate backtest member/date inputs")
        relevant = actual.join(
            expected_frame, on=["instrument_id", "trade_date"], how="semi"
        )
        bad = relevant.filter(
            pl.any_horizontal(
                [
                    pl.col(column).is_null()
                    | ~pl.col(column).is_finite()
                    | (pl.col(column) <= 0)
                    for column in ("open", "high", "low", "close")
                ]
            )
        )
        if not bad.is_empty():
            raise ValueError(
                "invalid OHLC: "
                + str(bad.select("instrument_id", "trade_date").head(10).to_dicts())
            )
        if (
            _SOURCE_SNAPSHOT_ID_COLUMN not in relevant.columns
            or relevant[_SOURCE_SNAPSHOT_ID_COLUMN].null_count()
        ):
            raise ValueError(
                "source snapshot lineage is incomplete for required backtest inputs"
            )
        self.get_history(list(self._id_map.values()), cutoff, requirements.warmup_days)

    def _validate_required_source_snapshot_lineage(self, df: pl.DataFrame) -> None:
        """Fail closed when a research/context-bound run has incomplete bar lineage."""
        if not self._require_source_snapshot_lineage:
            return
        expected = {
            iid
            for ticker, iid in self._id_map.items()
            if ticker in self._tickers and iid != self._benchmark_id
        }
        if _SOURCE_SNAPSHOT_ID_COLUMN not in df.columns:
            missing = sorted(int(item) for item in expected)
        else:
            relevant = df.filter(
                pl.col("instrument_id").is_in([int(item) for item in expected])
            )
            observed = {
                InstrumentId(int(item))
                for item in relevant["instrument_id"].unique().to_list()
            }
            unresolved = {
                InstrumentId(int(item))
                for item in relevant.filter(
                    pl.col(_SOURCE_SNAPSHOT_ID_COLUMN).is_null()
                    | (
                        pl.col(_SOURCE_SNAPSHOT_ID_COLUMN)
                        .cast(pl.String)
                        .str.strip_chars()
                        == ""
                    )
                )["instrument_id"]
                .unique()
                .to_list()
            }
            missing = sorted(int(item) for item in (expected - observed) | unresolved)
        if missing:
            rendered = ", ".join(str(item) for item in missing)
            raise ValueError(
                "source snapshot lineage is incomplete for instruments: " + rendered
            )

    @staticmethod
    def _ensure_prev_close(df: pl.DataFrame) -> pl.DataFrame:
        """
        若数据不含 prev_close，则通过 shift(1) 按标的计算。

        首日（每个 instrument_id 的第一行）无历史 close，
        fill_null(close) 用当日 close 填充，即 prev_close == close。
        """
        if df.is_empty() or "prev_close" in df.columns:
            return df
        if "pre_close" in df.columns:
            return df.with_columns(pl.col("pre_close").alias("prev_close"))
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

        day_df = df.filter(pl.col("trade_date").cast(pl.String) == date)
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
        if self._requirements is not None and lookback_days > 0:
            tickers = tuple(
                ticker for ticker, iid in self._id_map.items() if iid in instrument_ids
            )
            df = self._provider.get_bars(
                BarQuery(
                    instruments=tickers,
                    start=self._start_date,
                    end=(
                        date.fromisoformat(as_of_date) - timedelta(days=1)
                    ).isoformat(),
                    adj="qfq",
                    asof=as_of_date,
                )
            )
            if not df.is_empty():
                if "knowledge_date" not in df.columns:
                    raise ValueError("missing history knowledge_date")
                df = df.filter(
                    pl.col("knowledge_date").cast(pl.Date)
                    <= date.fromisoformat(as_of_date)
                )
        else:
            df = self._load_bars()
        if self._requirements is not None and df.is_empty() and lookback_days > 0:
            raise ValueError(
                f"missing visible history before {as_of_date}: {instrument_ids}"
            )
        if df.is_empty() or lookback_days <= 0:
            return df.clear()

        iid_values = [int(iid) for iid in instrument_ids]
        cutoff = date.fromisoformat(as_of_date)
        filtered = df.filter(
            (pl.col("instrument_id").is_in(iid_values))
            # PIT: strict < 排除当日数据，防止未来数据泄露到因子回看窗口
            & (pl.col("trade_date").cast(pl.Date) < cutoff),
        )

        # 按 instrument_id 分组，每组取最近 lookback_days 个交易日
        result = (
            filtered.sort(["instrument_id", "trade_date"])
            .group_by("instrument_id", maintain_order=True)
            .tail(lookback_days)
        )
        if self._requirements is not None:
            counts = dict(result.group_by("instrument_id").len().iter_rows())
            missing = {
                int(iid): counts.get(int(iid), 0)
                for iid in instrument_ids
                if counts.get(int(iid), 0) < lookback_days
            }
            if missing:
                raise ValueError(
                    f"insufficient warmup before {as_of_date}, "
                    + f"require {lookback_days}: "
                    + f"{missing}"
                )
        return result

    def get_fundamental_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        委托注入的 fundamental_snapshot_fn；未注入返回空 schema DataFrame.

        backtest 只做数据通道委托，PIT 查询与因子列预计算由 application 层
        注入的闭包（build_fundamental_snapshot_fn）负责。
        """
        fn = self._snapshots.fundamental
        if fn is None:
            return pl.DataFrame(schema=_EMPTY_FUNDAMENTAL_SCHEMA)
        return fn(instrument_ids, as_of_date)

    def get_classification_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        委托注入的 classification_snapshot_fn；未注入返回空 schema DataFrame.

        backtest 只做数据通道委托，PIT 行业查询由 application 层注入的闭包
        （build_classification_snapshot_fn）负责。
        """
        fn = self._snapshots.classification
        if fn is None:
            return pl.DataFrame(schema=_EMPTY_CLASSIFICATION_SCHEMA)
        return fn(instrument_ids, as_of_date)
