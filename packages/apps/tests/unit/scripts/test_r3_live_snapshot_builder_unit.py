"""Unit contracts for immutable R3 live research snapshot construction."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest
from ditto_apps.registry.live.r3_live_market_projection import _normalized_bars
from ditto_apps.registry.live.r3_live_snapshot_builder import (
    _certified_source_snapshots,
    _instrument_rules,
    _stock_membership,
)
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader


def _raw_bars(rows: tuple[tuple[date, int, float], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [item[0] for item in rows],
            "instrument_id": [item[1] for item in rows],
            "open": [item[2] for item in rows],
            "high": [item[2] for item in rows],
            "low": [item[2] for item in rows],
            "close": [item[2] for item in rows],
            "pre_close": [item[2] - 1.0 for item in rows],
            "volume": [1_000.0] * len(rows),
            "amount": [10_000.0] * len(rows),
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        },
    )


def _membership(
    rows: tuple[tuple[date, int], ...],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [item[0] for item in rows],
            "instrument_id": [item[1] for item in rows],
        },
        schema={"trade_date": pl.Date, "instrument_id": pl.Int64},
    )


@pytest.mark.unit
def test_normalized_bars_seed_first_suspension_from_pre_window_bar() -> None:
    frame = _normalized_bars(
        _raw_bars(
            (
                (date(2015, 1, 30), 1, 10.0),
                (date(2015, 2, 3), 1, 11.0),
            )
        ),
        _membership(((date(2015, 2, 2), 1), (date(2015, 2, 3), 1))),
        authority_snapshot_id="source-1",
    )

    first = frame.sort("trade_date").row(0, named=True)
    assert first["close"] == 10.0
    assert first["prev_close"] == 10.0
    assert first["is_suspended"] is True


@pytest.mark.unit
def test_normalized_bars_emit_numeric_price_limits_and_complete_grid() -> None:
    frame = _normalized_bars(
        _raw_bars(((date(2015, 2, 2), 1, 10.0),)),
        _membership(((date(2015, 2, 2), 1), (date(2015, 2, 3), 1))),
        authority_snapshot_id="source-1",
    ).sort("trade_date")

    assert frame.height == 2
    assert frame.schema["limit_up"] == pl.Float64
    assert frame.schema["limit_down"] == pl.Float64
    assert frame["limit_up"].to_list() == pytest.approx([9.9, 11.0])
    assert frame["limit_down"].to_list() == pytest.approx([8.1, 9.0])


@pytest.mark.unit
def test_stock_membership_uses_only_strictly_prior_index_composition() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE index_weight "
        "(index_id TEXT, instrument_id INTEGER, effective_from TEXT)"
    )
    connection.executemany(
        "INSERT INTO index_weight VALUES (?, ?, ?)",
        (
            ("000300.SH", 1, "2015-01-30"),
            ("000300.SH", 2, "2015-02-03"),
        ),
    )

    frame = _stock_membership(
        connection,
        (date(2015, 2, 2), date(2015, 2, 3), date(2015, 2, 4)),
        authority_snapshot_id="source-1",
    )

    assert frame.select("trade_date", "instrument_id", "known_at").rows() == [
        (date(2015, 2, 2), 1, date(2015, 1, 30)),
        (date(2015, 2, 3), 1, date(2015, 1, 30)),
        (date(2015, 2, 4), 2, date(2015, 2, 3)),
    ]


@pytest.mark.unit
def test_instrument_rules_are_not_backdated_before_listing() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE instrument (
            instrument_id INTEGER,
            ticker TEXT,
            exchange TEXT,
            asset_class TEXT,
            list_date TEXT,
            delist_date TEXT,
            board TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO instrument VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, "600001", "SSE", "stock", "2016-01-04", None, "main"),
    )
    connection.execute(
        "INSERT INTO instrument VALUES (?, ?, ?, ?, ?, ?, ?)",
        (3_000_149, "000300", "SSE", "index", "2005-04-08", None, None),
    )

    frame = _instrument_rules(
        connection,
        (1,),
        authority_snapshot_id="source-1",
    )

    target = frame.filter(pl.col("instrument_id") == 1)
    assert target["known_at"].to_list() == [date(2016, 1, 4)]
    assert target["as_of_date"].to_list() == [date(2016, 1, 4)]
    connection.close()


@pytest.mark.unit
def test_certified_source_snapshots_exclude_superseded_history() -> None:
    certified_ids = {
        "calendar": ("calendar-current",),
        "etf_basic": ("etf-basic-current",),
        "etf_daily": ("etf-daily-current",),
        "index_daily": ("index-daily-current",),
    }

    class _Certifications:
        def get_active_report(self, dataset_id: str, profile: str) -> object:
            assert profile == "r2-modern-a-share-v1"
            return SimpleNamespace(
                report_id=f"report-{dataset_id}",
                dataset_id=dataset_id,
                generated_at=datetime(2026, 8, 1, tzinfo=UTC),
                coverage=SimpleNamespace(
                    complete_from=date(2015, 1, 1),
                    target_to=date(2026, 8, 1),
                ),
                evidence=SimpleNamespace(snapshot_ids=certified_ids[dataset_id]),
            )

    current = {
        snapshot_id: SimpleNamespace(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
            request_start="2015-01-01",
            request_end="2026-07-31",
            payload_retained=True,
            payload_uri=f"artifact://{snapshot_id}",
        )
        for dataset_id, values in certified_ids.items()
        for snapshot_id in values
    }
    current["etf-daily-old"] = SimpleNamespace(
        snapshot_id="etf-daily-old",
        dataset_id="etf_daily",
        request_start="2015-01-01",
        request_end="2025-12-31",
        payload_retained=True,
        payload_uri="artifact://etf-daily-old",
    )

    class _Snapshots:
        def get_snapshot(self, snapshot_id: str) -> object | None:
            return current.get(snapshot_id)

    sources, authority, by_dataset, bindings = _certified_source_snapshots(
        certification_reader=cast("CertificationReader", _Certifications()),
        snapshot_reader=cast("ProviderSnapshotReader", _Snapshots()),
        lane="etf",
    )

    assert "etf-daily-old" not in sources
    assert authority == "etf-daily-current"
    assert by_dataset["etf_daily"] == ("etf-daily-current",)
    assert tuple(binding.dataset_id for binding in bindings) == (
        "calendar",
        "etf_basic",
        "etf_daily",
        "index_daily",
    )
    assert all(binding.certified_through == "2026-08-01" for binding in bindings)
