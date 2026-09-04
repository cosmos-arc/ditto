"""Correlation receipt spanning ingest, Agent and account-ledger operations."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, cast

import orjson
from ditto_platform.foundation import Metrics, SafeCounter, SafeHistogram, span

type WorkstationTraceStageName = Literal["ingest", "agent", "ledger"]

_MAX_CORRELATION_ID_LENGTH = 256


class WorkstationTraceError(RuntimeError):
    """Raised when the correlated chain cannot finish in exact order."""


@dataclass(frozen=True, slots=True)
class WorkstationTraceStage:
    """One successful stage linked by an evidence reference hash."""

    stage: WorkstationTraceStageName
    evidence_ref: str
    evidence_hash: str


@dataclass(frozen=True, slots=True)
class WorkstationTraceReceipt:
    """Authenticated completion receipt for the exact three-stage chain."""

    schema_version: int
    correlation_id: str
    stages: tuple[WorkstationTraceStage, ...]
    duration_seconds: float
    receipt_hash: str


def run_correlated_workstation_trace(
    *,
    correlation_id: str,
    ingest: Callable[[], str],
    agent: Callable[[], str],
    ledger: Callable[[], str],
    monotonic: Callable[[], float] = time.monotonic,
) -> WorkstationTraceReceipt:
    """Run the three callbacks in order under one trace and correlation ID."""
    normalized_id = correlation_id.strip()
    if (
        not normalized_id
        or normalized_id != correlation_id
        or len(normalized_id) > _MAX_CORRELATION_ID_LENGTH
    ):
        raise WorkstationTraceError("correlation_id is invalid")
    started = monotonic()
    completed: list[WorkstationTraceStage] = []
    operations: tuple[tuple[WorkstationTraceStageName, Callable[[], str]], ...] = (
        ("ingest", ingest),
        ("agent", agent),
        ("ledger", ledger),
    )
    with span("ditto.workstation.e2e", correlation_id=normalized_id):
        for stage, operation in operations:
            try:
                with span(
                    f"ditto.workstation.{stage}",
                    correlation_id=normalized_id,
                    stage=stage,
                ) as current_span:
                    evidence_ref = operation()
                    if not evidence_ref.strip():
                        raise ValueError("evidence reference is blank")
                    evidence_hash = _sha256(evidence_ref)
                    current_span.set_attribute("evidence_hash", evidence_hash)
                    completed.append(
                        WorkstationTraceStage(
                            stage=stage,
                            evidence_ref=evidence_ref,
                            evidence_hash=evidence_hash,
                        )
                    )
                _trace_counter().add(1, {"stage": stage, "status": "completed"})
            except Exception as exc:
                _trace_counter().add(1, {"stage": stage, "status": "failed"})
                _run_counter().add(1, {"status": "failed"})
                raise WorkstationTraceError(f"{stage} stage failed") from exc
    duration = max(0.0, monotonic() - started)
    _e2e_histogram().record(duration, {"status": "completed"})
    _run_counter().add(1, {"status": "completed"})
    stages = tuple(completed)
    return WorkstationTraceReceipt(
        schema_version=1,
        correlation_id=normalized_id,
        stages=stages,
        duration_seconds=duration,
        receipt_hash=_receipt_hash(normalized_id, stages, duration),
    )


def _sha256(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _receipt_hash(
    correlation_id: str,
    stages: tuple[WorkstationTraceStage, ...],
    duration_seconds: float,
) -> str:
    payload = orjson.dumps(
        {
            "schema_version": 1,
            "correlation_id": correlation_id,
            "stages": [asdict(item) for item in stages],
            "duration_seconds": duration_seconds,
        },
        option=orjson.OPT_SORT_KEYS,
    )
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _trace_counter() -> SafeCounter:
    return cast(
        SafeCounter,
        getattr(Metrics, "workstation_trace_stages", SafeCounter()),
    )


def _run_counter() -> SafeCounter:
    return cast(
        SafeCounter,
        getattr(Metrics, "workstation_runs", SafeCounter()),
    )


def _e2e_histogram() -> SafeHistogram:
    return cast(
        SafeHistogram,
        getattr(Metrics, "workstation_e2e_latency", SafeHistogram()),
    )


__all__ = [
    "WorkstationTraceError",
    "WorkstationTraceReceipt",
    "WorkstationTraceStage",
    "run_correlated_workstation_trace",
]
