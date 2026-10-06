"""
新浪外盘连续期货 DataSource（#436）——商品复合源的第三条腿.

身份与口径合同：
- 品种小白名单在 ``ditto_data.models.SINA_FOREIGN_FUTURES``（逐品种
  instrument_id/单位/币种登记；ZSD 身份未核实不入表）。
- 端点无窗口参数：每次请求返回全量当前视图，本地按 [start, end] 过滤。
  实测历史起点恰为探测日 10/30 年前（CL 1996-10-07、GC/SI 2016-10-05，
  2026-10-05 探测），疑似滚动窗口——旧行可能从源端滚出，回填深度以逐日
  摄取为准，不验收可交易连续期货收益。
- 占位零语义：CL/GC 的 volume/position/settlement 实测恒为 0（ZSD 缺
  settlement 字段），不证明真实成交/持仓/结算，一律不入库；仅存真实
  日线 OHLC。单位/币种逐品种见白名单登记。
- OHLC 非空校验：源字段改名会经宽松 String+非严格 cast 静默得 null，
  入库前对窗口内行 fail-closed（#516），拒绝整段静默空数据。
- trade_date_utc 为交易日纽约午夜占位时间戳（schema 要求），外盘真实
  收盘时刻未验证，不用于可见性判断。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.models import SINA_FOREIGN_FUTURES
from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA

if TYPE_CHECKING:
    from ditto_data.sources.sina.client import SinaClient


class SinaSource:
    """新浪外盘连续期货参考序列源（展示-only，#436）."""

    def __init__(self, client: SinaClient) -> None:
        self._client = client

    def close(self) -> None:
        """释放底层 HTTP 连接资源."""
        self._client.close()

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        按白名单品种取回区间内的连续参考日线.

        Args:
            codes: 新浪品种符号白名单（必须在 SINA_FOREIGN_FUTURES 中）.
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).

        Returns:
            COMMODITY_SOURCE_SCHEMA 帧（instrument_id 身份，OHLC 真实值）。

        """
        unknown = [code for code in codes if code not in SINA_FOREIGN_FUTURES]
        if unknown:
            msg = f"sina foreign futures symbols not registered: {unknown}"
            raise ValueError(msg)

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        results: list[pl.DataFrame] = []
        for symbol in codes:
            instrument_id = SINA_FOREIGN_FUTURES[symbol][0]
            rows = self._client.get_global_futures_daily_kline(symbol)
            if not rows:
                continue
            frame = pl.DataFrame(
                rows,
                schema={
                    "date": pl.String,
                    "open": pl.String,
                    "high": pl.String,
                    "low": pl.String,
                    "close": pl.String,
                    "volume": pl.String,
                    "position": pl.String,
                    "s": pl.String,
                },
                strict=False,
            )
            # 占位字段（volume/position/s/settlement）不选出：实测恒零或
            # 缺失，不证明真实成交/持仓/结算（#436 口径合同）。
            transformed = (
                frame.select(
                    pl.col("date")
                    .str.to_date("%Y-%m-%d", strict=False)
                    .alias("trade_date"),
                    pl.col("open").cast(pl.Float64, strict=False).alias("open"),
                    pl.col("high").cast(pl.Float64, strict=False).alias("high"),
                    pl.col("low").cast(pl.Float64, strict=False).alias("low"),
                    pl.col("close").cast(pl.Float64, strict=False).alias("close"),
                )
                .drop_nulls("trade_date")
                .filter(pl.col("trade_date").is_between(start, end))
            )
            if transformed.is_empty():
                continue
            # 字段解析为宽松 String + 非严格 cast：源端字段改名会静默得
            # null OHLC 而非报错（drop_nulls 只保护 trade_date）。入库前
            # 对窗口内行做非空校验，fail-closed 防整段静默空数据（#516）。
            null_ohlc = transformed.filter(
                pl.any_horizontal(
                    pl.col("open").is_null(),
                    pl.col("high").is_null(),
                    pl.col("low").is_null(),
                    pl.col("close").is_null(),
                )
            )
            if not null_ohlc.is_empty():
                sample_dates = (
                    null_ohlc["trade_date"].head(3).dt.strftime("%Y-%m-%d").to_list()
                )
                raise SourceFetchError(
                    source="sina",
                    message=(
                        f"sina {symbol} 窗口内 {null_ohlc.height} 行 OHLC 为 null"
                        f" (样本 {sample_dates}):"
                        " 源字段契约疑似变更 拒绝静默入库 (#516)"
                    ),
                )
            transformed = transformed.with_columns(
                pl.lit(instrument_id).alias("instrument_id"),
                pl.col("trade_date")
                .dt.combine(pl.time(0, 0, 0))
                .dt.replace_time_zone("America/New_York", ambiguous="earliest")
                .dt.convert_time_zone("UTC")
                .cast(pl.Datetime("ms"))
                .alias("trade_date_utc"),
            )
            logger.info(
                "Sina commodity leg fetched",
                event="sina_commodity_leg_fetch",
                symbol=symbol,
                rows=transformed.height,
            )
            results.append(
                transformed.select(
                    "instrument_id",
                    "trade_date",
                    "trade_date_utc",
                    "open",
                    "high",
                    "low",
                    "close",
                )
            )

        if not results:
            return pl.DataFrame(schema=COMMODITY_SOURCE_SCHEMA.schema)
        return pl.concat(results)
