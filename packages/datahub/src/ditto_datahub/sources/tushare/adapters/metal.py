"""
Tushare Metal (Precious Metals) data adapter.

Uses fx_daily API with METAL classify to fetch XAUUSD and XAGUSD data.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_infra.foundation import traced

from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_datahub.sources.tushare.client import TushareClient
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)

# 贵金属品种代码映射到 instrument_id
# 使用与 FRED commodity 相同的 ID 范围 (5,000,000 - 5,099,999)
# 注意：这些 ID 需要与 fred/adapters/commodity.py 中的映射一致
METAL_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    # 贵金属现货（通过 Tushare fx_daily METAL 分类获取）
    "XAUUSD.FXCM": 5_000_003,  # 黄金美元（对应 COMMOD_GOLD）
    "XAGUSD.FXCM": 5_000_004,  # 白银美元（对应 COMMOD_SILVER）
}

# 代码别名映射（支持多种输入格式）
METAL_CODE_ALIASES: dict[str, str] = {
    # 黄金
    "COMMOD_GOLD": "XAUUSD.FXCM",
    "GOLD": "XAUUSD.FXCM",
    "XAUUSD": "XAUUSD.FXCM",
    # 白银
    "COMMOD_SILVER": "XAGUSD.FXCM",
    "SILVER": "XAGUSD.FXCM",
    "XAGUSD": "XAGUSD.FXCM",
}


class MetalTushareAdapter:
    """
    Tushare adapter for precious metals daily data.

    贵金属日线行情数据适配器，从 Tushare fx_daily 接口（METAL 分类）获取数据。

    支持的数据类型：
    - XAUUSD: 黄金美元现货
    - XAGUSD: 白银美元现货

    Note:
        - 使用 fx_daily 接口的 METAL 分类
        - Tushare fx_daily 使用 bid 价格作为标准 OHLC
        - 日期为 GMT 时区（格林尼治时间）
        - 需要至少 2000 积分才能调用

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
        初始化贵金属适配器.

        Args:
            token: Tushare API token（可选，优先使用环境变量）.
            _client: 已存在的 client（用于依赖注入，仅供测试使用）.

        """
        if _client is not None:
            self._client: TushareClient = _client
        else:
            settings = DataSourceSettings()
            self._client = TushareClient(settings=settings, token=token)

    @traced("source.tushare.fetch_metal_daily")
    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch precious metals daily data from Tushare fx_daily API.

        Args:
            codes: Metal codes (e.g., ["XAUUSD.FXCM", "COMMOD_GOLD"]).
                   支持别名：COMMOD_GOLD, GOLD, XAUUSD, COMMOD_SILVER, SILVER, XAGUSD
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns.

        """
        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")

        results: list[pl.DataFrame] = []

        for code in codes:
            # 解析代码别名
            ts_code = METAL_CODE_ALIASES.get(code, code)

            # 获取 instrument_id
            instrument_id = METAL_CODE_TO_INSTRUMENT_ID.get(ts_code)
            if instrument_id is None:
                # 不是贵金属代码，跳过
                continue

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

                # 转换为 COMMODITY_SOURCE_SCHEMA
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
            return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)

        return pl.concat(results)


__all__ = ["METAL_CODE_ALIASES", "METAL_CODE_TO_INSTRUMENT_ID", "MetalTushareAdapter"]
