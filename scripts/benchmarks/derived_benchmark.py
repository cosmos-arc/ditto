#!/usr/bin/env python3
"""Unified derived engine benchmark harness."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import polars as pl

RegressionSeverity = Literal["pass", "warning", "error"]


@dataclass(frozen=True)
class BenchmarkScale:
    """Synthetic benchmark scale definition."""

    name: str
    instrument_count: int
    day_count: int
    slot_count: int

    @property
    def row_count(self) -> int:
        return self.instrument_count * self.day_count * self.slot_count


@dataclass(frozen=True)
class BenchmarkWorkload:
    """Logical workload family tracked by Phase 6."""

    name: str
    scales: tuple[BenchmarkScale, ...]


@dataclass(frozen=True)
class BenchmarkResult:
    """Single benchmark result."""

    workload: str
    scale: str
    row_count: int
    elapsed_seconds: float
    throughput_rows_per_second: float


@dataclass(frozen=True)
class RegressionBudget:
    """Phase 1 regression budget thresholds."""

    warning_degradation: float = 0.15
    error_degradation: float = 0.25

    def classify(
        self,
        *,
        elapsed_seconds: float,
        baseline_seconds: float,
    ) -> RegressionSeverity:
        degradation = (elapsed_seconds - baseline_seconds) / baseline_seconds
        if degradation > self.error_degradation:
            return "error"
        if degradation > self.warning_degradation:
            return "warning"
        return "pass"


SCALE_S = BenchmarkScale(name="S", instrument_count=10, day_count=100, slot_count=10)
SCALE_M = BenchmarkScale(name="M", instrument_count=100, day_count=500, slot_count=10)
SCALE_L = BenchmarkScale(name="L", instrument_count=500, day_count=1000, slot_count=10)
WORKLOAD_SCALES = (SCALE_S, SCALE_M, SCALE_L)


def default_workloads() -> list[BenchmarkWorkload]:
    """Return the Phase 6 benchmark families."""

    scales = WORKLOAD_SCALES
    return [
        BenchmarkWorkload(name="query", scales=scales),
        BenchmarkWorkload(name="materialize", scales=scales),
        BenchmarkWorkload(name="shadow_compare", scales=scales),
    ]


def _scale_by_name(scale_name: str) -> BenchmarkScale:
    for scale in WORKLOAD_SCALES:
        if scale.name == scale_name:
            return scale
    raise ValueError(f"unknown scale: {scale_name}")


def build_fixture(scale: BenchmarkScale) -> pl.DataFrame:
    """Build a deterministic synthetic market-like fixture."""

    row_ids = pl.int_range(0, scale.row_count, eager=True)
    base_date = date(2024, 1, 1)
    base_time = datetime(2024, 1, 1)

    return (
        pl.DataFrame({"row_id": row_ids})
        .with_columns(
            (
                (pl.col("row_id") % scale.instrument_count)
                .cast(pl.Int32)
                .alias("instrument_id")
            ),
            ((pl.col("row_id") // scale.instrument_count) % scale.day_count)
            .cast(pl.Int32)
            .alias("day_offset"),
            (pl.col("row_id") // (scale.instrument_count * scale.day_count))
            .cast(pl.Int16)
            .alias("slot"),
        )
        .with_columns(
            (
                pl.lit(base_date)
                + pl.duration(days=pl.col("day_offset").cast(pl.Int64))
            ).alias("trade_date"),
            (
                pl.lit(base_time)
                + pl.duration(days=pl.col("day_offset").cast(pl.Int64))
                + pl.duration(minutes=pl.col("slot").cast(pl.Int64) * 5)
            ).alias("availability_time"),
            (
                pl.lit(100.0)
                + pl.col("instrument_id").cast(pl.Float64) * 0.25
                + pl.col("day_offset").cast(pl.Float64) * 0.05
                + pl.col("slot").cast(pl.Float64) * 0.005
            ).alias("close"),
            (
                pl.lit(10_000)
                + pl.col("instrument_id").cast(pl.Int64) * 25
                + pl.col("day_offset").cast(pl.Int64) * 10
                + pl.col("slot").cast(pl.Int64)
            ).alias("volume"),
        )
        .drop("row_id")
    )


def _run_query_workload(frame: pl.DataFrame) -> pl.DataFrame:
    latest_trade_date = frame.select(pl.col("trade_date").max()).item()
    start_trade_date = latest_trade_date - timedelta(days=29)
    return (
        frame.lazy()
        .filter(pl.col("trade_date") >= start_trade_date)
        .group_by("instrument_id")
        .agg(
            pl.col("close").mean().alias("mean_close"),
            pl.col("close").last().alias("latest_close"),
            pl.col("volume").sum().alias("volume_sum"),
        )
        .sort("instrument_id")
        .collect()
    )


def _run_materialize_workload(frame: pl.DataFrame) -> pl.DataFrame:
    sorted_frame = frame.lazy().sort(["instrument_id", "trade_date", "slot"])
    return (
        sorted_frame.with_columns(
            (pl.col("close") / pl.col("close").shift(1).over("instrument_id") - 1.0)
            .fill_null(0.0)
            .alias("return_1d"),
        )
        .with_columns(
            pl.col("return_1d")
            .shift(1)
            # PIT 安全: shift(1) 保证窗口使用 [T-5, T-1] 范围
            .rolling_mean(window_size=5, min_samples=3)
            .over("instrument_id")
            .fill_null(0.0)
            .alias("factor_value"),
        )
        .select(
            "instrument_id",
            "trade_date",
            "slot",
            "availability_time",
            "factor_value",
        )
        .collect()
    )


def _run_shadow_compare_workload(frame: pl.DataFrame) -> pl.DataFrame:
    baseline = _run_materialize_workload(frame)
    candidate = baseline.with_columns(
        (
            pl.col("factor_value")
            + (pl.col("instrument_id").cast(pl.Float64) % 7) * 0.0001
            + pl.col("slot").cast(pl.Float64) * 0.00001
        ).alias("factor_value")
    )
    return (
        candidate.lazy()
        .rename({"factor_value": "candidate_value"})
        .join(
            baseline.lazy().rename({"factor_value": "baseline_value"}),
            on=["instrument_id", "trade_date", "slot", "availability_time"],
            how="inner",
        )
        .with_columns(
            (pl.col("candidate_value") - pl.col("baseline_value"))
            .abs()
            .alias("abs_diff")
        )
        .select(
            pl.len().alias("row_count"),
            pl.col("abs_diff").mean().alias("mean_abs_diff"),
            pl.col("abs_diff").max().alias("max_abs_diff"),
        )
        .collect()
    )


def _measure(
    *,
    workload_name: str,
    scale: BenchmarkScale,
    iterations: int,
) -> BenchmarkResult:
    frame = build_fixture(scale)
    if workload_name == "query":
        runner = _run_query_workload
    elif workload_name == "materialize":
        runner = _run_materialize_workload
    elif workload_name == "shadow_compare":
        runner = _run_shadow_compare_workload
    else:
        raise ValueError(f"unsupported workload: {workload_name}")

    runner(frame)
    durations: list[float] = []
    for _ in range(iterations):
        started_at = time.perf_counter()
        runner(frame)
        durations.append(time.perf_counter() - started_at)

    elapsed_seconds = statistics.median(durations)
    return BenchmarkResult(
        workload=workload_name,
        scale=scale.name,
        row_count=scale.row_count,
        elapsed_seconds=elapsed_seconds,
        throughput_rows_per_second=scale.row_count / elapsed_seconds,
    )


def run_benchmark_suite(
    *,
    scales: tuple[str, ...] = ("S", "M", "L"),
    iterations: int = 3,
) -> list[BenchmarkResult]:
    """Execute the benchmark suite for the selected scales."""

    results: list[BenchmarkResult] = []
    selected_scales = tuple(_scale_by_name(scale_name) for scale_name in scales)
    selected_scale_names = {scale.name for scale in selected_scales}
    for workload in default_workloads():
        for scale in workload.scales:
            if scale.name not in selected_scale_names:
                continue
            results.append(
                _measure(
                    workload_name=workload.name,
                    scale=scale,
                    iterations=iterations,
                )
            )
    return results


def write_baseline(results: list[BenchmarkResult], output_path: Path) -> None:
    """Persist benchmark results as a local baseline file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        f"{result.workload}:{result.scale}": round(result.elapsed_seconds, 6)
        for result in results
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def format_results_as_json(results: list[BenchmarkResult]) -> str:
    """Render benchmark results as JSON."""

    payload = [asdict(result) for result in results]
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Derived benchmark harness")
    parser.add_argument(
        "--scale",
        action="append",
        choices=[scale.name for scale in WORKLOAD_SCALES],
        help="Only run the selected scale (repeatable). Default: all scales.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of timed iterations per workload. Default: 3.",
    )
    parser.add_argument(
        "--baseline-out",
        type=Path,
        help="Write the measured elapsed-seconds baseline to a JSON file.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""

    parser = _build_parser()
    args = parser.parse_args()
    scales = tuple(args.scale) if args.scale else ("S", "M", "L")
    results = run_benchmark_suite(scales=scales, iterations=args.iterations)
    if args.baseline_out is not None:
        write_baseline(results, args.baseline_out)
    print(format_results_as_json(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
