"""基于 DataHub Metadata/MarketService 的 DataFeed 适配器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import polars as pl
from ditto_core.backtest.data_feed import Slice
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_kernel.enums import AssetClass
from ditto_kernel.identity import InstrumentId

__all__ = ["MarketServiceDataFeed", "MarketServiceDataFeedConfig"]


@dataclass(frozen=True)
class MarketServiceDataFeedConfig:
    """市场服务 DataFeed 的静态装配参数。"""

    universe_id: str
    asset_class: str
    start_date: str
    end_date: str
    benchmark_id: InstrumentId | None = None
    source: str = "tushare"


class MarketServiceDataFeed:
    """将 DataHub 市场数据服务适配为 Core ``DataFeed``。"""

    def __init__(
        self,
        *,
        metadata_service: MetadataService,
        market_service: MarketService,
        config: MarketServiceDataFeedConfig,
    ) -> None:
        self._metadata_service = metadata_service
        self._market_service = market_service
        self._config = config
        self._asset_class = AssetClass(config.asset_class)
        self._trading_days: list[str] | None = None
        self._bars_by_date: dict[str, dict[InstrumentId, MarketSnapshot]] | None = None
        self._benchmark_close_by_date: dict[str, float] | None = None
        self._display_map: dict[InstrumentId, str] = field(default_factory=dict)

    def trading_days(self) -> list[str]:
        """返回回测区间内交易日列表。"""
        self._ensure_loaded()
        return list(self._trading_days or [])

    @property
    def display_map(self) -> dict[InstrumentId, str]:
        """返回 InstrumentId → standard_ticker 映射。"""
        self._ensure_loaded()
        return dict(self._display_map)

    def get_slice(self, date: str) -> Slice:
        """返回指定日期的市场切片。"""
        self._ensure_loaded()
        step_time = datetime.strptime(date, "%Y-%m-%d").replace(
            hour=15,
            minute=0,
            second=0,
        )
        bars = dict((self._bars_by_date or {}).get(date, {}))
        benchmark_close = (self._benchmark_close_by_date or {}).get(date)
        return Slice(
            trade_date=date,
            step_time=step_time,
            bars=bars,
            benchmark_close=benchmark_close,
        )

    def _ensure_loaded(self) -> None:
        if self._trading_days is not None:
            return

        calendar_df = self._metadata_service.list_calendar_range(
            self._config.start_date,
            self._config.end_date,
            only_open=True,
        )
        trading_days = self._extract_trading_days(calendar_df)
        query_start = self._resolve_query_start(calendar_df)

        universe_ids = self._metadata_service.get_universe(
            self._config.universe_id,
            asof=self._config.start_date,
        )
        display_map = self._build_display_map(universe_ids)
        bars_df = self._load_universe_bars(universe_ids, query_start)

        if not trading_days:
            trading_days = self._extract_trading_days_from_bars(bars_df)

        self._trading_days = trading_days
        self._display_map = display_map
        self._bars_by_date = self._build_bars_by_date(
            bars_df,
            trading_days=set(trading_days),
        )
        self._benchmark_close_by_date = self._load_benchmark_close_map(
            query_start,
            trading_days=set(trading_days),
        )

    def _resolve_query_start(self, calendar_df: pl.DataFrame) -> str:
        if "prev_trade_date" not in calendar_df.columns or calendar_df.is_empty():
            return self._config.start_date
        prev_trade_dates = [
            value
            for value in calendar_df.select(pl.col("prev_trade_date").cast(pl.String))
            .to_series()
            .to_list()
            if value is not None
        ]
        if not prev_trade_dates:
            return self._config.start_date
        return prev_trade_dates[0]

    def _extract_trading_days(self, calendar_df: pl.DataFrame) -> list[str]:
        if "trade_date" not in calendar_df.columns or calendar_df.is_empty():
            return []
        dates = [
            value
            for value in calendar_df.select(pl.col("trade_date").cast(pl.String))
            .to_series()
            .to_list()
            if value is not None
        ]
        return sorted(dates)

    def _extract_trading_days_from_bars(self, bars_df: pl.DataFrame) -> list[str]:
        if bars_df.is_empty() or "trade_date" not in bars_df.columns:
            return []
        dates = [
            value
            for value in bars_df.select(pl.col("trade_date").cast(pl.String).unique())
            .to_series()
            .to_list()
            if value is not None
            and self._config.start_date <= value <= self._config.end_date
        ]
        return sorted(dates)

    def _build_display_map(self, instrument_ids: list[int]) -> dict[InstrumentId, str]:
        """构建 InstrumentId → standard_ticker 映射。"""
        display_map: dict[InstrumentId, str] = {}
        for iid in instrument_ids:
            instrument_id = InstrumentId(iid)
            instrument = self._metadata_service.get_instrument(iid)
            if instrument is not None:
                ticker = instrument.get("ticker", str(iid))
                exchange = instrument.get("exchange", "")
                key = f"{ticker}.{exchange}" if exchange else str(iid)
                display_map[instrument_id] = key
            else:
                display_map[instrument_id] = str(iid)
        return display_map

    def _load_universe_bars(
        self,
        instrument_ids: list[int],
        start_date: str,
    ) -> pl.DataFrame:
        if not instrument_ids:
            return pl.DataFrame()
        return self._market_service.list_bars(
            instrument_ids,
            start=start_date,
            end=self._config.end_date,
            asset_class=self._asset_class.value,
        )

    def _build_bars_by_date(
        self,
        bars_df: pl.DataFrame,
        *,
        trading_days: set[str],
    ) -> dict[str, dict[InstrumentId, MarketSnapshot]]:
        if bars_df.is_empty():
            return {}

        prepared = self._prepare_bars_frame(bars_df)
        bars_by_date: dict[str, dict[InstrumentId, MarketSnapshot]] = {}
        for row in prepared.to_dicts():
            trade_date = self._read_str(row, "trade_date")
            if trade_date not in trading_days:
                continue
            instrument_id = InstrumentId(self._read_int(row, "instrument_id"))
            date_bucket = bars_by_date.setdefault(trade_date, {})
            date_bucket[instrument_id] = self._row_to_snapshot(instrument_id, row)
        return bars_by_date

    def _load_benchmark_close_map(
        self,
        start_date: str,
        *,
        trading_days: set[str],
    ) -> dict[str, float]:
        if self._config.benchmark_id is None:
            return {}

        benchmark_instrument_id = int(self._config.benchmark_id)
        benchmark_asset_class = self._resolve_benchmark_asset_class(
            benchmark_instrument_id,
        )
        benchmark_df = self._market_service.list_bars(
            [benchmark_instrument_id],
            start=start_date,
            end=self._config.end_date,
            asset_class=benchmark_asset_class.value,
        )
        if benchmark_df.is_empty():
            return {}

        prepared = self._prepare_bars_frame(benchmark_df)
        close_map: dict[str, float] = {}
        for row in prepared.to_dicts():
            trade_date = self._read_str(row, "trade_date")
            if trade_date not in trading_days:
                continue
            close_map[trade_date] = self._read_float(row.get("close"))
        return close_map

    def _resolve_benchmark_asset_class(self, instrument_id: int) -> AssetClass:
        instrument = self._metadata_service.get_instrument(instrument_id)
        if instrument is None:
            return AssetClass.INDEX
        asset_class = instrument.get("asset_class")
        if not isinstance(asset_class, str):
            return AssetClass.INDEX
        try:
            return AssetClass(asset_class)
        except ValueError:
            return AssetClass.INDEX

    def _prepare_bars_frame(self, bars_df: pl.DataFrame) -> pl.DataFrame:
        prepared = bars_df.with_columns(pl.col("trade_date").cast(pl.String)).sort(
            ["instrument_id", "trade_date"],
        )
        return prepared.with_columns(
            pl.col("close").shift(1).over("instrument_id").alias("prev_close"),
        ).with_columns(
            pl.col("prev_close").fill_null(pl.col("close")),
        )

    def _row_to_snapshot(
        self,
        instrument_id: InstrumentId,
        row: dict[str, object],
    ) -> MarketSnapshot:
        close = self._read_float(row.get("close"))
        amount = row.get("amount")
        if amount is None:
            amount_value = close * self._read_float(row.get("volume"))
        else:
            amount_value = self._read_float(amount)
        return MarketSnapshot(
            trade_date=self._read_str(row, "trade_date"),
            instrument_id=instrument_id,
            open=self._read_float(row.get("open")),
            high=self._read_float(row.get("high")),
            low=self._read_float(row.get("low")),
            close=close,
            prev_close=self._read_float(row.get("prev_close"), default=close),
            volume=self._read_float(row.get("volume")),
            amount=amount_value,
            is_suspended=bool(row.get("is_suspended", False)),
            limit_up=self._read_optional_float(row.get("limit_up")),
            limit_down=self._read_optional_float(row.get("limit_down")),
            avg_volume_20d=self._read_optional_float(row.get("avg_volume_20d")),
        )

    @staticmethod
    def _read_str(row: dict[str, object], key: str) -> str:
        value = row.get(key)
        if isinstance(value, str):
            return value
        if value is None:
            msg = f"缺失字段: {key}"
            raise ValueError(msg)
        return str(value)

    @staticmethod
    def _read_int(row: dict[str, object], key: str) -> int:
        value = row.get(key)
        if isinstance(value, int):
            return value
        if value is None:
            msg = f"缺失字段: {key}"
            raise ValueError(msg)
        return int(str(value))

    @staticmethod
    def _read_float(value: object, *, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        return float(str(value))

    @staticmethod
    def _read_optional_float(value: object) -> float | None:
        if value is None:
            return None
        return MarketServiceDataFeed._read_float(value)
