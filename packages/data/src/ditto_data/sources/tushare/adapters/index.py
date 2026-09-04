"""指数数据适配器."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import INDEX_BASIC_MAPPING
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


@dataclass(frozen=True, slots=True)
class _GlobalIndexSpec:
    timezone: str
    currency: str
    close_time: time


_GLOBAL_INDEX_SPECS: dict[str, _GlobalIndexSpec] = {
    "SPX": _GlobalIndexSpec("America/New_York", "USD", time(16, 0)),
    "IXIC": _GlobalIndexSpec("America/New_York", "USD", time(16, 0)),
    "DJI": _GlobalIndexSpec("America/New_York", "USD", time(16, 0)),
    "GDAXI": _GlobalIndexSpec("Europe/Berlin", "EUR", time(17, 30)),
    "N225": _GlobalIndexSpec("Asia/Tokyo", "JPY", time(15, 30)),
}
_TSE_CLOSE_EXTENSION_DATE = date(2024, 11, 5)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_INDEX_DAILY_FIELDS = (
    "ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg"
)
_SW_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,change,pct_change,vol,amount"


def _global_session_close_utc(code: str, trade_date: date) -> datetime:
    spec = _GLOBAL_INDEX_SPECS[code]
    close_time = spec.close_time
    if code == "N225" and trade_date < _TSE_CLOSE_EXTENSION_DATE:
        close_time = time(15, 0)
    return datetime.combine(
        trade_date,
        close_time,
        tzinfo=ZoneInfo(spec.timezone),
    ).astimezone(UTC)


_GLOBAL_INDEX_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source_ticker": pl.String,
    "trade_date": pl.Date,
    "event_time": pl.Datetime("us", "UTC"),
    "published_at": pl.Datetime("us", "UTC"),
    "available_at": pl.Datetime("us", "UTC"),
    "knowledge_date": pl.Date,
    "timezone": pl.String,
    "currency": pl.String,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "change": pl.Float64,
    "pct_change": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


class IndexTushareAdapter(BaseTushareAdapter):
    """
    指数 Tushare 适配器.

    专门处理指数相关数据获取，包括：
    - 指数基本信息
    - 指数日线数据

    注意：
    - Tushare index_daily API 必须指定 ts_code 参数
    - 不支持仅用 trade_date 获取所有指数数据
    - 指数代码列表由编排层提供，不在 Adapter 层硬编码
    """

    @traced("source.tushare.fetch_index_basic")
    def fetch_basic(self) -> pl.DataFrame:
        """
        获取指数基本信息.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SH")
            - ticker: Display ticker (e.g., "000001")
            - name: Index name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare index basic info",
            event="tushare_index_basic_fetch_start",
        )

        with tushare_fetch_error_handler("index_basic", "index_basic"):
            response = self._client.query(
                api_name="index_basic",
                fields="ts_code,name,market,list_date",
            )

            return TushareDataTransformer.transform(
                response, "index_basic", INDEX_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_index_daily")
    def fetch_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数日线 OHLCV 数据.

        支持两种查询模式：
        - 按日期批量：指定 trade_date + ts_codes（由编排层提供指数列表）
        - 按标的+时间段：指定 source_ticker + start_date + end_date

        注意：Tushare index_daily API 必须指定 ts_code 参数，不支持仅用 trade_date。

        Args:
            trade_date: Trade date (YYYY-MM-DD). 与 ts_codes 配合使用.
            ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
                由编排层提供，不在 Adapter 层硬编码.
            source_ticker: Source code (e.g., "000001.SH").
            start_date: Start date (YYYY-MM-DD). 与 source_ticker 配合使用.
            end_date: End date (YYYY-MM-DD). 与 source_ticker 配合使用.

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: 参数组合无效.
            SourceFetchError: If all fetches fail.

        """
        # 参数校验
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")

        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")

        # 按日期批量查询
        if trade_date:
            if not ts_codes:
                raise ValueError("按日期查询必须指定 ts_codes")
            return self._fetch_daily_by_date(trade_date, ts_codes)

        # 按标的+时间段查询（此时 source_ticker 必定不为 None）
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")

        return self._fetch_daily_by_ticker(source_ticker, start_date, end_date)

    @traced("source.tushare.fetch_global_index_daily")
    def fetch_global_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_at: datetime | None = None,
    ) -> pl.DataFrame:
        """
        Fetch a narrow global-index basket with fail-closed time semantics.

        ``event_time`` is the underlying market session close. Tushare does not
        expose the historical publication timestamp, so ``published_at`` and
        ``available_at`` are the actual retrieval instant. This deliberately
        prevents a newly fetched historical row from appearing in an earlier
        point-in-time query.
        """
        unsupported = sorted(set(codes) - _GLOBAL_INDEX_SPECS.keys())
        if unsupported:
            raise ValueError(
                f"Unsupported global index code(s): {', '.join(unsupported)}"
            )
        observed = observed_at or datetime.now(UTC)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        observed = observed.astimezone(UTC)
        frames: list[pl.DataFrame] = []
        for code in codes:
            with tushare_fetch_error_handler(
                "global_index_daily", f"index_global:{code}"
            ):
                frame = self._client.query(
                    api_name="index_global",
                    ts_code=code,
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    fields=(
                        "ts_code,trade_date,open,high,low,close,pre_close,"
                        "change,pct_chg,vol"
                    ),
                )
            if frame.height > 0:
                frames.append(frame)
        if not frames:
            return pl.DataFrame(schema=_GLOBAL_INDEX_SCHEMA)

        result = pl.concat(frames).rename(
            {
                "ts_code": "source_ticker",
                "pct_chg": "pct_change",
                "vol": "volume",
            }
        )
        result = result.with_columns(
            pl.col("trade_date").cast(pl.String).str.to_date("%Y%m%d", strict=False),
            *(
                pl.col(column).cast(pl.Float64, strict=False)
                for column in (
                    "open",
                    "high",
                    "low",
                    "close",
                    "pre_close",
                    "change",
                    "pct_change",
                    "volume",
                )
            ),
            pl.lit(None, dtype=pl.Float64).alias("amount"),
        )
        event_times = [
            _global_session_close_utc(str(code), trade_date)
            for code, trade_date in result.select(
                "source_ticker", "trade_date"
            ).iter_rows()
        ]
        result = result.with_columns(
            pl.Series("event_time", event_times),
            pl.lit(observed).alias("published_at"),
            pl.lit(observed).alias("available_at"),
            pl.lit(observed.astimezone(_SHANGHAI).date()).alias("knowledge_date"),
            pl.col("source_ticker")
            .replace_strict(
                {code: spec.timezone for code, spec in _GLOBAL_INDEX_SPECS.items()}
            )
            .alias("timezone"),
            pl.col("source_ticker")
            .replace_strict(
                {code: spec.currency for code, spec in _GLOBAL_INDEX_SPECS.items()}
            )
            .alias("currency"),
        )
        return result.select(*_GLOBAL_INDEX_SCHEMA)

    def _fetch_daily_by_date(
        self, trade_date: str, ts_codes: list[str]
    ) -> pl.DataFrame:
        """按日期获取指数日线数据."""
        logger.info(
            "Fetching Tushare index daily",
            event="tushare_index_daily_fetch_start",
            trade_date=trade_date,
            num_codes=len(ts_codes),
        )

        ts_date = trade_date.replace("-", "")
        dfs: list[pl.DataFrame] = []

        # 逐个查询每个指数
        for ts_code in ts_codes:
            try:
                provider_api = self._daily_api_name(ts_code)
                api_name = f"{provider_api}:{ts_code}"
                with tushare_fetch_error_handler("index_daily", api_name):
                    response = self._query_daily(
                        ts_code,
                        ts_date,
                        ts_date,
                    )
                    if response.height > 0:
                        dfs.append(response)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch index {ts_code}",
                    event="tushare_index_daily_fetch_failed",
                    ts_code=ts_code,
                    error=str(e),
                )
                continue

        if not dfs:
            logger.warning(
                "No index data fetched",
                event="tushare_index_daily_empty",
                trade_date=trade_date,
                ts_codes=ts_codes,
            )
            # 返回空 DataFrame 但保持正确的 schema
            return TushareDataTransformer.transform_daily_ohlcv(
                pl.DataFrame(),
                "index_daily",
            )

        # 合并所有结果
        combined = pl.concat(dfs)
        return TushareDataTransformer.transform_daily_ohlcv(
            combined,
            "index_daily",
        )

    def _fetch_daily_by_ticker(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """按标的+时间段获取指数日线数据（内部方法）."""
        logger.info(
            "Fetching Tushare index daily by ticker",
            event="tushare_index_daily_ticker_fetch_start",
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        provider_api = self._daily_api_name(source_ticker)
        with tushare_fetch_error_handler(
            "index_daily", f"{provider_api}:{source_ticker}"
        ):
            ts_start = start_date.replace("-", "")
            ts_end = end_date.replace("-", "")
            response = self._query_daily(source_ticker, ts_start, ts_end)

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "index_daily",
            )

    @staticmethod
    def _daily_api_name(source_ticker: str) -> str:
        """Resolve provider surface without treating SW codes as exchange indexes."""
        return "sw_daily" if source_ticker.endswith(".SI") else "index_daily"

    def _query_daily(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch one provider-native index series and normalize its raw columns."""
        api_name = self._daily_api_name(source_ticker)
        response = self._client.query(
            api_name=api_name,
            ts_code=source_ticker,
            start_date=start_date,
            end_date=end_date,
            fields=_SW_DAILY_FIELDS if api_name == "sw_daily" else _INDEX_DAILY_FIELDS,
        )
        if api_name != "sw_daily" or response.is_empty():
            return response
        return (
            response.with_columns(
                (
                    pl.col("close").cast(pl.Float64) - pl.col("change").cast(pl.Float64)
                ).alias("pre_close")
            )
            .rename({"pct_change": "pct_chg"})
            .select(
                "ts_code",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "vol",
                "amount",
                "pct_chg",
            )
        )
