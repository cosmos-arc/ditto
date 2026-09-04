"""Repeatable p95 benchmarks for the local workstation's critical read paths."""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson

_SCHEMA_VERSION = 1
_MIN_ITERATIONS = 2


class PerformanceBudgetError(RuntimeError):
    """Raised when any measured p95 exceeds its explicit local budget."""


@dataclass(frozen=True, slots=True)
class PerformanceCase:
    """One named synchronous operation and its p95 budget."""

    name: str
    operation: Callable[[], object]
    threshold_ms: float


@dataclass(frozen=True, slots=True)
class PerformanceCaseResult:
    """Distribution summary for one operation."""

    name: str
    iterations: int
    median_ms: float
    p95_ms: float
    max_ms: float
    threshold_ms: float
    status: str


@dataclass(frozen=True, slots=True)
class WorkstationPerformanceReport:
    """Authenticated report across all mandatory workstation paths."""

    schema_version: int
    generated_at: str
    status: str
    warmup: int
    iterations: int
    cases: tuple[PerformanceCaseResult, ...]
    report_hash: str


def benchmark_workstation(
    cases: tuple[PerformanceCase, ...],
    *,
    warmup: int = 5,
    iterations: int = 40,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> WorkstationPerformanceReport:
    """Measure real callbacks and fail closed on a missing or exceeded budget."""
    if not cases or warmup < 0 or iterations < _MIN_ITERATIONS:
        raise ValueError("cases, warmup, and iterations are invalid")
    if len({case.name for case in cases}) != len(cases):
        raise ValueError("performance case names must be unique")
    results: list[PerformanceCaseResult] = []
    for case in cases:
        if not case.name or case.threshold_ms <= 0:
            raise ValueError("performance case identity or budget is invalid")
        for _ in range(warmup):
            case.operation()
        samples: list[float] = []
        for _ in range(iterations):
            started = clock_ns()
            case.operation()
            samples.append((clock_ns() - started) / 1_000_000)
        samples.sort()
        p95 = samples[math.ceil(0.95 * len(samples)) - 1]
        median = (
            samples[len(samples) // 2]
            if len(samples) % 2
            else (samples[len(samples) // 2 - 1] + samples[len(samples) // 2]) / 2
        )
        results.append(
            PerformanceCaseResult(
                name=case.name,
                iterations=iterations,
                median_ms=round(median, 6),
                p95_ms=round(p95, 6),
                max_ms=round(samples[-1], 6),
                threshold_ms=case.threshold_ms,
                status="passed" if p95 <= case.threshold_ms else "failed",
            )
        )
    failed = tuple(item.name for item in results if item.status != "passed")
    if failed:
        raise PerformanceBudgetError(
            f"p95 performance budget exceeded: {', '.join(failed)}"
        )
    generated_at = datetime.now(UTC).isoformat()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "passed",
        "warmup": warmup,
        "iterations": iterations,
        "cases": [asdict(item) for item in results],
    }
    return WorkstationPerformanceReport(
        schema_version=_SCHEMA_VERSION,
        generated_at=generated_at,
        status="passed",
        warmup=warmup,
        iterations=iterations,
        cases=tuple(results),
        report_hash=_hash(payload),
    )


def write_performance_report(
    destination: Path,
    report: WorkstationPerformanceReport,
) -> None:
    """Write an exact JSON evidence artifact."""
    path = destination.expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        orjson.dumps(asdict(report), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )


def _hash(payload: object) -> str:
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


__all__ = [
    "PerformanceBudgetError",
    "PerformanceCase",
    "PerformanceCaseResult",
    "WorkstationPerformanceReport",
    "benchmark_workstation",
    "write_performance_report",
]
