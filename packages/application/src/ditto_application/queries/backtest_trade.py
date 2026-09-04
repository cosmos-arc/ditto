"""BacktestTrade query facade — 从回测产物读取成交明细."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from ditto_strategy.models import ArtifactKind
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.queries.artifact_utils import find_artifact

__all__ = ["BacktestTradeQueryFacade", "TradeRecord"]

_TRADE_LOG_FILENAME = "trade_log.parquet"


@dataclass(frozen=True)
class TradeRecord:
    """回测成交记录 — 对应 trade_log.parquet 的行结构."""

    trade_date: str
    instrument_id: int
    direction: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float


def _df_to_trade_records(df: pl.DataFrame) -> list[TradeRecord]:
    """将 DataFrame 转换为 TradeRecord 列表."""
    if df.is_empty():
        return []
    trade_date_column = "trade_date" if "trade_date" in df.columns else "exit_date"
    pnl_column = "pnl" if "pnl" in df.columns else "net_pnl"
    rows = df.to_dicts()
    return [
        TradeRecord(
            trade_date=str(row[trade_date_column]),
            instrument_id=int(row["instrument_id"]),
            direction=str(row["direction"]),
            entry_date=str(row["entry_date"]),
            exit_date=str(row["exit_date"]),
            entry_price=float(row["entry_price"]),
            exit_price=float(row["exit_price"]),
            quantity=int(row["quantity"]),
            pnl=float(row[pnl_column]),
        )
        for row in rows
    ]


class BacktestTradeQueryFacade:
    """
    回测成交查询 facade.

    封装 StrategyArtifactService，根据 run_id 查找产物目录，
    读取 trade_log.parquet 并返回结构化 DataFrame.
    """

    def __init__(self, artifact_service: StrategyArtifactService) -> None:
        self._service = artifact_service

    def query_trades(
        self,
        *,
        run_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TradeRecord]:
        """
        查询回测成交明细.

        Args:
            run_id: 回测运行 ID
            start_date: 过滤起始日期 (YYYY-MM-DD)，过滤 exit_date < start_date 的记录
            end_date: 过滤截止日期 (YYYY-MM-DD)，过滤 entry_date > end_date 的记录
            limit: 返回数量限制
            offset: 跳过前 N 条记录

        Returns:
            TradeRecord 列表，找不到时返回空列表

        """
        record = find_artifact(self._service, run_id, ArtifactKind.BACKTEST_REPORT)
        if record is None:
            return []

        parquet_path = Path(record.file_path) / _TRADE_LOG_FILENAME
        if not parquet_path.exists():
            return []

        df = pl.read_parquet(parquet_path)
        df = self._filter_closed_trades(df)
        df = self._apply_date_filters(df, start_date, end_date)
        df = self._apply_pagination(df, limit, offset)
        return _df_to_trade_records(df)

    @staticmethod
    def _filter_closed_trades(df: pl.DataFrame) -> pl.DataFrame:
        """Exclude current-engine aggregate rows that still represent open positions."""
        pnl_column = "pnl" if "pnl" in df.columns else "net_pnl"
        return df.drop_nulls(["exit_date", "exit_price", pnl_column])

    @staticmethod
    def _apply_date_filters(
        df: pl.DataFrame,
        start_date: str | None,
        end_date: str | None,
    ) -> pl.DataFrame:
        """应用日期范围过滤."""
        if start_date is not None:
            df = df.filter(pl.col("exit_date") >= start_date)
        if end_date is not None:
            df = df.filter(pl.col("entry_date") <= end_date)
        return df

    @staticmethod
    def _apply_pagination(
        df: pl.DataFrame,
        limit: int | None,
        offset: int,
    ) -> pl.DataFrame:
        """应用分页."""
        if offset > 0:
            df = df.slice(offset)
        if limit is not None:
            df = df.head(limit)
        return df
