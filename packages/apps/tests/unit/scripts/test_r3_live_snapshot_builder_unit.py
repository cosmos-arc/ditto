"""Unit contracts for immutable R3 live research snapshot construction."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_apps.registry.live.r3_live_market_projection import (
    _membership_with_observed_bar_history,
    _normalized_bars,
)
from ditto_apps.registry.live.r3_live_snapshot_builder import (
    _BENCHMARK_INSTRUMENT_ID,
    _certified_source_snapshots,
    _dependency_evidence,
    _ensure_live_catalog_parents,
    _evidence,
    _factor_evidence,
    _fundamental,
    _instrument_rules,
    _membership_with_complete_fundamentals,
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
def test_normalized_benchmark_bars_keep_required_price_limits_non_null() -> None:
    """Benchmark rows share the strict frozen bars schema used by the data feed."""
    frame = _normalized_bars(
        _raw_bars(((date(2015, 2, 2), _BENCHMARK_INSTRUMENT_ID, 3_500.0),)),
        _membership(((date(2015, 2, 2), _BENCHMARK_INSTRUMENT_ID),)),
        authority_snapshot_id="source-1",
    )

    assert frame["limit_up"].null_count() == 0
    assert frame["limit_down"].null_count() == 0
    assert frame["limit_up"].to_list() == pytest.approx([3_848.9])
    assert frame["limit_down"].to_list() == pytest.approx([3_149.1])


@pytest.mark.unit
def test_membership_starts_at_first_observed_bar_without_future_backfill() -> None:
    frame = _membership_with_observed_bar_history(
        _raw_bars(((date(2015, 2, 4), 1, 10.0),)),
        _membership(
            (
                (date(2015, 2, 2), 1),
                (date(2015, 2, 3), 1),
                (date(2015, 2, 4), 1),
                (date(2015, 2, 5), 1),
            )
        ),
    )

    assert frame.rows() == [
        (date(2015, 2, 4), 1),
        (date(2015, 2, 5), 1),
    ]


@pytest.mark.unit
def test_membership_fails_closed_when_member_has_no_observed_bar() -> None:
    with pytest.raises(ValueError, match="live members have no observed bars: 2"):
        _membership_with_observed_bar_history(
            _raw_bars(((date(2015, 2, 2), 1, 10.0),)),
            _membership(((date(2015, 2, 2), 1), (date(2015, 2, 2), 2))),
        )


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
def test_stock_fundamental_projection_keeps_only_complete_pit_rows() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE income_statement "
        "(instrument_id INTEGER, report_date TEXT, knowledge_date TEXT, "
        "net_profit REAL, revenue REAL, eps REAL)"
    )
    connection.execute(
        "CREATE TABLE balance_sheet "
        "(instrument_id INTEGER, report_date TEXT, knowledge_date TEXT, "
        "net_assets REAL)"
    )
    connection.executemany(
        "INSERT INTO income_statement VALUES (?, ?, ?, ?, ?, ?)",
        (
            (1, "2014-12-31", "2015-01-30", 10.0, 100.0, 0.5),
            (1, "2015-03-31", "2015-04-30", 20.0, 200.0, 0.7),
        ),
    )
    connection.executemany(
        "INSERT INTO balance_sheet VALUES (?, ?, ?, ?)",
        (
            (1, "2014-12-31", "2015-01-31", 50.0),
            (1, "2015-03-31", "2015-05-01", None),
        ),
    )

    frame = _fundamental(
        connection,
        "stock",
        (1,),
        authority_snapshot_id="source-1",
    )

    assert frame.select(
        "instrument_id", "known_at", "roe", "net_margin", "eps"
    ).rows() == [(1, date(2015, 1, 31), 0.2, 0.1, 0.5)]
    assert frame.null_count().row(0) == (0, 0, 0, 0, 0, 0)
    connection.close()


@pytest.mark.unit
def test_etf_fundamental_projection_uses_explicit_non_applicable_values() -> None:
    connection = sqlite3.connect(":memory:")

    frame = _fundamental(
        connection,
        "etf",
        (11, 12),
        authority_snapshot_id="source-1",
    )

    assert frame.select("instrument_id", "roe", "net_margin", "eps").rows() == [
        (11, 0.0, 0.0, 0.0),
        (12, 0.0, 0.0, 0.0),
    ]
    assert frame.null_count().row(0) == (0, 0, 0, 0, 0, 0)
    connection.close()


@pytest.mark.unit
def test_stock_membership_starts_after_complete_fundamentals_are_known() -> None:
    membership = pl.DataFrame(
        {
            "trade_date": (date(2015, 2, 2), date(2015, 2, 3), date(2015, 2, 4)),
            "instrument_id": (1, 1, 1),
            "is_member": (True, True, True),
            "known_at": (date(2015, 1, 30),) * 3,
            "source_snapshot_id": ("source-1",) * 3,
        }
    )
    fundamental = pl.DataFrame(
        {
            "instrument_id": (1,),
            "known_at": (date(2015, 2, 2),),
            "roe": (0.2,),
            "net_margin": (0.1,),
            "eps": (0.5,),
            "source_snapshot_id": ("source-1",),
        }
    )

    frame = _membership_with_complete_fundamentals(membership, fundamental)

    assert frame["trade_date"].to_list() == [date(2015, 2, 3), date(2015, 2, 4)]


@pytest.mark.unit
def test_live_catalog_parents_are_saved_before_dataset_snapshot(mocker) -> None:
    catalog = mocker.Mock()
    catalog.get_spine_spec.return_value = None
    catalog.get_dataset_spec.return_value = None
    catalog.get_spine_snapshot.return_value = None
    calendar_input = ContentAddressedResearchInput(
        input_id="r3-live-stock-calendar",
        artifact_kind="calendar",
        content_hash="a" * 64,
        schema_hash="b" * 64,
    )

    spine_snapshot_id = _ensure_live_catalog_parents(
        catalog,
        lane="stock",
        calendar_input=calendar_input,
        calendar_row_count=4_200,
        created_at="2026-08-01T00:00:00Z",
    )

    assert spine_snapshot_id.startswith("r3-live-stock-calendar-")
    assert catalog.save_spine_spec.call_count == 1
    assert catalog.save_dataset_spec.call_count == 1
    assert catalog.save_spine_snapshot.call_count == 1
    saved_spine = catalog.save_spine_snapshot.call_args.args[0]
    assert saved_spine.spine_snapshot_id == spine_snapshot_id
    assert saved_spine.manifest_hash == "a" * 64
    assert saved_spine.row_count == 4_200


@pytest.mark.unit
def test_live_spine_identity_binds_the_content_addressed_calendar_input(mocker) -> None:
    catalog = mocker.Mock()
    catalog.get_spine_spec.return_value = None
    catalog.get_dataset_spec.return_value = None
    catalog.get_spine_snapshot.return_value = None

    first = _ensure_live_catalog_parents(
        catalog,
        lane="stock",
        calendar_input=ContentAddressedResearchInput(
            input_id="calendar@sha256:first",
            artifact_kind="calendar",
            content_hash="a" * 64,
            schema_hash="b" * 64,
        ),
        calendar_row_count=4_200,
        created_at="2026-08-01T00:00:00Z",
    )
    second = _ensure_live_catalog_parents(
        catalog,
        lane="stock",
        calendar_input=ContentAddressedResearchInput(
            input_id="calendar@sha256:second",
            artifact_kind="calendar",
            content_hash="a" * 64,
            schema_hash="b" * 64,
        ),
        calendar_row_count=4_200,
        created_at="2026-08-01T00:00:00Z",
    )

    assert first != second


@pytest.mark.unit
def test_factor_evidence_freezes_every_versioned_code_registration() -> None:
    factors = _factor_evidence()
    evidence = {item.input_id: item for item, _payload in factors}

    assert {
        "momentum_1m@1",
        "quality_roe@1",
        "value_pe@1",
        "volatility_factor@1",
    }.issubset(evidence)
    assert all(item.artifact_kind == "factor" for item in evidence.values())
    assert all(len(item.content_hash) == 64 for item in evidence.values())
    assert len({item.schema_hash for item in evidence.values()}) == 1


@pytest.mark.unit
def test_live_mutable_inputs_use_content_addressed_artifact_ids() -> None:
    membership = _membership(((date(2015, 2, 2), 1),))
    first, _ = _evidence(
        "stock_daily",
        "bars",
        _normalized_bars(
            _raw_bars(((date(2015, 2, 2), 1, 10.0),)),
            membership,
            authority_snapshot_id="source-1",
        ),
    )
    changed, _ = _evidence(
        "stock_daily",
        "bars",
        _normalized_bars(
            _raw_bars(((date(2015, 2, 2), 1, 11.0),)),
            membership,
            authority_snapshot_id="source-1",
        ),
    )
    dependency, _ = _dependency_evidence("adj_factor", ("snapshot-1",))

    assert first.input_id == f"stock_daily@sha256:{first.content_hash}"
    assert changed.input_id == f"stock_daily@sha256:{changed.content_hash}"
    assert first.input_id != changed.input_id
    assert dependency.input_id == f"adj_factor@sha256:{dependency.content_hash}"


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
