"""Frozen ordinary pools cannot shrink to available rows."""

from datetime import date

import polars as pl
import pytest
from ditto_backtest.data_feed import (
    FeedInputRequirements,
    ProviderBackedDataFeed,
    SnapshotProviders,
)
from ditto_data.provider import BarQuery
from ditto_kernel.identity import InstrumentId
from packages.backtest.tests.unit.test_provider_data_feed_unit import _StubProvider

DATES = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"]


class _Provider(_StubProvider):
    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        ids = (
            [3_000_001]
            if query.instruments == ("000300.SH",)
            else [2_000_001, 2_000_002]
        )
        return self._bars_df.filter(pl.col("instrument_id").is_in(ids))


def _feed(missing: tuple[int, str] | None = None) -> ProviderBackedDataFeed:
    rows = [
        {
            "instrument_id": iid,
            "trade_date": day,
            "close": 4.0,
            "open": 4.0,
            "high": 4.0,
            "low": 4.0,
            "volume": 1000.0,
            "knowledge_date": date.fromisoformat(day),
            "source_snapshot_id": f"snapshot:{iid}",
            "adjustment_source_snapshot_id": f"adjustment:{iid}",
        }
        for iid in [2_000_001, 2_000_002, 3_000_001]
        for day in DATES
        if missing not in {(iid, day), (iid, "all")}
    ]
    return ProviderBackedDataFeed(
        _Provider(pl.DataFrame(rows), pl.DataFrame({"trade_date": DATES})),
        tickers=("510300.SH", "510500.SH"),
        start_date=DATES[0],
        end_date=DATES[-1],
        id_map={
            "510300.SH": InstrumentId(2_000_001),
            "510500.SH": InstrumentId(2_000_002),
        },
        benchmark_id=InstrumentId(3_000_001),
        snapshot_providers=SnapshotProviders(
            requirements=FeedInputRequirements(
                start_date=DATES[2], warmup_days=2, benchmark_ticker="000300.SH"
            )
        ),
    )


@pytest.mark.parametrize(
    "missing", [(2_000_002, "all"), (2_000_001, DATES[0]), (3_000_001, DATES[-1])]
)
def test_catalog_feed_rejects_missing_member_warmup_or_benchmark(missing) -> None:
    with pytest.raises(ValueError, match=str(missing[0])):
        _feed(missing).validate_inputs()


def test_catalog_feed_loads_benchmark_separately_without_trading_it() -> None:
    feed = _feed()
    feed.validate_inputs()
    slice_ = feed.get_slice(DATES[2])
    assert slice_.benchmark_close == 4.0
    assert set(slice_.bars) == {2_000_001, 2_000_002}


@pytest.mark.parametrize("input_kind", ["benchmark", "history"])
def test_consumed_inputs_cover_nontrading_dependencies(input_kind: str) -> None:
    from dataclasses import replace

    from ditto_backtest.replay import ReplayValidator
    from packages.backtest.tests.unit.test_manifest_unit import _make_manifest

    original, changed = _feed(), _feed()
    provider = changed._provider
    assert isinstance(provider, _Provider)
    iid = 3_000_001 if input_kind == "benchmark" else 2_000_001
    day = DATES[2] if input_kind == "benchmark" else DATES[0]
    provider._bars_df = provider._bars_df.with_columns(
        pl.when((pl.col("instrument_id") == iid) & (pl.col("trade_date") == day))
        .then(5.0)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    for feed in (original, changed):
        feed.validate_inputs()
        feed.get_slice(DATES[2])
    refs = original.consumed_input_refs()
    assert {ref.instrument_id for ref in refs} == {2_000_001, 2_000_002, 3_000_001}
    stock_ref = next(ref for ref in refs if ref.instrument_id == 2_000_001)
    assert stock_ref.date_range == (DATES[0], DATES[2])
    manifest = replace(
        _make_manifest(),
        input_refs=(InstrumentId(2_000_001), InstrumentId(2_000_002)),
        input_ref_details=refs,
    )
    replay = replace(manifest, input_ref_details=changed.consumed_input_refs())
    assert not ReplayValidator.validate(manifest, replay, [], []).input_data_match


def test_actual_history_rejects_missing_lineage_after_preflight() -> None:
    feed = _feed()
    feed.validate_inputs()
    provider = feed._provider
    assert isinstance(provider, _Provider)
    provider._bars_df = provider._bars_df.with_columns(
        pl.lit(None, dtype=pl.String).alias("source_snapshot_id")
    )
    with pytest.raises(ValueError, match=r"history.*lineage"):
        feed.get_history([InstrumentId(2_000_001)], "2026-10-13", 2)
