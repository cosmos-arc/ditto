"""Tushare FX (Foreign Exchange) data adapter."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_infra.foundation import traced

from ditto_data.config import DataSourceSettings

# 汇率品种代码映射到 instrument_id
# 使用 4M 范围 (4,000,000 - 4,999,999) 作为汇率
# 注意：贵金属现货（伦敦金/银）通过 FRED 获取，不在此列表
# 常量已迁移至 models 层
from ditto_data.models.source_codes import FX_CODE_TO_INSTRUMENT_ID
from ditto_data.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA
from ditto_data.sources.tushare.client import TushareClient
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)


class FxTushareAdapter:
    """
    Tushare adapter for FX daily data.

    外汇日线行情数据适配器，从 Tushare fx_daily 接口获取数据。

    支持的数据类型：
    - FX: 外汇货币对 (USDCNH, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD)

    注意：
    - Tushare fx_daily 使用 bid 价格作为标准 OHLC
    - 日期为 GMT 时区（格林尼治时间）
    - 贵金属现货（伦敦金/银）通过 FRED 获取

    Attributes:
        _client: TushareClient 实例.

    """

    def __init__(
        self,
        token: str | None = None,
        *,
        _client: Any = None,
    ) -> None:
        """
        初始化汇率适配器.

        Args:
            token: Tushare API token（可选，优先使用环境变量）.
            _client: 已存在的 client（用于依赖注入，仅供测试使用）.

        """
        if _client is not None:
            self._client: TushareClient = _client
        else:
            settings = DataSourceSettings()
            self._client = TushareClient(settings=settings, token=token)

    @traced("source.tushare.fetch_fx_daily")
    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch FX daily data from Tushare.

        Args:
            ts_codes: FX ticker codes (e.g., ["USDCNH.FXCM"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with FX_SOURCE_SCHEMA columns.

        """
        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")

        results: list[pl.DataFrame] = []

        for ts_code in ts_codes:
            with tushare_fetch_error_handler("fx_daily", ts_code):
                response = self._client.query(
                    api_name="fx_daily",
                    # Tushare fx_daily 返回 bid/ask 价格，使用 bid 价格作为 OHLC
                    fields="ts_code,trade_date,bid_open,bid_high,bid_low,bid_close",
                    ts_code=ts_code,
                    start_date=compact_start,
                    end_date=compact_end,
                )

                if response.is_empty():
                    continue

                # 获取 instrument_id
                instrument_id = FX_CODE_TO_INSTRUMENT_ID.get(ts_code)
                if instrument_id is None:
                    continue

                # 转换为 FX_SOURCE_SCHEMA
                # Tushare fx_daily 日期为 GMT 时区（格林尼治时间）
                df = response.with_columns(
                    pl.lit(instrument_id).alias("instrument_id"),
                    pl.col("trade_date")
                    .cast(pl.String)
                    .str.to_date(format="%Y%m%d", strict=False)
                    .alias("trade_date"),
                    # Tushare fx_daily 日期为 GMT，直接转换为 UTC
                    pl.col("trade_date")
                    .cast(pl.String)
                    .str.to_date(format="%Y%m%d", strict=False)
                    .dt.combine(time=pl.time(0, 0, 0))
                    .dt.replace_time_zone("UTC", ambiguous="earliest")
                    .alias("trade_date_utc"),
                    # 使用 bid 价格作为标准 OHLC
                    pl.col("bid_open").cast(pl.Float64).alias("open"),
                    pl.col("bid_high").cast(pl.Float64).alias("high"),
                    pl.col("bid_low").cast(pl.Float64).alias("low"),
                    pl.col("bid_close").cast(pl.Float64).alias("close"),
                ).select(
                    "instrument_id",
                    "trade_date",
                    "trade_date_utc",
                    "open",
                    "high",
                    "low",
                    "close",
                )

                results.append(df)

        if not results:
            return pl.DataFrame(schema=FX_SOURCE_SCHEMA.schema)

        return pl.concat(results)


__all__ = ["FX_CODE_TO_INSTRUMENT_ID", "FxTushareAdapter"]
