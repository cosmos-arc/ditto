"""
#630 性能基线：代表性消费者查询负载的耗时与内存实测（只读）.

「先实测后优化，不虚构性能预算」（#621 P5 条款）：本脚本对真实数据根
执行一组代表性查询——图表窗口读、单标的全历史、逐日横截面、全年
横截面（因子/回测式）、覆盖限制装载（/datasets/coverage 消费面）与
账本统计（ops status 消费面）——逐项记录耗时（中位/最大）与进程 RSS
高水位增长，末尾另报整进程峰值 RSS。输出仅是观测值，预算与优化裁决归
docs/data 性能基线记录。

用法::

    python -m ditto_apps.scripts.data_perf_baseline \
        --data-root <root> [--repeat 3] [--output baseline.json]
"""

from __future__ import annotations

import argparse
import os
import resource
import sqlite3
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import polars as pl
from ditto_data.coverage.limits import list_dataset_coverage

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.protocol_adapters import MarketReaders

__all__ = ["collect_perf_baseline", "main"]

_SCHEMA = "ditto.data-perf-baseline.v1"


def _collect(
    *,
    data_root: Path,
    repeat: int,
) -> dict[str, Any]:
    # 与 ops/API 消费者同路：经组合根取真实读栈（registry 豁免边界），
    # data_root 以 DITTO_STATE_ROOT 注入（r2 runner 同法，须绝对路径）。
    data_root = data_root.absolute()
    os.environ["DITTO_STATE_ROOT"] = str(data_root)
    container = make_app_container()
    try:
        readers = container.get(MarketReaders)
        return _collect_with_readers(
            readers=readers,
            data_root=data_root,
            repeat=repeat,
        )
    finally:
        container.close()


def _collect_with_readers(
    *,
    readers: MarketReaders,
    data_root: Path,
    repeat: int,
) -> dict[str, Any]:
    stock = readers.stock_bars
    if readers.index_bars is None or readers.etf_nav is None:
        raise ValueError("index_daily/etf_nav readers not wired on this root")
    index = readers.index_bars
    etf_nav = readers.etf_nav
    day = stock.get_date_range()[1]
    if day is None:
        raise ValueError(f"dataset under {stock.data_root} has no data")
    instrument = (
        stock.read(start_date=day, end_date=day).select("instrument_id").item(0, 0)
    )
    year = int(day[:4])
    queries: list[tuple[str, Callable[[], int]]] = [
        (
            "stock_daily 单标的 1 年窗口/图表车道",
            lambda: (
                stock.read(
                    instrument_ids=[instrument],
                    start_date=f"{year - 1}{day[4:]}",
                    end_date=day,
                ).height
            ),
        ),
        (
            "stock_daily 单标的全历史 2014 起",
            lambda: stock.read(instrument_ids=[instrument]).height,
        ),
        (
            "stock_daily 单日全市场横截面",
            lambda: stock.read(start_date=day, end_date=day).height,
        ),
        (
            "stock_daily 全年横截面/因子回测式",
            lambda: (
                stock.read(start_date=f"{year}-01-01", end_date=f"{year}-12-31").height
            ),
        ),
        (
            "adj_factor 单日全市场横截面",
            lambda: readers.stock_adj.read(start_date=day, end_date=day).height,
        ),
        (
            "index_daily 单日",
            lambda: index.read(start_date=day, end_date=day).height,
        ),
        (
            "etf_nav 单日横截面",
            lambda: etf_nav.read(start_date=day, end_date=day).height,
        ),
        ("覆盖限制装载 /datasets/coverage", lambda: len(list_dataset_coverage())),
    ]
    results: list[dict[str, Any]] = []
    for name, query in queries:
        elapsed: list[float] = []
        rows: int | None = None
        rss_before = _peak_rss_mb()
        for _ in range(repeat):
            started = time.perf_counter()
            rows = query()
            elapsed.append(time.perf_counter() - started)
        elapsed.sort()
        results.append(
            {
                "query": name,
                "rows": rows,
                "seconds_median": round(elapsed[len(elapsed) // 2], 4),
                "seconds_max": round(elapsed[-1], 4),
                "rss_peak_growth_mb": round(_peak_rss_mb() - rss_before, 1),
            }
        )
    # 账本统计（ops status 消费面）：只读 URI + 表级统计。
    ledger_started = time.perf_counter()
    catalog = (data_root / "metadata" / "metadata.sqlite").absolute()
    with sqlite3.connect(f"{catalog.as_uri()}?mode=ro", uri=True) as connection:
        ledger_rows = connection.execute(
            "SELECT COUNT(*) FROM ingestion_log"
        ).fetchone()[0]
    results.append(
        {
            "query": "ingestion_log 账本计数/ops status 消费面",
            "rows": ledger_rows,
            "seconds_median": round(time.perf_counter() - ledger_started, 4),
            "seconds_max": None,
            "rss_peak_growth_mb": None,
        }
    )
    return {
        "schema": _SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_root": str(data_root),
        "reference_day": day,
        "reference_instrument_id": instrument,
        "repeat": repeat,
        "python": sys.version.split()[0],
        "polars": pl.__version__,
        "process_peak_rss_mb": _peak_rss_mb(),
        "results": results,
    }


def _peak_rss_mb() -> float:
    """进程高水位 RSS（MB）；macOS ru_maxrss 单位是字节，Linux 是 KB."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / 1e6 if sys.platform == "darwin" else raw / 1024, 1)


def collect_perf_baseline(*, data_root: Path, repeat: int = 3) -> dict[str, Any]:
    """执行代表性查询组并返回观测基线（纯只读）."""
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    return _collect(data_root=data_root, repeat=repeat)


def main(argv: list[str] | None = None) -> int:
    """输出性能基线 JSON；预算与优化裁决归验收记录."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        baseline = collect_perf_baseline(data_root=args.data_root, repeat=args.repeat)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    payload = orjson.dumps(baseline, option=orjson.OPT_INDENT_2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    sys.stdout.write(payload.decode() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
