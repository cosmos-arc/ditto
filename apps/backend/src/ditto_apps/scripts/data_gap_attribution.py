"""
#658 批次2 逐证券缺口归因（复用覆盖审计引擎，只读）.

基线（2026-11-03）给出异常计数——股票 10,201 个 trading_no_bar、19,274 个
缺状态会话、ETF 92 个有价缺因子、no_status_dataset 210,870、上市日前 bar
76,267、缺上市日名册 3——冻结矩阵将其定向到批次2「归因」：这些是待归因
异常，不是已确认源端丢数。本脚本对真实数据根执行覆盖审计
（``PriceCoverageAuditService``→``audit_session_coverage``，与 ops CLI 同一
引擎），并对 gap_detail／anomaly_detail 逐证券做生命周期归因：

- ``bse_out_of_scope``：BSE（.BJ）个股——正式范围为沪深 A 股，BSE 个股
  完整链在 47 项范围外（冻结矩阵共同边界），其缺口不构成股票覆盖失败。
- ``never_any_bar``：窗口内从无任何行情（上市即无价：源端不覆盖或从未
  交易）。
- ``head_before_first_bar``：缺口早于该证券首根行情（上市初期静默）。
- ``tail_after_last_bar``：缺口晚于该证券末根行情（退市前长停／停供尾段）。
- ``silent_stretch``：前后都有行情的中间静默段（停牌或真缺段——无状态
  证据时不可分辨，显式留作残余）。

输出 JSON 报告（含每 kind×bucket 计数与代表性样本），供批次2 证据文档
消费；不修改任何数据。用法::

    python -m ditto_apps.scripts.data_gap_attribution \
        --data-root <DITTO_DATA_ROOT> --start 2014-01-01 --end <YYYY-MM-DD> \
        [--output report.json]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import orjson
import polars as pl
from ditto_application.processes.quality.coverage_audit import (
    PriceCoverageAuditRequest,
    PriceCoverageAuditService,
)
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

from ditto_apps.registry.container import make_app_container

__all__ = ["classify_gap_rows", "collect_attribution", "main"]

_SCHEMA = "ditto.data-gap-attribution.v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SAMPLE_LIMIT = 8

# 归因桶优先级：BSE 范围外 > 从无行情 > 首价前 > 末价后 > 中间静默段。
BUCKETS = (
    "bse_out_of_scope",
    "never_any_bar",
    "head_before_first_bar",
    "tail_after_last_bar",
    "silent_stretch",
)


def classify_gap_rows(
    gap_detail: pl.DataFrame,
    *,
    tickers: dict[int, str],
    bars: pl.DataFrame,
) -> pl.DataFrame:
    """
    给 gap_detail 逐行标注生命周期归因桶（纯函数）.

    Args:
        gap_detail: 审计产出的逐行缺口帧（instrument_id/trade_date/kind）。
        tickers: instrument_id -> source_ticker（主映射）。
        bars: 同窗口日线业务键帧（instrument_id/trade_date），用于推导
            每证券首末行情位置。

    """
    if gap_detail.is_empty():
        return gap_detail.with_columns(pl.lit("none").alias("bucket"))
    ticker_frame = pl.DataFrame(
        {
            "instrument_id": list(tickers.keys()),
            "ticker": list(tickers.values()),
        },
        schema={"instrument_id": pl.Int64, "ticker": pl.String},
    )
    bar_stats = bars.group_by("instrument_id").agg(
        pl.col("trade_date").min().alias("_first_bar"),
        pl.col("trade_date").max().alias("_last_bar"),
    )
    annotated = (
        gap_detail.join(bar_stats, on="instrument_id", how="left")
        .join(ticker_frame, on="instrument_id", how="left")
        .with_columns(
            pl.when(pl.col("ticker").cast(pl.String).str.ends_with(".BJ"))
            .then(pl.lit(BUCKETS[0]))
            .when(pl.col("_first_bar").is_null())
            .then(pl.lit(BUCKETS[1]))
            .when(pl.col("trade_date") < pl.col("_first_bar"))
            .then(pl.lit(BUCKETS[2]))
            .when(pl.col("trade_date") > pl.col("_last_bar"))
            .then(pl.lit(BUCKETS[3]))
            .otherwise(pl.lit(BUCKETS[4]))
            .alias("bucket")
        )
    )
    return annotated


def _attribute_asset_class(
    *,
    audit_service: PriceCoverageAuditService,
    market: MarketService,
    metadata: MetadataService,
    asset_class: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    request = PriceCoverageAuditRequest(
        start_date=start,
        end_date=end,
        asset_class=asset_class,
        dataset="daily",
        detail_limit=0,
    )
    report = audit_service.run(request)
    session = report.session
    roster = metadata.find_securities(asset_class=asset_class, is_active=None)
    tickers = {
        int(instrument_id): str(ticker)
        for instrument_id, ticker in roster.select("instrument_id", "source_ticker")
        .drop_nulls()
        .iter_rows()
    }
    bars = (
        market.get_stock_bars(start, end)
        if asset_class == "stock"
        else (market.get_etf_bars(start, end))
    )
    bars = bars.select(
        pl.col("instrument_id").cast(pl.Int64), pl.col("trade_date").cast(pl.Date)
    ).unique()

    annotated = classify_gap_rows(session.gap_detail, tickers=tickers, bars=bars)
    attribution: dict[str, dict[str, int]] = defaultdict(dict)
    samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    if annotated.height:
        counted = annotated.group_by(["kind", "bucket"]).len()
        for kind, bucket, count in counted.iter_rows():
            attribution[str(kind)][str(bucket)] = int(count)
        for kind in sorted(attribution):
            head = (
                annotated.filter(pl.col("kind") == kind)
                .sort(["bucket", "instrument_id", "trade_date"])
                .head(_SAMPLE_LIMIT)
            )
            for _, row in enumerate(head.iter_rows(named=True)):
                samples[kind].append(
                    {
                        "ticker": tickers.get(
                            int(row["instrument_id"]), str(row["instrument_id"])
                        ),
                        "instrument_id": str(row["instrument_id"]),
                        "trade_date": str(row["trade_date"]),
                        "bucket": str(row["bucket"]),
                    }
                )

    anomalies = _attribute_anomalies(
        session.anomaly_detail, tickers=tickers, roster=roster
    )
    return {
        "gap_counts": session.gap_counts,
        "expected_sessions": session.expected_sessions,
        "present_sessions": session.present_sessions,
        "attribution": dict(attribution),
        "gap_samples": dict(samples),
        "anomalies": anomalies,
    }


def _attribute_anomalies(
    anomaly_detail: pl.DataFrame,
    *,
    tickers: dict[int, str],
    roster: pl.DataFrame,
) -> dict[str, Any]:
    """异常类计数的结构归因：交易所分布、逐样本清单、名册缺口名单."""
    result: dict[str, Any] = {}
    missing_list_date = roster.filter(pl.col("list_date").is_null())
    if missing_list_date.height:
        result["master_list_date_missing"] = {
            "count": missing_list_date.height,
            "tickers": [
                str(ticker)
                for ticker in missing_list_date.select("source_ticker")
                .drop_nulls()["source_ticker"]
                .to_list()
            ],
        }
    if anomaly_detail.is_empty():
        return result
    with_ticker = anomaly_detail.with_columns(
        pl.col("instrument_id").replace_strict(tickers, default="").alias("ticker")
    )
    for kind in sorted(with_ticker["kind"].unique().to_list()):
        rows = with_ticker.filter(pl.col("kind") == kind)
        entry: dict[str, Any] = {"count": rows.height}
        if kind == "bar_before_list_date":
            by_suffix = (
                rows.with_columns(
                    pl.when(pl.col("ticker").str.ends_with(".BJ"))
                    .then(pl.lit("BJ"))
                    .when(pl.col("ticker").str.ends_with(".SH"))
                    .then(pl.lit("SH"))
                    .when(pl.col("ticker").str.ends_with(".SZ"))
                    .then(pl.lit("SZ"))
                    .otherwise(pl.lit("other"))
                    .alias("suffix")
                )
                .group_by("suffix")
                .len()
            )
            entry["by_exchange_suffix"] = {
                str(suffix): int(count) for suffix, count in by_suffix.iter_rows()
            }
        elif kind in ("adj_factor_missing", "bar_on_non_trading_day"):
            entry["samples"] = [
                {
                    "ticker": str(row["ticker"]),
                    "trade_date": str(row["trade_date"]),
                }
                for row in rows.sort(["instrument_id", "trade_date"])
                .head(_SAMPLE_LIMIT * 4)
                .iter_rows(named=True)
            ]
        elif kind == "suspended_with_bar":
            head = (
                rows.group_by(["instrument_id", "ticker"])
                .len()
                .sort("len", descending=True)
            )
            entry["top_instruments"] = [
                {
                    "ticker": str(ticker),
                    "sessions": int(count),
                }
                for instrument_id, ticker, count in head.head(_SAMPLE_LIMIT).iter_rows()
            ]
        result[kind] = entry
    return result


def collect_attribution(*, data_root: Path, start: str, end: str) -> dict[str, Any]:
    """组装容器并对股票/ETF 执行归因（只读）."""
    previous_root = os.environ.get("DITTO_STATE_ROOT")
    os.environ["DITTO_STATE_ROOT"] = str(data_root)
    try:
        container = make_app_container()
        try:
            audit_service = container.get(PriceCoverageAuditService)
            market = container.get(MarketService)
            metadata = container.get(MetadataService)
            payload = {
                asset_class: _attribute_asset_class(
                    audit_service=audit_service,
                    market=market,
                    metadata=metadata,
                    asset_class=asset_class,
                    start=start,
                    end=end,
                )
                for asset_class in ("stock", "etf")
            }
        finally:
            container.close()
    finally:
        if previous_root is None:
            os.environ.pop("DITTO_STATE_ROOT", None)
        else:
            os.environ["DITTO_STATE_ROOT"] = previous_root
    return {
        "schema": _SCHEMA,
        "generated_at": datetime.now(_SHANGHAI).isoformat(),
        "data_root": str(data_root),
        "window": {"start": start, "end": end},
        **payload,
    }


def main(argv: list[str] | None = None) -> int:
    """执行归因并输出 JSON 报告（只读，退出码非零＝失败）."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--start", required=True, help="窗口起点 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="窗口终点 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    try:
        report = collect_attribution(
            data_root=args.data_root.absolute(), start=args.start, end=args.end
        )
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    payload = orjson.dumps(report, option=orjson.OPT_INDENT_2)
    if args.output is not None:
        args.output.write_bytes(payload)
    sys.stdout.write(payload.decode() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
