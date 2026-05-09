"""复权因子回补编排 — 从 ingestion_coordinator 提取的回补子步骤."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.protocols import MarketFetcher
from ditto_platform.foundation import OnDuplicate, logger

from ditto_application.processes.ingestion.data_writer import IngestionDataWriter


@dataclass(frozen=True)
class BackfillContext:
    """backfill_adj_factor 所需的服务依赖聚合."""

    metadata_service: MetadataService
    market_service: MarketService
    source: MarketFetcher
    source_name: str
    data_writer: IngestionDataWriter


def backfill_adj_factor(
    instrument_id: int,
    start: str,
    end: str,
    ctx: BackfillContext,
) -> dict[str, object]:
    """
    按标的智能回补复权因子空洞.

    检测指定证券在 [start, end] 日期范围内的复权因子空洞，
    仅对缺失的连续日期区间发起数据源请求，避免全量覆盖。

    Args:
        instrument_id: 证券内部 ID.
        start: 开始日期 (YYYY-MM-DD).
        end: 结束日期 (YYYY-MM-DD).
        ctx: 回补上下文（服务依赖）.

    Returns:
        回补结果摘要，包含 status / gap_count / filled_dates.

    """
    logger.info(
        "开始智能回补复权因子",
        event="backfill_adj_factor_start",
        instrument_id=instrument_id,
        start=start,
        end=end,
    )

    # 1. 前置检查：范围内是否有交易日
    trading_days = ctx.metadata_service.list_trading_days(start, end)
    if not trading_days:
        logger.info(
            "范围内无交易日",
            event="backfill_adj_factor_no_trading_days",
            instrument_id=instrument_id,
        )
        return {"status": "ok", "gap_count": 0, "filled_dates": 0}

    # 2. 检测空洞
    gap_dates = detect_adj_factor_gaps(
        instrument_id, start, end, ctx.metadata_service, ctx.market_service
    )
    if not gap_dates:
        logger.info(
            "复权因子数据完整 无需回补",
            event="backfill_adj_factor_no_gaps",
            instrument_id=instrument_id,
        )
        return {"status": "ok", "gap_count": 0, "filled_dates": 0}

    # 3. 解析 source_ticker
    source_ticker = ctx.metadata_service.resolve_source_ticker(
        instrument_id=instrument_id,
        asset_class="stock",
        source=ctx.source_name,
    )

    # 4. 逐段 fetch + 写入
    gap_ranges = group_contiguous_dates(gap_dates)
    total_filled = 0
    for range_start, range_end in gap_ranges:
        gap_df = fetch_adj_factor_range(
            ctx.source, source_ticker, range_start, range_end
        )
        if gap_df.is_empty():
            continue
        total_filled += write_adj_factor_range(ctx.data_writer, gap_df, range_start)

    logger.info(
        "智能回补复权因子完成",
        event="backfill_adj_factor_complete",
        instrument_id=instrument_id,
        gap_count=len(gap_ranges),
        filled_dates=total_filled,
    )
    return {
        "status": "ok",
        "gap_count": len(gap_ranges),
        "filled_dates": total_filled,
    }


def detect_adj_factor_gaps(
    instrument_id: int,
    start: str,
    end: str,
    metadata_service: MetadataService,
    market_service: MarketService,
) -> list[str]:
    """检测 [start, end] 内缺失的复权因子日期，返回排序后的空洞列表."""
    trading_days = metadata_service.list_trading_days(start, end)
    if not trading_days:
        return []

    trading_day_set: set[str] = set(trading_days)

    existing_df = market_service.get_adj_factors(start, end)
    existing_dates: set[str] = set()
    if not existing_df.is_empty():
        existing_dates = set(
            existing_df.filter(pl.col("instrument_id") == instrument_id)
            .select("trade_date")
            .to_series()
            .cast(pl.String)
            .to_list()
        )

    return sorted(trading_day_set - existing_dates)


def fetch_adj_factor_range(
    source: MarketFetcher,
    source_ticker: str,
    range_start: str,
    range_end: str,
) -> pl.DataFrame:
    """拉取单个连续区间的复权因子数据，失败时返回空 DataFrame."""
    try:
        return source.fetch_adj_factor_by_ticker(
            ts_code=source_ticker,
            start_date=range_start.replace("-", ""),
            end_date=range_end.replace("-", ""),
        )
    except Exception as e:
        logger.warning(
            "回补 fetch 失败",
            event="backfill_adj_factor_fetch_failed",
            range_start=range_start,
            range_end=range_end,
            error=str(e),
        )
        return pl.DataFrame()


def write_adj_factor_range(
    data_writer: IngestionDataWriter,
    gap_df: pl.DataFrame,
    range_start: str,
) -> int:
    """写入单段复权因子数据，返回写入行数，失败时返回 0."""
    try:
        data_writer.write_data("adj_factor", gap_df, range_start, OnDuplicate.KEEP_LAST)
        return len(gap_df)
    except Exception as e:
        logger.warning(
            "回补写入失败",
            event="backfill_adj_factor_write_failed",
            range_start=range_start,
            error=str(e),
        )
        return 0


def group_contiguous_dates(dates: list[str]) -> list[tuple[str, str]]:
    """
    将日期列表按连续区间分组.

    对于 [2024-01-02, 2024-01-03, 2024-01-05, 2024-01-06]，
    返回 [("2024-01-02", "2024-01-03"), ("2024-01-05", "2024-01-06")]。

    Args:
        dates: 已排序的日期字符串列表 (YYYY-MM-DD).

    Returns:
        连续区间列表 [(start, end), ...].

    """
    if not dates:
        return []

    ranges: list[tuple[str, str]] = []
    range_start = dates[0]
    prev = date.fromisoformat(dates[0])

    for d_str in dates[1:]:
        d = date.fromisoformat(d_str)
        if (d - prev).days <= 1:
            prev = d
        else:
            ranges.append((range_start, prev.isoformat()))
            range_start = d_str
            prev = d

    ranges.append((range_start, prev.isoformat()))
    return ranges


__all__ = [
    "BackfillContext",
    "backfill_adj_factor",
    "detect_adj_factor_gaps",
    "fetch_adj_factor_range",
    "group_contiguous_dates",
    "write_adj_factor_range",
]
