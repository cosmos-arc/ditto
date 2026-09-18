"""
fuyao 数据源门面 — 冗余源（ADR：Tushare 主源，fuyao 对账与故障日降级）.

能力（与 #199/#191 对齐）：
- ``fetch_stock_daily``：MarketFetcher 协议两模式 — trade_date 全市场单日
  （10 交易日 dump 一次下载 + 本地过滤，供 source=auto 摄取）；source_ticker
  + 起止日单标的 REST 历史（adjust=none）；
- ``fetch_stock_daily_bars``：对账协议帧（ticker 裸码，单日）；
- 快照（A 股批量 / ETF 单只）：展示层用，不进管道；
- ``download_market_dump`` / ``daily_k_frame``：10 年日 K / 复权因子事件流
  Parquet 不可变快照与帧转换。

红线（#191）：只取原始价（adjust=none）与因子事件流，复权价快照不进因子
管道；fuyao 财务不作为披露锚（唯一锚 = Tushare f_ann_date）。ETF 历史为
前复权口径，不参与原始价摄取与对账。
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Literal

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.sources.fuyao.client import FuyaoClient, date_to_ms, ms_to_date

type DumpKind = Literal["daily-k", "daily-k-10d", "adjustment-factors"]

_DUMP_PATHS: dict[str, str] = {
    "daily-k": "/api/dump/market-dumps/daily-k/download-url",
    "daily-k-10d": "/api/dump/market-dumps/daily-k-10d/download-url",
    "adjustment-factors": "/api/dump/market-dumps/adjustment-factors/download-url",
}

# 裸码 → 交易所后缀（与 ts_code/thscode 同构；8/4 开头为北交所）
_TICKER_SUFFIX = {
    "6": ".SH",
    "5": ".SH",
    "0": ".SZ",
    "3": ".SZ",
    "1": ".SZ",
    "8": ".BJ",
    "4": ".BJ",
}

_BAR_COLUMNS = (
    "source_ticker",
    "trade_date",
    "knowledge_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_change",
)

_BARS_RAW_SCHEMA: dict[str, type[pl.DataType]] = {
    "trade_date_ms": pl.Int64,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


def _to_thscode(ticker: str) -> str:
    return (
        ticker if "." in ticker else f"{ticker}{_TICKER_SUFFIX.get(ticker[0], '.SZ')}"
    )


def _parse_date(value: str) -> date:
    return date.fromisoformat(value.replace("-", ""))


# 单位归一：fuyao 原始单位（股/元）→ 管道存储约定（Tushare 口径：手/千元），
# 跨源对账与同库混写均以此为准（2026-09-18 首跑对账实测 ×100/×1000 差异）。
_VOLUME_TO_LOTS = 100.0
_AMOUNT_TO_THOUSANDS = 1000.0


def _bars_frame(rows: list[Any], source_ticker: str) -> pl.DataFrame:
    """原始 bar 行 → STOCK_DAILY SourceSchema 帧（knowledge_date = T+1）."""
    frame = pl.DataFrame(rows, schema=_BARS_RAW_SCHEMA, orient="row")
    return (
        frame.sort("trade_date_ms")
        .with_columns(
            source_ticker=pl.lit(source_ticker),
            trade_date=pl.col("trade_date_ms").map_elements(
                ms_to_date, return_dtype=pl.Date
            ),
            pre_close=pl.col("close").shift(1),
            volume=pl.col("volume") / _VOLUME_TO_LOTS,
            amount=pl.col("amount") / _AMOUNT_TO_THOUSANDS,
        )
        .with_columns(
            knowledge_date=pl.col("trade_date") + pl.duration(days=1),
            pct_change=(pl.col("close") / pl.col("pre_close") - 1) * 100,
        )
        .drop("trade_date_ms")
        .select(_BAR_COLUMNS)
    )


class FuyaoSource:
    """fuyao 数据源门面."""

    def __init__(self, *, client: FuyaoClient) -> None:
        self._client = client

    def close(self) -> None:
        """释放底层 HTTP 连接."""
        self._client.close()

    # ── 摄取路径（source=auto / 按标的）─────────────────────────

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """原始日 K（adjust=none）— MarketFetcher 协议两模式."""
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")
        if trade_date:
            return self._fetch_market_daily(trade_date)
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 start_date 和 end_date")
        return self._fetch_ticker_daily(source_ticker, start_date, end_date)

    def _fetch_market_daily(self, trade_date: str) -> pl.DataFrame:
        target = _parse_date(trade_date)
        with tempfile.TemporaryDirectory(prefix="fuyao-dump-") as tmp:
            dump_path = Path(tmp) / "daily-k-10d.parquet"
            self.download_market_dump("daily-k-10d", dump_path)
            frame = self.daily_k_frame(dump_path)
        daily = frame.filter(pl.col("trade_date") == target)
        logger.info(
            "Fuyao daily-k-10d filtered",
            event="fuyao_stock_daily_fetch_complete",
            trade_date=str(target),
            row_count=len(daily),
        )
        return daily

    def _fetch_ticker_daily(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        thscode = _to_thscode(source_ticker)
        data = self._client.get(
            "/api/a-share/prices/historical",
            params={
                "thscode": thscode,
                "interval": "1d",
                "start": date_to_ms(_parse_date(start_date)),
                "end": date_to_ms(_parse_date(end_date)),
                "adjust": "none",
            },
        )
        items: list[dict[str, Any]] = data.get("item") or []
        rows: list[tuple[Any, ...]] = [
            (
                item["date_ms"],
                item["open_price"],
                item["high_price"],
                item["low_price"],
                item["close_price"],
                item["volume"],
                item["turnover"],
            )
            for item in items
        ]
        return _bars_frame(rows, thscode)

    @staticmethod
    def daily_k_frame(dump_path: Path) -> pl.DataFrame:
        """日 K dump Parquet → STOCK_DAILY 帧（pre_close 在 dump 窗口内推导）."""
        raw = pl.read_parquet(dump_path)
        return (
            raw.rename(
                {
                    "thscode": "source_ticker",
                    "date_ms": "trade_date_ms",
                    "open_price": "open",
                    "high_price": "high",
                    "low_price": "low",
                    "close_price": "close",
                    "turnover": "amount",
                }
            )
            .sort(["source_ticker", "trade_date_ms"])
            .with_columns(
                trade_date=pl.col("trade_date_ms").map_elements(
                    ms_to_date, return_dtype=pl.Date
                ),
                pre_close=pl.col("close").shift(1).over("source_ticker"),
                volume=pl.col("volume") / _VOLUME_TO_LOTS,
                amount=pl.col("amount") / _AMOUNT_TO_THOUSANDS,
            )
            .with_columns(
                knowledge_date=pl.col("trade_date") + pl.duration(days=1),
                pct_change=(pl.col("close") / pl.col("pre_close") - 1) * 100,
            )
            .drop("trade_date_ms")
            .select(_BAR_COLUMNS)
        )

    # ── 对账协议（辅源）──────────────────────────────────────────

    def fetch_stock_daily_bars(
        self,
        tickers: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """对账协议帧：[ticker, trade_date, open, high, low, close, volume, amount]."""
        target = _parse_date(trade_date)
        frames: list[pl.DataFrame] = []
        for ticker in tickers:
            frame = self._fetch_ticker_daily(ticker, str(target), str(target))
            frame = frame.filter(pl.col("trade_date") == target)
            if not frame.is_empty():
                frames.append(
                    frame.with_columns(
                        ticker=pl.col("source_ticker").str.split(".").list.get(0)
                    ).select(
                        "ticker",
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "amount",
                    )
                )
        if not frames:
            return pl.DataFrame(
                schema={
                    "ticker": pl.String,
                    "trade_date": pl.Date,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64,
                    "amount": pl.Float64,
                }
            )
        return pl.concat(frames)

    # ── 快照（展示层，不进管道）──────────────────────────────────

    def fetch_a_share_snapshot(self, thscodes: list[str]) -> pl.DataFrame:
        """A 股 L1 快照（批量，展示层）."""
        data = self._client.get(
            "/api/a-share/prices/snapshot", params={"thscodes": ",".join(thscodes)}
        )
        return pl.DataFrame(data.get("item") or [])

    def fetch_fund_snapshot(self, thscode: str) -> pl.DataFrame:
        """ETF L1 快照（单只，展示层）."""
        data = self._client.get(
            "/api/fund/market/snapshot", params={"thscode": thscode}
        )
        return pl.DataFrame(data.get("item") or [])

    # ── 全市场 dump（不可变快照落盘）─────────────────────────────

    def download_market_dump(self, kind: DumpKind, dest: Path) -> Path:
        """获取预签名链接并流式下载 dump Parquet 到 dest."""
        data = self._client.get(_DUMP_PATHS[kind])
        presigned = data.get("presigned_url")
        if not presigned:
            raise ValueError(f"fuyao dump {kind} returned no presigned_url")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            self._client.download(presigned, fh)
        logger.info(
            "Fuyao market dump downloaded",
            event="fuyao_dump_download_complete",
            kind=kind,
            path=str(dest),
            size_bytes=dest.stat().st_size,
        )
        return dest
