"""Unit contracts for content-addressable R2 runtime/idempotency evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ditto_apps.scripts.r2_data_acceptance import R2IdempotencySnapshot
from ditto_apps.scripts.r2_live_runtime_probe import (
    collect_live_runtime_evidence,
    observe_runtime_identity,
)


def _provider_evidence() -> dict[str, object]:
    return {
        "provider_access": [{"provider_dataset": "tushare:daily"}],
        "benchmarks": [{"dataset_id": "stock_daily"}],
        "incremental_elapsed_seconds": None,
        "workbench_query_seconds": None,
        "first_run": None,
        "second_run": None,
    }


def test_collect_live_runtime_evidence_binds_two_runs_and_workbench_query() -> None:
    observations = iter(
        (
            R2IdempotencySnapshot(2, 7, ("snapshot-a", "snapshot-b")),
            R2IdempotencySnapshot(2, 7, ("snapshot-a", "snapshot-b")),
        )
    )
    ticks = iter((0.0, 4.0, 10.0, 11.5, 20.0, 20.25))
    run_count = 0

    def run() -> None:
        nonlocal run_count
        run_count += 1

    result = collect_live_runtime_evidence(
        provider_evidence=_provider_evidence(),
        run_incremental=run,
        observe=lambda: next(observations),
        query_workbench=lambda: tuple(range(22)),
        clock=lambda: next(ticks),
    )

    assert run_count == 2
    assert result["incremental_elapsed_seconds"] == 4.0
    assert result["workbench_query_seconds"] == 0.25
    assert result["first_run"] == {
        "durable_identity_count": 2,
        "write_attempt_count": 7,
        "snapshot_ids": ["snapshot-a", "snapshot-b"],
    }
    assert result["second_run"] == result["first_run"]


def test_collect_live_runtime_evidence_rejects_second_run_write() -> None:
    observations = iter(
        (
            R2IdempotencySnapshot(1, 4, ("snapshot-a",)),
            R2IdempotencySnapshot(2, 5, ("snapshot-a", "snapshot-b")),
        )
    )
    ticks = iter((0.0, 1.0, 2.0, 3.0, 4.0, 4.1))

    with pytest.raises(ValueError, match="consecutive idempotency"):
        collect_live_runtime_evidence(
            provider_evidence=_provider_evidence(),
            run_incremental=lambda: None,
            observe=lambda: next(observations),
            query_workbench=lambda: tuple(range(22)),
            clock=lambda: next(ticks),
        )


def test_observe_runtime_identity_uses_durable_event_and_snapshot_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "metadata.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE provider_snapshots (snapshot_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE ingestion_partition_events (event_id TEXT PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT INTO provider_snapshots VALUES (?)",
            (("snapshot-b",), ("snapshot-a",)),
        )
        connection.executemany(
            "INSERT INTO ingestion_partition_events VALUES (?)",
            (("event-1",), ("event-2",), ("event-3",)),
        )

    observed = observe_runtime_identity(database)

    assert observed == R2IdempotencySnapshot(
        durable_identity_count=2,
        write_attempt_count=3,
        snapshot_ids=("snapshot-a", "snapshot-b"),
    )
