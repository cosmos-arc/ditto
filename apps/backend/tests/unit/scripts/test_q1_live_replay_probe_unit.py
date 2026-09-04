"""Unit tests for the redacted Q1 live replay probe."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_apps.scripts.q1_live_replay_probe import (
    ReplayPartition,
    ReplayRunObservation,
    _is_durable_payload,
    _iter_durable_payload_paths,
    collect_live_replay_evidence,
)


def test_sqlite_runtime_sidecars_are_not_durable_payloads() -> None:
    assert _is_durable_payload("constituent.db") is True
    assert _is_durable_payload("constituent.db-wal") is False
    assert _is_durable_payload("constituent.db-shm") is False


def test_durable_payload_paths_cover_market_and_provider_payloads(
    tmp_path: Path,
) -> None:
    expected = {
        "market/index/constituent.db",
        "market/stock/bars/2024.parquet",
        "provider_payloads/tushare/stock_daily/payload.parquet",
    }
    for relative in expected | {
        "market/index/constituent.db-wal",
        "market/index/constituent.db-shm",
        "locks/stock_daily.lock",
        "metadata/metadata.sqlite",
    }:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())

    observed = {
        path.relative_to(tmp_path).as_posix()
        for path in _iter_durable_payload_paths(tmp_path)
    }

    assert observed == expected


def test_collect_live_replay_evidence_accepts_exact_skip_replay() -> None:
    state = {
        "ingestion_records": [{"dataset": "stock_daily", "status": "SUCCESS"}],
        "payloads": [{"path": "market/stock/bars/2024.parquet", "sha256": "a" * 64}],
        "sqlite_table_row_counts": {"instrument": 1},
    }

    evidence = collect_live_replay_evidence(
        partitions=(ReplayPartition("stock_daily", "2024-03-29"),),
        run_replay=lambda: (
            ReplayRunObservation("stock_daily", "2024-03-29", "skipped", 5_356),
        ),
        observe=lambda: state,
    )

    assert evidence["passed"] is True
    assert evidence["before_state_sha256"] == evidence["after_state_sha256"]
    assert evidence["replay_results"] == [
        {
            "dataset": "stock_daily",
            "trade_date": "2024-03-29",
            "row_count": 5_356,
            "status": "skipped",
        }
    ]
    assert evidence["partitions"] == [
        {"dataset": "stock_daily", "trade_date": "2024-03-29"}
    ]


def test_collect_live_replay_evidence_fails_when_state_mutates() -> None:
    states = iter(
        (
            {"payloads": [{"sha256": "a" * 64}]},
            {"payloads": [{"sha256": "b" * 64}]},
        )
    )

    with pytest.raises(ValueError, match=r"^Q1 replay mutated durable runtime state$"):
        collect_live_replay_evidence(
            partitions=(ReplayPartition("stock_daily", "2024-03-29"),),
            run_replay=lambda: (
                ReplayRunObservation("stock_daily", "2024-03-29", "skipped", 5_356),
            ),
            observe=lambda: next(states),
        )


def test_collect_live_replay_evidence_fails_when_dataset_is_not_skipped() -> None:
    state = {"payloads": [{"sha256": "a" * 64}]}

    with pytest.raises(
        ValueError, match=r"^Q1 replay was not a complete partition skip$"
    ):
        collect_live_replay_evidence(
            partitions=(ReplayPartition("stock_daily", "2024-03-29"),),
            run_replay=lambda: (
                ReplayRunObservation("stock_daily", "2024-03-29", "success", 5_356),
            ),
            observe=lambda: state,
        )


def test_collect_live_replay_evidence_requires_exact_partition_dates() -> None:
    state = {"payloads": [{"sha256": "a" * 64}]}

    with pytest.raises(
        ValueError, match=r"^Q1 replay was not a complete partition skip$"
    ):
        collect_live_replay_evidence(
            partitions=(ReplayPartition("corporate_actions", "2024-03-28"),),
            run_replay=lambda: (
                ReplayRunObservation("corporate_actions", "2024-03-29", "skipped", 50),
            ),
            observe=lambda: state,
        )
