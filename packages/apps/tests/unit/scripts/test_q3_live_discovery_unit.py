"""Unit tests for deterministic Q3 real-data adaptations."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import polars as pl
from ditto_apps.scripts.q3_live_discovery import (
    _snapshot,
    derive_limit_state,
    normalized_rank_values,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


class _SnapshotReader:
    def __init__(self, snapshots: tuple[SimpleNamespace, ...]) -> None:
        self._snapshots = snapshots

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
    ) -> tuple[SimpleNamespace, ...]:
        return tuple(
            snapshot
            for snapshot in self._snapshots
            if dataset_id is None or snapshot.dataset_id == dataset_id
        )


def test_snapshot_selection_requires_the_exact_instrument_partition() -> None:
    snapshots = tuple(
        SimpleNamespace(
            dataset_id="etf_daily",
            request_start="2022-10-01",
            request_end="2024-03-29",
            payload_retained=True,
            payload_uri=f"{ticker}.parquet",
            canonical_asset=SimpleNamespace(
                partition_keys=(f"source_ticker={ticker}",),
            ),
            snapshot_id=f"snapshot:{ticker}",
        )
        for ticker in ("510300.SH", "518880.SH")
    )

    selected = _snapshot(
        cast(ProviderSnapshotReader, _SnapshotReader(snapshots)),
        dataset_id="etf_daily",
        request_start=date(2022, 10, 1),
        request_end=date(2024, 3, 29),
        required_partition_key="source_ticker=518880.SH",
    )

    assert selected.snapshot_id == "snapshot:518880.SH"


def test_derive_limit_state_respects_board_specific_price_limits() -> None:
    assert (
        derive_limit_state(
            source_ticker="600000.SH",
            pct_change=9.99,
            close=11.0,
            high=11.0,
            low=10.1,
            is_st=False,
        )
        == "limit_up"
    )
    assert (
        derive_limit_state(
            source_ticker="300001.SZ",
            pct_change=9.99,
            close=11.0,
            high=11.0,
            low=10.1,
            is_st=False,
        )
        == "normal"
    )
    assert (
        derive_limit_state(
            source_ticker="600001.SH",
            pct_change=-5.0,
            close=9.5,
            high=10.0,
            low=9.5,
            is_st=True,
        )
        == "limit_down"
    )


def test_normalized_rank_values_are_order_independent_and_bounded() -> None:
    frame = pl.DataFrame(
        {
            "source_ticker": ["B", "A", "C"],
            "pct_change": [2.0, -1.0, 2.0],
        }
    )

    ranked = normalized_rank_values(
        frame,
        value_column="pct_change",
        output_column="momentum_score",
    ).sort("source_ticker")

    assert ranked["momentum_score"].to_list() == [-1.0, 0.5, 0.5]
    assert all(-1.0 <= value <= 1.0 for value in ranked["momentum_score"])
