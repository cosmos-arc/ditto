"""
国内商品/金融期货合约日线与合约信息适配器（#434）.

身份合同：ts_code 是具体合约（如 CU2506.SHF），保留合约生命周期
（上市/最后交易日）与结算价，不与连续参考序列混身份；不建立期货
交易/交割链。单位与口径按原始值存储，不在适配层换算：

- ``amount`` 万元；2020-01-01 前后成交量单/双边统计口径变化，原始
  口径保留，不按资产统一正价格校验。
- ``close`` 可为 null（实测 2026-09-30 SCTASL.INE 行 close=null、
  settle 有效），结算价与收盘价是不同字段，不互填。
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)

_FUTURES_DAILY_FIELDS = (
    "ts_code,trade_date,open,high,low,close,settle,pre_settle,vol,amount,oi"
)
_FUTURES_BASIC_FIELDS = (
    "ts_code,symbol,exchange,fut_code,multiplier,list_date,delist_date"
)
# 官方交易所代码（doc_id=135）。2026-10-05 实测：exchange=SHF/ZCE 会
# 静默返回空，必须使用 SHFE/CZCE；全表 11287 行 > 10000 单页上限，
# 按交易所分片后最大 3632 行，落在单页内。
_FUTURES_EXCHANGES = ("SHFE", "CZCE", "DCE", "INE", "CFFEX", "GFEX")

FUTURES_DAILY_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source_ticker": pl.String,
    "trade_date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "settle": pl.Float64,
    "pre_settle": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "open_interest": pl.Float64,
    "knowledge_date": pl.Date,
}

FUTURES_BASIC_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source": pl.String,
    "source_ticker": pl.String,
    "symbol": pl.String,
    "exchange": pl.String,
    "fut_code": pl.String,
    "multiplier": pl.Float64,
    "list_date": pl.Date,
    "delist_date": pl.Date,
    "knowledge_date": pl.Date,
}


def empty_futures_daily() -> pl.DataFrame:
    """Return an empty frame with the futures-daily contract."""
    return pl.DataFrame(schema=FUTURES_DAILY_SCHEMA)


def empty_futures_basic() -> pl.DataFrame:
    """Return an empty frame with the futures-basic contract."""
    return pl.DataFrame(schema=FUTURES_BASIC_SCHEMA)


class FuturesTushareAdapter(BaseTushareAdapter):
    """Tushare 期货合约日线与合约信息适配器."""

    @traced("source.tushare.fetch_futures_daily")
    def fetch_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取期货合约日线.

        两种模式：按交易日全市场（trade_date）或按合约+区间
        （source_ticker + start_date/end_date）。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD).
            source_ticker: 合约代码 (e.g., "CU2506.SHF").
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).

        Returns:
            DataFrame with FUTURES_DAILY_SCHEMA columns.

        """
        if trade_date and source_ticker:
            msg = "trade_date 和 source_ticker 互斥, 不能同时指定"
            raise ValueError(msg)
        if not trade_date and not source_ticker:
            msg = "必须指定 trade_date 或 source_ticker 之一"
            raise ValueError(msg)

        params: dict[str, str] = {
            "api_name": "fut_daily",
            "fields": _FUTURES_DAILY_FIELDS,
        }
        if trade_date:
            params["trade_date"] = trade_date.replace("-", "")
        else:
            params["ts_code"] = source_ticker or ""
            params["start_date"] = (start_date or "").replace("-", "")
            params["end_date"] = (end_date or "").replace("-", "")

        logger.info(
            "Fetching Tushare futures daily",
            event="tushare_futures_daily_fetch_start",
            trade_date=trade_date,
            source_ticker=source_ticker,
        )
        with tushare_fetch_error_handler("futures_daily", "fut_daily"):
            response = self._client.query(**params)

        if response.is_empty():
            return empty_futures_daily()

        result = (
            response.rename(
                {"ts_code": "source_ticker", "vol": "volume", "oi": "open_interest"}
            )
            .with_columns(
                pl.col("trade_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False),
                *(
                    pl.col(column).cast(pl.Float64, strict=False)
                    for column in (
                        "open",
                        "high",
                        "low",
                        "close",
                        "settle",
                        "pre_settle",
                        "volume",
                        "amount",
                        "open_interest",
                    )
                ),
                pl.lit(date.today()).alias("knowledge_date"),
            )
            .filter(pl.col("trade_date").is_not_null())
        )

        Metrics.data_records.add(
            result.height,
            {"source": "tushare", "dataset": "futures_daily", "status": "success"},
        )
        return result.select(*FUTURES_DAILY_SCHEMA)

    @traced("source.tushare.fetch_futures_basic")
    def fetch_basic(self) -> pl.DataFrame:
        """
        获取期货合约信息快照（按交易所分片）.

        fut_basic 不提供公告时刻；knowledge_date 即采集日，写入为
        effective-dated 快照。delist_date 为合约最后交易日。

        Returns:
            DataFrame with FUTURES_BASIC_SCHEMA columns.

        """
        logger.info(
            "Fetching Tushare futures basic",
            event="tushare_futures_basic_fetch_start",
        )
        frames: list[pl.DataFrame] = []
        for exchange in _FUTURES_EXCHANGES:
            with tushare_fetch_error_handler("futures_basic", f"fut_basic:{exchange}"):
                response = self._client.query(
                    api_name="fut_basic",
                    fields=_FUTURES_BASIC_FIELDS,
                    exchange=exchange,
                )
            if response.height > 0:
                # 各交易所分片可整列为 null（polars 推断 Null dtype），
                # 先统一 cast 再 concat，避免 vstack dtype 冲突。
                frames.append(
                    response.with_columns(
                        pl.col("multiplier").cast(pl.Float64, strict=False),
                        pl.col("list_date").cast(pl.String),
                        pl.col("delist_date").cast(pl.String),
                    )
                )

        if not frames:
            return empty_futures_basic()

        result = (
            pl.concat(frames)
            .rename({"ts_code": "source_ticker"})
            .with_columns(
                pl.col("list_date").str.to_date("%Y%m%d", strict=False),
                pl.col("delist_date").str.to_date("%Y%m%d", strict=False),
                pl.lit("tushare").alias("source"),
                pl.lit(date.today()).alias("knowledge_date"),
            )
        )
        Metrics.data_records.add(
            result.height,
            {"source": "tushare", "dataset": "futures_basic", "status": "success"},
        )
        return result.select(*FUTURES_BASIC_SCHEMA)
