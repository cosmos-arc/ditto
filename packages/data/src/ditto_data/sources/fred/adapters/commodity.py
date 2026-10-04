"""FRED commodity data adapter."""

from __future__ import annotations

import polars as pl

from ditto_data.models.source_codes import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)
from ditto_data.sources.fred.adapters.base import BaseFredAdapter
from ditto_data.sources.fred.indicators import get_fred_indicator
from ditto_data.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_data.utils.timezone_utils import (
    get_fred_query_date,
)


class CommodityFredAdapter(BaseFredAdapter):
    """
    Adapter for fetching commodity prices and VIX from FRED API.

    Normalizes FRED data to COMMODITY_SOURCE_SCHEMA format.
    FRED 每个观察日只有一个单值：写入 ``close``；``open/high/low`` 置空，
    不把单点参考值伪装成日内 OHLC（#432）。展示层如需蜡烛图自行以
    close 兜底，策略/可成交 OHLC 算法不得消费该帧。

    ``trade_date_utc`` 为观察日纽约午夜的占位时间戳（schema 要求），
    不是真实成交/观察时刻。

    Note:
        此适配器同时处理商品数据（WTI、Brent）和 VIX 波动率指数。
        VIX 虽然属于"另类数据"类别，但与商品数据共享相同的数据结构和处理流程，
        因此统一在此适配器中处理。两者都使用 COMMODITY_SOURCE_SCHEMA。
        金银不在本适配器：FRED LBMA 序列已死（见 indicators.py 核查依据），
        金银参考由 Tushare fx_daily 的 FXCM bid 提供。

    """

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity prices and VIX from FRED.

        Args:
            codes: Codes to fetch (e.g., ["COMMOD_WTI", "VIX_30D"]).
                   Supports both commodity codes and VIX codes.
            start_date: Start date in Beijing time (YYYY-MM-DD).
            end_date: End date in Beijing time (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.
            Unknown codes or non-commodity/vix codes are skipped.

        """
        # Convert Beijing time dates to FRED query dates (US Eastern time)
        fred_start = get_fred_query_date(start_date)
        fred_end = get_fred_query_date(end_date)

        results: list[pl.DataFrame] = []

        for code in codes:
            indicator = get_fred_indicator(code)
            if indicator is None or indicator.category not in ("commodity", "vix"):
                # Skip unknown codes or non-commodity/vix indicators
                continue

            # Look up instrument_id from either commodity or VIX mapping
            instrument_id = COMMODITY_CODE_TO_INSTRUMENT_ID.get(
                code
            ) or VIX_CODE_TO_INSTRUMENT_ID.get(code)
            if instrument_id is None:
                continue

            # Fetch from FRED API using converted dates
            df = self._client.get_series_observations(
                series_id=indicator.series_id,
                observation_start=fred_start,
                observation_end=fred_end,
            )

            if df.height == 0:
                continue

            # Transform to COMMODITY_SOURCE_SCHEMA
            # FRED 单值序列：close=value，open/high/low 为 null（无日内高低价
            # 可言），展示兜底由消费层决定；不伪造日内 OHLC。
            # FRED dates are in US Eastern time, convert to UTC midnight
            # （占位时间戳，非真实观察时刻）
            transformed = df.with_columns(
                pl.lit(instrument_id).alias("instrument_id"),
                pl.col("date").alias("trade_date"),
                pl.col("date")
                .dt.combine(time=pl.time(0, 0, 0))
                .dt.replace_time_zone("America/New_York", ambiguous="earliest")
                .dt.convert_time_zone("UTC")
                .alias("trade_date_utc"),
                pl.lit(None, dtype=pl.Float64).alias("open"),
                pl.lit(None, dtype=pl.Float64).alias("high"),
                pl.lit(None, dtype=pl.Float64).alias("low"),
                pl.col("value").alias("close"),
            ).select(
                "instrument_id",
                "trade_date",
                "trade_date_utc",
                "open",
                "high",
                "low",
                "close",
            )

            results.append(transformed)

        if not results:
            # Return empty DataFrame with correct schema
            return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)

        return pl.concat(results)


__all__ = [
    "COMMODITY_CODE_TO_INSTRUMENT_ID",
    "VIX_CODE_TO_INSTRUMENT_ID",
    "CommodityFredAdapter",
]
